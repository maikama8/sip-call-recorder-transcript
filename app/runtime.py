"""Build the archive and the watcher from settings."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from app.config import Settings
from app.db.session import make_session_factory
from app.services.archive import CallArchive
from app.services.factory import build_transcription_provider
from app.services.metadata import CdrSource
from app.services.transcription.base import TranscriptionProvider
from app.services.watcher import MonitorWatcher


@dataclass
class Runtime:
    engine: Engine
    archive: CallArchive
    watcher: MonitorWatcher
    settings: Settings


def open_runtime(
    settings: Settings,
    provider: TranscriptionProvider | None = None,
) -> Runtime:
    """Open the database and wire the archive. Does not start the watcher thread."""
    resolved = provider or build_transcription_provider(settings)
    factory, engine = make_session_factory(settings.database_url)
    recordings = Path(settings.recordings_dir).expanduser()
    recordings.mkdir(parents=True, exist_ok=True)
    cdr_path = Path(settings.cdr_path).expanduser() if settings.cdr_path.strip() else None
    monitor = Path(settings.monitor_dir).expanduser() if settings.monitor_dir.strip() else None
    archive = CallArchive(
        factory,
        recordings,
        CdrSource(cdr_path),
        resolved,
        max_upload_bytes=settings.max_upload_bytes,
        default_language=settings.default_language,
    )
    watcher = MonitorWatcher(
        archive,
        monitor,
        settle_seconds=settings.watch_settle_seconds,
        interval_seconds=settings.watch_interval_seconds,
    )
    return Runtime(engine=engine, archive=archive, watcher=watcher, settings=settings)


def close_runtime(runtime: Runtime) -> None:
    runtime.watcher.stop()
    runtime.engine.dispose()
