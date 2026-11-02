"""Shared test fixtures."""

import struct
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def wav_bytes(frames: int = 80) -> bytes:
    """A tiny valid PCM WAV. The fake provider does not decode it."""
    payload = b"\x00\x00" * frames
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(payload),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        8000,
        16000,
        2,
        16,
        b"data",
        len(payload),
    )
    return header + payload


def build_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "transcription_provider": "fake",
        "openai_api_key": None,
        "database_url": f"sqlite:///{tmp_path / 'calls.db'}",
        "recordings_dir": str(tmp_path / "recordings"),
        "monitor_dir": "",
        "cdr_path": "",
        "watch_enabled": False,
        "watch_settle_seconds": 0,
        "max_upload_bytes": 25 * 1024 * 1024,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return build_settings(tmp_path)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
