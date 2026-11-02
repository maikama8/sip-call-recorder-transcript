"""OpenAI Audio transcription API.

Selected with ``TRANSCRIPTION_PROVIDER=openai``. Uses the REST API so the base
install does not depend on the OpenAI SDK. Whisper does not identify speakers,
so every segment is labelled ``unknown``.
"""

from pathlib import Path

import httpx

from app.services.errors import ProviderError
from app.services.models import Segment, Transcript


class OpenAITranscriptionProvider:
    """Transcribe audio with OpenAI's ``/audio/transcriptions`` endpoint."""

    name = "openai"

    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: float) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def transcribe(self, filename: str, data: bytes, language: str | None) -> Transcript:
        form = {"model": self._model, "response_format": "verbose_json"}
        if language:
            form["language"] = language
        safe_name = Path(filename).name or "audio.bin"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    data=form,
                    files={"file": (safe_name, data, "application/octet-stream")},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise ProviderError(
                f"OpenAI transcription failed ({exc.response.status_code}): {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("OpenAI transcription request failed.") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("OpenAI transcription returned a non-JSON response.") from exc
        if not isinstance(payload, dict):
            raise ProviderError("OpenAI transcription returned an unexpected payload.")

        duration = _number(payload.get("duration"))
        segments = _segments(payload, duration)
        text = str(payload.get("text") or "").strip() or " ".join(
            segment.text for segment in segments
        )
        if not text:
            raise ProviderError("OpenAI transcription returned an empty transcript.")
        detected = payload.get("language") or language or "en"
        return Transcript(
            text=text,
            language=str(detected),
            provider=self.name,
            segments=segments,
            duration_seconds=duration,
        )


def _segments(payload: dict[str, object], duration: float | None) -> tuple[Segment, ...]:
    raw_segments = payload.get("segments")
    segments: list[Segment] = []
    if isinstance(raw_segments, list):
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            start = _number(item.get("start")) or 0.0
            end = _number(item.get("end"))
            segments.append(
                Segment(
                    speaker="unknown",
                    start=start,
                    end=end if end is not None else start,
                    text=text,
                )
            )
    if segments:
        return tuple(segments)
    text = str(payload.get("text") or "").strip()
    if not text:
        return ()
    end = duration if duration is not None else 0.0
    return (Segment(speaker="unknown", start=0.0, end=end, text=text),)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
