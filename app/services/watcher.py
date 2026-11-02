"""Poll an Asterisk/FreePBX monitor directory for closed recordings.

MixMonitor creates the file when the call starts and keeps writing until the
channel hangs up (or ``StopMixMonitor`` runs). A file is ready once it is
non-empty and its mtime is at least ``settle_seconds`` old. FreePBX stores
files under ``YYYY/MM/DD/``, so the scan is recursive.

The original file stays in the spool. A copy is what the archive plays back,
so a later FreePBX cleanup does not remove the transcript's audio.
"""

import logging
import threading
import time
from pathlib import Path

from app.services.archive import CallArchive
from app.services.errors import DuplicateCallError
from app.services.media import is_audio

logger = logging.getLogger(__name__)

_MAX_FAILURES = 3


class MonitorWatcher:
    """Scan ``monitor_dir`` on a timer, or once when ``scan_once`` is called."""

    def __init__(
        self,
        archive: CallArchive,
        monitor_dir: Path | None,
        *,
        settle_seconds: float,
        interval_seconds: float,
    ) -> None:
        self._archive = archive
        self._monitor_dir = monitor_dir
        self._settle = settle_seconds
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failures: dict[str, int] = {}

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="monitor-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=self._interval + 2)
        self._thread = None

    def scan_once(self) -> list[str]:
        """Ingest every closed recording that is not already stored. Returns new ids."""
        if self._monitor_dir is None or not self._monitor_dir.is_dir():
            return []
        ingested: list[str] = []
        root = self._monitor_dir.resolve()
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            if not is_audio(path.name):
                continue
            if self._inside_recordings(path):
                continue
            key = str(path.resolve())
            if self._failures.get(key, 0) >= _MAX_FAILURES:
                continue
            if not self._ready(path):
                continue
            try:
                stored = self._archive.ingest_path(path, source="watcher")
            except DuplicateCallError:
                continue
            except Exception:
                logger.exception("failed to ingest %s", path)
                self._failures[key] = self._failures.get(key, 0) + 1
                continue
            ingested.append(stored.id)
        return ingested

    def _ready(self, path: Path) -> bool:
        stat = path.stat()
        if stat.st_size <= 0:
            return False
        if self._settle <= 0:
            return True
        return (time.time() - stat.st_mtime) >= self._settle

    def _inside_recordings(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._archive.recordings_dir.resolve())
        except ValueError:
            return False
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception:
                logger.exception("monitor scan failed")
            self._stop.wait(self._interval)
