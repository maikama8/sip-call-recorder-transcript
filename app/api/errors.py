"""Map archive and provider failures onto HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.errors import (
    CallNotFoundError,
    DuplicateCallError,
    InvalidUploadError,
    ProviderConfigError,
    ProviderError,
    UnsupportedMediaError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProviderConfigError)
    async def provider_config_error(_request: Request, exc: ProviderConfigError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def provider_error(_request: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(InvalidUploadError)
    async def invalid_upload(_request: Request, exc: InvalidUploadError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(UnsupportedMediaError)
    async def unsupported_media(_request: Request, exc: UnsupportedMediaError) -> JSONResponse:
        return JSONResponse(status_code=415, content={"detail": str(exc)})

    @app.exception_handler(DuplicateCallError)
    async def duplicate_call(_request: Request, _exc: DuplicateCallError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": "This recording was already ingested."},
        )

    @app.exception_handler(CallNotFoundError)
    async def missing_call(_request: Request, _exc: CallNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Call not found."})
