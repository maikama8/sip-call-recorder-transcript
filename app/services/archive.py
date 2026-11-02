"""Store a recording, transcribe it, and query the archive."""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.db.records import SearchHit, StoredCall, StoredSegment
from app.db.repository import CallRepository
from app.db.session import session_scope
from app.services.errors import (
    CallNotFoundError,
    DuplicateCallError,
    InvalidUploadError,
    UnsupportedMediaError,
)
from app.services.media import is_accepted_upload, suffix_of
from app.services.metadata import CallMetadata, CdrSource, merge_metadata, parse_filename
from app.services.summary import summarize_call
from app.services.transcription.base import TranscriptionProvider

_MAX_PAGE = 200


class CallArchive:
    """The recording archive the API, the CLI, and the watcher share."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        recordings_dir: Path,
        cdr: CdrSource,
        provider: TranscriptionProvider,
        *,
        max_upload_bytes: int,
        default_language: str,
    ) -> None:
        self.sessions = sessions
        self.recordings_dir = recordings_dir
        self.cdr = cdr
        self.provider = provider
        self.max_upload_bytes = max_upload_bytes
        self.default_language = default_language
        self._repo = CallRepository()

    def ingest_path(self, path: Path, *, source: str) -> StoredCall:
        """Read a file from disk and ingest it. ``source`` is ``upload`` or ``watcher``."""
        return self.ingest_bytes(
            filename=path.name,
            data=path.read_bytes(),
            source=source,
            source_path=str(path.resolve()),
            language=None,
            overrides=None,
        )

    def ingest_bytes(
        self,
        *,
        filename: str,
        data: bytes,
        source: str,
        source_path: str | None,
        language: str | None,
        overrides: CallMetadata | None,
    ) -> StoredCall:
        """Transcribe ``data`` and store the call. The file is removed if this fails."""
        if not data:
            raise InvalidUploadError("Upload is empty.")
        if len(data) > self.max_upload_bytes:
            raise InvalidUploadError(f"Upload exceeds the {self.max_upload_bytes} byte limit.")
        safe_name = Path(filename).name or "upload.bin"
        if not is_accepted_upload(safe_name):
            raise UnsupportedMediaError(
                "Upload must be wav, mp3, gsm, ogg, flac, ulaw, alaw, or a .txt transcript."
            )
        if source_path and self.already_ingested(source_path):
            raise DuplicateCallError(source_path)

        parsed = parse_filename(safe_name)
        metadata = merge_metadata(
            parsed,
            self.cdr.lookup(safe_name, parsed.uniqueid),
            overrides,
        )
        call_id = uuid4().hex[:16]
        target = self._write(call_id, safe_name, data)
        try:
            selected = language or self.default_language
            transcript = self.provider.transcribe(safe_name, data, selected)
            if metadata.duration_seconds is None and transcript.duration_seconds is not None:
                metadata = replace(metadata, duration_seconds=transcript.duration_seconds)
            summary = summarize_call(transcript.text, metadata)
            segments = tuple(
                StoredSegment(
                    speaker=segment.speaker,
                    start=segment.start,
                    end=segment.end,
                    text=segment.text,
                )
                for segment in transcript.segments
            )
            with session_scope(self.sessions) as session:
                return self._repo.insert(
                    session,
                    call_id=call_id,
                    filename=safe_name,
                    source=source,
                    source_path=source_path,
                    audio_path=str(target.resolve()),
                    language=transcript.language,
                    summary=summary,
                    transcript_text=transcript.text,
                    provider=transcript.provider,
                    notice=transcript.notice,
                    uniqueid=metadata.uniqueid,
                    linkedid=metadata.linkedid,
                    caller=metadata.caller,
                    callee=metadata.callee,
                    caller_name=metadata.caller_name,
                    direction=metadata.direction,
                    dcontext=metadata.dcontext,
                    started_at=metadata.started_at,
                    answered_at=metadata.answered_at,
                    ended_at=metadata.ended_at,
                    duration_seconds=metadata.duration_seconds,
                    billsec=metadata.billsec,
                    disposition=metadata.disposition,
                    segments=segments,
                )
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def already_ingested(self, source_path: str) -> bool:
        with session_scope(self.sessions) as session:
            return self._repo.get_by_source_path(session, source_path) is not None

    def get(self, call_id: str) -> StoredCall:
        with session_scope(self.sessions) as session:
            stored = self._repo.get(session, call_id)
        if stored is None:
            raise CallNotFoundError(call_id)
        return stored

    def list_calls(
        self,
        *,
        caller: str | None = None,
        callee: str | None = None,
        uniqueid: str | None = None,
        direction: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[StoredCall], int]:
        bounded, start = _page(limit, offset)
        with session_scope(self.sessions) as session:
            return self._repo.list_calls(
                session,
                caller=caller,
                callee=callee,
                uniqueid=uniqueid,
                direction=direction,
                query=query,
                limit=bounded,
                offset=start,
            )

    def search(self, query: str, *, limit: int = 20) -> list[SearchHit]:
        needle = query.strip()
        if not needle:
            return []
        bounded, _start = _page(limit, 0)
        with session_scope(self.sessions) as session:
            return self._repo.search(session, needle, limit=bounded)

    def count(self) -> int:
        with session_scope(self.sessions) as session:
            return self._repo.count(session)

    def delete(self, call_id: str) -> None:
        with session_scope(self.sessions) as session:
            stored = self._repo.delete(session, call_id)
        if stored is None:
            raise CallNotFoundError(call_id)
        self._unlink(stored.audio_path)

    def audio_file(self, call_id: str) -> tuple[StoredCall, Path]:
        """Return the stored audio path if it stays inside the recordings directory."""
        stored = self.get(call_id)
        if not stored.audio_path:
            raise CallNotFoundError(call_id)
        path = Path(stored.audio_path).resolve()
        root = self.recordings_dir.resolve()
        if root != path and root not in path.parents:
            raise CallNotFoundError(call_id)
        if not path.is_file():
            raise CallNotFoundError(call_id)
        return stored, path

    def reload_cdr(self) -> int:
        return self.cdr.refresh(force=True)

    def _write(self, call_id: str, filename: str, data: bytes) -> Path:
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        suffix = suffix_of(filename) or ".bin"
        target = self.recordings_dir / f"{call_id}{suffix}"
        target.write_bytes(data)
        return target

    def _unlink(self, audio_path: str | None) -> None:
        if not audio_path:
            return
        path = Path(audio_path).resolve()
        root = self.recordings_dir.resolve()
        if root == path or root in path.parents:
            path.unlink(missing_ok=True)


def _page(limit: int, offset: int) -> tuple[int, int]:
    bounded = min(max(limit, 1), _MAX_PAGE)
    start = max(offset, 0)
    return bounded, start
