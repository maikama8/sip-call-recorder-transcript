"""Transcription provider interface."""

from typing import Protocol

from app.services.models import Transcript


class TranscriptionProvider(Protocol):
    """Turn recording bytes into speaker-labelled segments."""

    name: str

    def transcribe(self, filename: str, data: bytes, language: str | None) -> Transcript:
        """Transcribe ``data``, described by ``filename``."""
