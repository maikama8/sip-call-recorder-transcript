"""Local faster-whisper transcription.

Selected with ``TRANSCRIPTION_PROVIDER=faster_whisper``. The package is
optional and is imported only when this provider is constructed. Segments
are labelled ``unknown`` because faster-whisper does not diarize.
"""

import os
import tempfile
import threading
from collections.abc import Iterable
from pathlib import Path

from app.services.errors import ProviderConfigError, ProviderError
from app.services.models import Segment, Transcript


class FasterWhisperTranscriptionProvider:
    """Transcribe audio on this machine with faster-whisper."""

    name = "faster_whisper"

    def __init__(self, *, model_size: str, device: str, compute_type: str) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ProviderConfigError(
                "faster-whisper is not installed. Install it with "
                "`pip install faster-whisper` and set TRANSCRIPTION_PROVIDER=faster_whisper."
            ) from exc
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._lock = threading.Lock()

    def transcribe(self, filename: str, data: bytes, language: str | None) -> Transcript:
        suffix = Path(filename).suffix or ".wav"
        descriptor, path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
            with self._lock:
                raw_segments, info = self._model.transcribe(path, language=language)
                segments = _collect(raw_segments)
                duration = getattr(info, "duration", None)
                detected = getattr(info, "language", None) or language or "en"
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"faster-whisper failed to transcribe the upload: {exc}") from exc
        finally:
            os.unlink(path)

        text = " ".join(segment.text for segment in segments).strip()
        if not text:
            raise ProviderError("faster-whisper returned an empty transcript.")
        duration_seconds = float(duration) if isinstance(duration, int | float) else None
        return Transcript(
            text=text,
            language=str(detected),
            provider=self.name,
            segments=segments,
            duration_seconds=duration_seconds,
        )


def _collect(raw_segments: Iterable[object]) -> tuple[Segment, ...]:
    segments: list[Segment] = []
    for item in raw_segments:
        text = str(getattr(item, "text", "") or "").strip()
        if not text:
            continue
        start = float(getattr(item, "start", 0.0) or 0.0)
        end = float(getattr(item, "end", start) or start)
        segments.append(Segment(speaker="unknown", start=start, end=end, text=text))
    return tuple(segments)
