"""File types this service will store and play."""

from pathlib import Path

AUDIO_SUFFIXES = {".wav", ".mp3", ".gsm", ".ogg", ".flac", ".ulaw", ".alaw"}
TEXT_SUFFIXES = {".txt"}

_MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".gsm": "audio/x-gsm",
    ".ulaw": "audio/basic",
    ".alaw": "audio/basic",
    ".txt": "text/plain; charset=utf-8",
}


def suffix_of(filename: str) -> str:
    """Return the lower-case suffix, including the dot."""
    return Path(filename).suffix.lower()


def is_audio(filename: str) -> bool:
    """True for the audio types MixMonitor and FreePBX actually write."""
    return suffix_of(filename) in AUDIO_SUFFIXES


def is_accepted_upload(filename: str) -> bool:
    """True for audio or a plain-text transcript."""
    return suffix_of(filename) in AUDIO_SUFFIXES | TEXT_SUFFIXES


def media_type_for(filename: str) -> str:
    """Content type used when the browser plays or downloads a stored file."""
    return _MEDIA_TYPES.get(suffix_of(filename), "application/octet-stream")
