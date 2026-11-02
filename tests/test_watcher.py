"""Monitor directory watcher."""

import os
import time
from pathlib import Path

from app.runtime import close_runtime, open_runtime
from app.services.errors import ProviderError
from tests.conftest import build_settings, wav_bytes

INTERNAL = "internal-102-100-20250116-102939-1737016179.6.wav"


def _runtime(tmp_path: Path, **overrides: object):
    settings = build_settings(tmp_path, **overrides)
    return open_runtime(settings)


def test_scan_ingests_a_freepbx_dated_directory_once(tmp_path: Path) -> None:
    monitor = tmp_path / "spool"
    day = monitor / "2026" / "11" / "02"
    day.mkdir(parents=True)
    (day / INTERNAL).write_bytes(wav_bytes())
    (day / "notes.txt").write_text("ignore me")
    (day / ".hidden.wav").write_bytes(wav_bytes())
    (day / "empty.wav").write_bytes(b"")

    runtime = _runtime(tmp_path, monitor_dir=str(monitor), watch_settle_seconds=0)
    try:
        ids = runtime.watcher.scan_once()
        assert len(ids) == 1
        call = runtime.archive.get(ids[0])
        assert call.caller == "100"
        assert call.callee == "102"
        assert call.direction == "internal"
        assert call.source == "watcher"
        assert call.summary.startswith("Recorded call from 100 to 102 (internal).")
        assert runtime.watcher.scan_once() == []
        assert runtime.archive.count() == 1
    finally:
        close_runtime(runtime)


def test_fresh_file_waits_for_the_settle_window(tmp_path: Path) -> None:
    monitor = tmp_path / "spool"
    monitor.mkdir()
    target = monitor / INTERNAL
    target.write_bytes(wav_bytes())
    runtime = _runtime(tmp_path, monitor_dir=str(monitor), watch_settle_seconds=60)
    try:
        assert runtime.watcher.scan_once() == []
        os.utime(target, (time.time() - 120, time.time() - 120))
        ids = runtime.watcher.scan_once()
        assert len(ids) == 1
    finally:
        close_runtime(runtime)


def test_cdr_fills_a_uniqueid_filename(tmp_path: Path) -> None:
    monitor = tmp_path / "spool"
    monitor.mkdir()
    (monitor / "1730554215.23.wav").write_bytes(wav_bytes())
    cdr = tmp_path / "Master.csv"
    cdr.write_text(
        "uniqueid,src,dst,dcontext,disposition,billsec,start\n"
        "1730554215.23,1001,200,from-internal,ANSWERED,142,2026-11-02 14:30:15\n",
        encoding="utf-8",
    )
    runtime = _runtime(
        tmp_path,
        monitor_dir=str(monitor),
        cdr_path=str(cdr),
        watch_settle_seconds=0,
    )
    try:
        ids = runtime.watcher.scan_once()
        call = runtime.archive.get(ids[0])
        assert call.caller == "1001"
        assert call.callee == "200"
        assert call.direction == "internal"
        assert call.disposition == "ANSWERED"
        assert call.duration_seconds == 142
        assert call.started_at is not None
        assert call.started_at.isoformat(timespec="seconds") == "2026-11-02T14:30:15"
    finally:
        close_runtime(runtime)


def test_copies_inside_the_recordings_directory_are_not_ingested_again(tmp_path: Path) -> None:
    monitor = tmp_path / "spool"
    recordings = monitor / "archive"
    recordings.mkdir(parents=True)
    (monitor / INTERNAL).write_bytes(wav_bytes())
    (recordings / "already.wav").write_bytes(wav_bytes())
    runtime = _runtime(
        tmp_path,
        monitor_dir=str(monitor),
        recordings_dir=str(recordings),
        watch_settle_seconds=0,
    )
    try:
        ids = runtime.watcher.scan_once()
        assert len(ids) == 1
        assert runtime.archive.count() == 1
    finally:
        close_runtime(runtime)


def test_a_poison_file_is_abandoned_after_three_failures(tmp_path: Path) -> None:
    monitor = tmp_path / "spool"
    monitor.mkdir()
    (monitor / INTERNAL).write_bytes(wav_bytes())

    class Boom:
        name = "fake"

        def __init__(self) -> None:
            self.calls = 0

        def transcribe(self, filename: str, data: bytes, language: str | None) -> None:
            del filename, data, language
            self.calls += 1
            raise ProviderError("nope")

    provider = Boom()
    settings = build_settings(tmp_path, monitor_dir=str(monitor), watch_settle_seconds=0)
    runtime = open_runtime(settings, provider)
    try:
        for _ in range(3):
            assert runtime.watcher.scan_once() == []
        assert provider.calls == 3
        assert runtime.watcher.scan_once() == []
        assert provider.calls == 3
        assert runtime.archive.count() == 0
    finally:
        close_runtime(runtime)
