"""Offline transcription provider.

Text uploads are split on speaker labels. Audio uploads receive the bundled
sample call so the archive, the search, and the UI run with no model and no
API key. The notice on the call says so.
"""

from pathlib import Path

from app.services.media import is_audio
from app.services.models import Transcript
from app.services.speakers import join_segments, parse_labelled_transcript

_SAMPLE_PATH = Path(__file__).resolve().parents[2] / "samples" / "sample_call.txt"

_AUDIO_NOTICE = (
    "Fake transcription provider does not decode audio. It returned the bundled "
    "sample call so the archive can be browsed offline. Set TRANSCRIPTION_PROVIDER "
    "to 'openai' or 'faster_whisper' to transcribe this file."
)
_TEXT_NOTICE = "Speaker lines were read from the text file. No speech-to-text model was called."


def load_sample_call() -> str:
    """Return the bundled call transcript shipped with the app."""
    return _SAMPLE_PATH.read_text(encoding="utf-8").strip()


def _looks_like_text(data: bytes) -> bool:
    if not data or b"\x00" in data:
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    printable = sum(character.isprintable() or character.isspace() for character in text)
    return printable / len(text) >= 0.95


class FakeTranscriptionProvider:
    """Deterministic transcription used when no external provider is configured."""

    name = "fake"

    def transcribe(self, filename: str, data: bytes, language: str | None) -> Transcript:
        selected = language or "en"
        if is_audio(filename) or not _looks_like_text(data):
            segments = parse_labelled_transcript(load_sample_call())
            notice = _AUDIO_NOTICE
        else:
            text = data.decode("utf-8-sig", errors="replace").strip()
            segments = parse_labelled_transcript(text)
            notice = _TEXT_NOTICE
        joined = join_segments(segments)
        duration = segments[-1].end if segments else None
        return Transcript(
            text=joined,
            language=selected,
            provider=self.name,
            segments=segments,
            duration_seconds=duration,
            notice=notice,
        )
