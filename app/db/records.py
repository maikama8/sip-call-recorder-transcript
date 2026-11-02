"""Plain call records detached from the database session."""

from dataclasses import dataclass
from datetime import datetime

from app.services.media import is_audio


@dataclass(frozen=True)
class StoredSegment:
    speaker: str
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class StoredCall:
    id: str
    uniqueid: str | None
    linkedid: str | None
    caller: str | None
    callee: str | None
    caller_name: str | None
    direction: str | None
    dcontext: str | None
    started_at: datetime | None
    answered_at: datetime | None
    ended_at: datetime | None
    duration_seconds: float | None
    billsec: float | None
    disposition: str | None
    filename: str
    source: str
    source_path: str | None
    audio_path: str | None
    language: str | None
    summary: str
    transcript_text: str
    provider: str
    notice: str | None
    status: str
    created_at: datetime
    segments: tuple[StoredSegment, ...]

    @property
    def playable(self) -> bool:
        return bool(self.audio_path) and is_audio(self.filename)


@dataclass(frozen=True)
class SearchHit:
    call: StoredCall
    snippet: str
