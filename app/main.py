"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.routes import router
from app.config import Settings, get_settings
from app.runtime import close_runtime, open_runtime
from app.services.factory import build_transcription_provider


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API. The database opens when the process starts, not at import."""
    resolved = settings or get_settings()
    provider = build_transcription_provider(resolved)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = open_runtime(resolved, provider)
        app.state.archive = runtime.archive
        app.state.watcher = runtime.watcher
        app.state.engine = runtime.engine
        if resolved.watch_enabled and resolved.monitor_dir.strip():
            runtime.watcher.start()
        try:
            yield
        finally:
            close_runtime(runtime)

    app = FastAPI(
        title="SIP Call Recorder",
        version=__version__,
        summary="Ingest Asterisk and FreePBX recordings, then store a speaker-labelled transcript.",
        description=(
            "Upload a WAV or MP3, or point the watcher at an Asterisk monitor spool. "
            "Caller, callee, uniqueid, and timestamps are read from the MixMonitor filename "
            "and from an Asterisk CDR CSV. The default transcription provider runs offline. "
            "OpenAI Whisper and faster-whisper are selected with environment variables. "
            "Record calls only when you have a lawful basis to do so."
        ),
        contact={"name": "Abdulrasheed Oseni", "url": "https://github.com/maikama8"},
        license_info={"name": "MIT"},
        lifespan=lifespan,
    )
    app.state.settings = resolved
    register_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
