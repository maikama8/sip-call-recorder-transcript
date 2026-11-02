"""HTTP routes for calls, transcripts, and search."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app import __version__
from app.api.deps import get_archive, get_settings, get_watcher
from app.config import Settings
from app.schemas.call import (
    CallDetail,
    CallListResponse,
    CdrUploadResponse,
    HealthResponse,
    SearchResponse,
    ServiceInfo,
    TranscriptResponse,
    call_detail,
    list_item,
    search_result,
    transcript_out,
)
from app.services.archive import CallArchive
from app.services.errors import InvalidUploadError
from app.services.media import media_type_for
from app.services.metadata import CallMetadata, normalize_direction, parse_timestamp
from app.services.watcher import MonitorWatcher

router = APIRouter()
_INDEX = Path(__file__).resolve().parents[1] / "static" / "index.html"


def watcher_label(settings: Settings, watcher: MonitorWatcher) -> str:
    """Report whether the spool thread is looping."""
    if not settings.watch_enabled or not settings.monitor_dir.strip():
        return "disabled"
    return "running" if watcher.running else "stopped"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _language(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    if len(cleaned) > 16:
        raise InvalidUploadError("Language must be a short code such as 'en'.")
    return cleaned.lower()


def _overrides(
    caller: str | None,
    callee: str | None,
    caller_name: str | None,
    uniqueid: str | None,
    direction: str | None,
    started_at: str | None,
) -> CallMetadata | None:
    direction_value = _clean(direction)
    if direction_value is not None and len(direction_value) > 32:
        raise InvalidUploadError("direction must be 32 characters or fewer.")
    started_raw = _clean(started_at)
    started = parse_timestamp(started_raw, strict=True) if started_raw else None
    fields = CallMetadata(
        caller=_clean(caller),
        callee=_clean(callee),
        caller_name=_clean(caller_name),
        uniqueid=_clean(uniqueid),
        direction=direction_value,
        started_at=started,
    )
    if all(
        value is None
        for value in (
            fields.caller,
            fields.callee,
            fields.caller_name,
            fields.uniqueid,
            fields.direction,
            fields.started_at,
        )
    ):
        return None
    return fields


async def _read_upload(file: UploadFile, settings: Settings) -> bytes:
    data = await file.read()
    if not data:
        raise InvalidUploadError("Upload is empty.")
    if len(data) > settings.max_upload_bytes:
        limit = settings.max_upload_bytes
        raise HTTPException(status_code=413, detail=f"Upload exceeds the {limit} byte limit.")
    return data


@router.get("/", response_model=ServiceInfo, tags=["Health"])
def root(
    settings: Settings = Depends(get_settings),
    archive: CallArchive = Depends(get_archive),
    watcher: MonitorWatcher = Depends(get_watcher),
) -> ServiceInfo:
    """Service name, active provider, and links to the docs and the UI."""
    return ServiceInfo(
        name=settings.app_name,
        version=__version__,
        status="ok",
        transcription_provider=settings.transcription_provider,
        watcher=watcher_label(settings, watcher),
        calls=archive.count(),
    )


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def health(
    settings: Settings = Depends(get_settings),
    archive: CallArchive = Depends(get_archive),
    watcher: MonitorWatcher = Depends(get_watcher),
) -> HealthResponse:
    """Liveness probe. Reports the provider, the watcher, and how many calls are stored."""
    return HealthResponse(
        status="ok",
        transcription_provider=settings.transcription_provider,
        watcher=watcher_label(settings, watcher),
        calls=archive.count(),
    )


@router.get("/ui", include_in_schema=False)
@router.get("/ui/", include_in_schema=False)
def ui() -> FileResponse:
    """Browser UI for browsing calls and playing audio with the transcript."""
    return FileResponse(_INDEX, media_type="text/html")


@router.post("/calls", response_model=CallDetail, status_code=201, tags=["Calls"])
async def create_call(
    file: UploadFile = File(..., description="WAV, MP3, GSM, or a .txt transcript."),
    caller: str | None = Form(default=None),
    callee: str | None = Form(default=None),
    caller_name: str | None = Form(default=None),
    uniqueid: str | None = Form(default=None),
    direction: str | None = Form(default=None),
    started_at: str | None = Form(default=None),
    language: str | None = Form(default=None),
    settings: Settings = Depends(get_settings),
    archive: CallArchive = Depends(get_archive),
) -> CallDetail:
    """Ingest one recording. Filename and CDR metadata fill any field you omit."""
    data = await _read_upload(file, settings)
    stored = archive.ingest_bytes(
        filename=file.filename or "upload.bin",
        data=data,
        source="upload",
        source_path=None,
        language=_language(language),
        overrides=_overrides(caller, callee, caller_name, uniqueid, direction, started_at),
    )
    return call_detail(stored)


@router.get("/calls", response_model=CallListResponse, tags=["Calls"])
def list_calls(
    caller: str | None = Query(default=None),
    callee: str | None = Query(default=None),
    uniqueid: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    archive: CallArchive = Depends(get_archive),
) -> CallListResponse:
    """List stored calls, newest start time first. ``q`` matches the transcript and the parties."""
    calls, total = archive.list_calls(
        caller=_clean(caller),
        callee=_clean(callee),
        uniqueid=_clean(uniqueid),
        direction=normalize_direction(_clean(direction)),
        query=_clean(q),
        limit=limit,
        offset=offset,
    )
    return CallListResponse(
        calls=[list_item(call) for call in calls],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/calls/{call_id}", response_model=CallDetail, tags=["Calls"])
def get_call(call_id: str, archive: CallArchive = Depends(get_archive)) -> CallDetail:
    """One call, including speaker segments and the summary."""
    return call_detail(archive.get(call_id))


@router.get("/calls/{call_id}/transcript", response_model=TranscriptResponse, tags=["Transcripts"])
def get_transcript(call_id: str, archive: CallArchive = Depends(get_archive)) -> TranscriptResponse:
    """The transcript, speaker segments, and summary for one call."""
    return transcript_out(archive.get(call_id))


@router.get("/calls/{call_id}/audio", tags=["Calls"])
def get_audio(call_id: str, archive: CallArchive = Depends(get_archive)) -> FileResponse:
    """Play or download the stored recording."""
    stored, path = archive.audio_file(call_id)
    return FileResponse(
        path,
        media_type=media_type_for(stored.filename),
        filename=stored.filename,
        content_disposition_type="inline",
    )


@router.delete("/calls/{call_id}", status_code=204, tags=["Calls"])
def delete_call(call_id: str, archive: CallArchive = Depends(get_archive)) -> None:
    """Delete the call, its segments, and the stored audio."""
    archive.delete(call_id)


@router.get("/search", response_model=SearchResponse, tags=["Search"])
def search_calls(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=200),
    archive: CallArchive = Depends(get_archive),
) -> SearchResponse:
    """Keyword search across the transcript, summary, parties, uniqueid, and filename."""
    hits = archive.search(q, limit=limit)
    return SearchResponse(query=q.strip(), results=[search_result(hit) for hit in hits])


@router.post("/cdr", response_model=CdrUploadResponse, tags=["Calls"])
async def upload_cdr(
    file: UploadFile = File(..., description="Asterisk Master.csv or a FreePBX CDR export."),
    settings: Settings = Depends(get_settings),
    archive: CallArchive = Depends(get_archive),
) -> CdrUploadResponse:
    """Replace the file at ``CDR_PATH``. Later ingests join on uniqueid."""
    if not settings.cdr_path.strip():
        raise HTTPException(status_code=400, detail="CDR_PATH is not set. The CSV was not stored.")
    data = await _read_upload(file, settings)
    path = Path(settings.cdr_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return CdrUploadResponse(rows=archive.reload_cdr())
