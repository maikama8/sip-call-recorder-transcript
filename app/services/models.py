"""Results returned by a transcription provider."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    """One speaker turn in a transcript."""

    speaker: str
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcript:
    """A transcript and the segments it was built from."""

    text: str
    language: str
    provider: str
    segments: tuple[Segment, ...]
    duration_seconds: float | None = None
    notice: str | None = None
