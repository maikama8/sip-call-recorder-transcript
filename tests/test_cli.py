"""Command line archive access."""

from pathlib import Path

import pytest

from app.cli import run
from tests.conftest import build_settings, wav_bytes

DIALPLAN = "20261102-143015-1730554215.23-1001-200.wav"


def test_ingest_search_and_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    recording = tmp_path / DIALPLAN
    recording.write_bytes(wav_bytes())
    settings = build_settings(tmp_path)

    assert run(settings, ["ingest", str(recording)]) == 0
    assert run(settings, ["search", "invoice 1842"]) == 0
    assert run(settings, ["calls"]) == 0

    output = capsys.readouterr().out
    assert "1001" in output
    assert "invoice 1842" in output
    assert '"total": 1' in output


def test_missing_file_is_an_error(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    assert run(settings, ["ingest", str(tmp_path / "missing.wav")]) == 1


def test_watch_once_on_an_empty_spool(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monitor = tmp_path / "spool"
    monitor.mkdir()
    settings = build_settings(tmp_path, monitor_dir=str(monitor), watch_settle_seconds=0)
    assert run(settings, ["watch-once"]) == 0
    assert '"ingested": []' in capsys.readouterr().out


def test_help_exits_cleanly(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as caught:
        run(build_settings(tmp_path), ["--help"])
    assert caught.value.code == 0
