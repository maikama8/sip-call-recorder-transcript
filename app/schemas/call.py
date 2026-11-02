"""Response models for calls, transcripts, and search."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.db.records import SearchHit, StoredCall, StoredSegment


class SegmentOut(BaseModel):
    speaker: str
    start: float
    end: float
    text: str


class CallListItem(BaseModel):
    id: str
    uniqueid: str | None
    caller: str | None
    callee: str | None
    caller_name: str | None
    direction: str | None
    started_at: datetime | None
    duration_seconds: float | None
    disposition: str | None
    filename: str
    source: str
    summary: str
    created_at: datetime
    playable: bool


class CallDetail(CallListItem):
    linkedid: str | None
    dcontext: str | None
    answered_at: datetime | None
    ended_at: datetime | None
    billsec: float | None
    status: str
    language: str | None
    provider: str
    notice: str | None
    audio_url: str | None
    segments: list[SegmentOut]


class CallListResponse(BaseModel):
    calls: list[CallListItem]
    total: int
    limit: int
    offset: int


class SearchResult(CallListItem):
    snippet: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class TranscriptResponse(BaseModel):
    call_id: str
    language: str | None
    provider: str
    summary: str
    text: str
    notice: str | None
    segments: list[SegmentOut]


class ServiceInfo(BaseModel):
    name: str
    version: str
    status: str
    transcription_provider: str
    watcher: str
    calls: int
    docs: str = "/docs"
    ui: str = "/ui"


class HealthResponse(BaseModel):
    status: str
    transcription_provider: str
    watcher: str
    calls: int


class CdrUploadResponse(BaseModel):
    rows: int = Field(description="Uniqueids loaded from the CSV.")


def _segment(segment: StoredSegment) -> SegmentOut:
    return SegmentOut(
        speaker=segment.speaker,
        start=segment.start,
        end=segment.end,
        text=segment.text,
    )


def list_item(call: StoredCall) -> CallListItem:
    return CallListItem(
        id=call.id,
        uniqueid=call.uniqueid,
        caller=call.caller,
        callee=call.callee,
        caller_name=call.caller_name,
        direction=call.direction,
        started_at=call.started_at,
        duration_seconds=call.duration_seconds,
        disposition=call.disposition,
        filename=call.filename,
        source=call.source,
        summary=call.summary,
        created_at=call.created_at,
        playable=call.playable,
    )


def call_detail(call: StoredCall) -> CallDetail:
    item = list_item(call)
    return CallDetail(
        **item.model_dump(),
        linkedid=call.linkedid,
        dcontext=call.dcontext,
        answered_at=call.answered_at,
        ended_at=call.ended_at,
        billsec=call.billsec,
        status=call.status,
        language=call.language,
        provider=call.provider,
        notice=call.notice,
        audio_url=f"/calls/{call.id}/audio" if call.audio_path else None,
        segments=[_segment(segment) for segment in call.segments],
    )


def search_result(hit: SearchHit) -> SearchResult:
    item = list_item(hit.call)
    return SearchResult(**item.model_dump(), snippet=hit.snippet)


def transcript_out(call: StoredCall) -> TranscriptResponse:
    return TranscriptResponse(
        call_id=call.id,
        language=call.language,
        provider=call.provider,
        summary=call.summary,
        text=call.transcript_text,
        notice=call.notice,
        segments=[_segment(segment) for segment in call.segments],
    )
