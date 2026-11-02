"""Queries over stored calls."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import CallRow, SegmentRow
from app.db.records import SearchHit, StoredCall, StoredSegment
from app.services.errors import DuplicateCallError


def utcnow() -> datetime:
    """Naive UTC timestamp for ``created_at``. Call times stay on the PBX clock."""
    return datetime.now(UTC).replace(tzinfo=None)


class CallRepository:
    """Persist and query calls. The caller owns the transaction."""

    def insert(
        self,
        session: Session,
        *,
        call_id: str,
        filename: str,
        source: str,
        source_path: str | None,
        audio_path: str | None,
        language: str | None,
        summary: str,
        transcript_text: str,
        provider: str,
        notice: str | None,
        uniqueid: str | None,
        linkedid: str | None,
        caller: str | None,
        callee: str | None,
        caller_name: str | None,
        direction: str | None,
        dcontext: str | None,
        started_at: datetime | None,
        answered_at: datetime | None,
        ended_at: datetime | None,
        duration_seconds: float | None,
        billsec: float | None,
        disposition: str | None,
        segments: tuple[StoredSegment, ...],
    ) -> StoredCall:
        row = CallRow(
            id=call_id,
            uniqueid=uniqueid,
            linkedid=linkedid,
            caller=caller,
            callee=callee,
            caller_name=caller_name,
            direction=direction,
            dcontext=dcontext,
            started_at=started_at,
            answered_at=answered_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            billsec=billsec,
            disposition=disposition,
            filename=filename,
            source=source,
            source_path=source_path,
            audio_path=audio_path,
            language=language,
            summary=summary,
            transcript_text=transcript_text,
            provider=provider,
            notice=notice,
            status="transcribed",
            created_at=utcnow(),
            segments=[
                SegmentRow(
                    position=index,
                    speaker=segment.speaker,
                    start_seconds=segment.start,
                    end_seconds=segment.end,
                    text=segment.text,
                )
                for index, segment in enumerate(segments)
            ],
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise DuplicateCallError(source_path or call_id) from exc
        return _stored(row)

    def get(self, session: Session, call_id: str) -> StoredCall | None:
        row = session.get(CallRow, call_id)
        if row is None:
            return None
        return _stored(row)

    def get_by_source_path(self, session: Session, source_path: str) -> StoredCall | None:
        stmt = select(CallRow).where(CallRow.source_path == source_path)
        row = session.scalars(stmt).first()
        if row is None:
            return None
        return _stored(row)

    def count(self, session: Session) -> int:
        return int(session.scalar(select(func.count()).select_from(CallRow)) or 0)

    def delete(self, session: Session, call_id: str) -> StoredCall | None:
        row = session.get(CallRow, call_id)
        if row is None:
            return None
        stored = _stored(row)
        session.delete(row)
        session.flush()
        return stored

    def list_calls(
        self,
        session: Session,
        *,
        caller: str | None,
        callee: str | None,
        uniqueid: str | None,
        direction: str | None,
        query: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[StoredCall], int]:
        conditions = _filters(
            caller=caller,
            callee=callee,
            uniqueid=uniqueid,
            direction=direction,
            query=query,
        )
        total = int(
            session.scalar(select(func.count()).select_from(CallRow).where(*conditions)) or 0
        )
        stmt = (
            select(CallRow)
            .where(*conditions)
            .order_by(CallRow.started_at.desc(), CallRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_stored(row) for row in session.scalars(stmt).all()], total

    def search(self, session: Session, query: str, *, limit: int) -> list[SearchHit]:
        calls, _total = self.list_calls(
            session,
            caller=None,
            callee=None,
            uniqueid=None,
            direction=None,
            query=query,
            limit=limit,
            offset=0,
        )
        return [SearchHit(call=call, snippet=_snippet(call, query)) for call in calls]


def _filters(
    *,
    caller: str | None,
    callee: str | None,
    uniqueid: str | None,
    direction: str | None,
    query: str | None,
) -> list[Any]:
    conditions: list[Any] = []
    if caller:
        conditions.append(_contains(CallRow.caller, caller))
    if callee:
        conditions.append(_contains(CallRow.callee, callee))
    if uniqueid:
        conditions.append(CallRow.uniqueid == uniqueid)
    if direction:
        conditions.append(CallRow.direction == direction)
    if query:
        conditions.append(
            or_(
                _contains(CallRow.transcript_text, query),
                _contains(CallRow.summary, query),
                _contains(CallRow.caller, query),
                _contains(CallRow.callee, query),
                _contains(CallRow.caller_name, query),
                _contains(CallRow.uniqueid, query),
                _contains(CallRow.filename, query),
            )
        )
    return conditions


def _contains(column: Any, query: str) -> Any:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def _stored(row: CallRow) -> StoredCall:
    return StoredCall(
        id=row.id,
        uniqueid=row.uniqueid,
        linkedid=row.linkedid,
        caller=row.caller,
        callee=row.callee,
        caller_name=row.caller_name,
        direction=row.direction,
        dcontext=row.dcontext,
        started_at=row.started_at,
        answered_at=row.answered_at,
        ended_at=row.ended_at,
        duration_seconds=row.duration_seconds,
        billsec=row.billsec,
        disposition=row.disposition,
        filename=row.filename,
        source=row.source,
        source_path=row.source_path,
        audio_path=row.audio_path,
        language=row.language,
        summary=row.summary,
        transcript_text=row.transcript_text,
        provider=row.provider,
        notice=row.notice,
        status=row.status,
        created_at=row.created_at,
        segments=tuple(
            StoredSegment(
                speaker=segment.speaker,
                start=segment.start_seconds,
                end=segment.end_seconds,
                text=segment.text,
            )
            for segment in row.segments
        ),
    )


def _snippet(call: StoredCall, query: str, window: int = 80) -> str:
    party = " ".join(
        part
        for part in (call.caller_name, call.caller, call.callee, call.uniqueid, call.filename)
        if part
    )
    for source in (call.transcript_text, call.summary, party):
        if query.lower() in source.lower():
            return _window(source, query, window)
    return _window(call.summary or call.transcript_text, query, window)


def _window(text: str, query: str, window: int) -> str:
    index = text.lower().find(query.lower())
    if index < 0:
        piece = text[: window * 2].strip()
        return piece
    start = max(0, index - window)
    end = min(len(text), index + len(query) + window)
    piece = text[start:end].strip()
    if start > 0:
        piece = f"…{piece}"
    if end < len(text):
        piece = f"{piece}…"
    return piece
