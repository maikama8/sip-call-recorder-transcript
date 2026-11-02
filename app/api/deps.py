"""Request dependencies."""

from fastapi import Request

from app.config import Settings
from app.services.archive import CallArchive
from app.services.watcher import MonitorWatcher


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_archive(request: Request) -> CallArchive:
    return request.app.state.archive


def get_watcher(request: Request) -> MonitorWatcher:
    return request.app.state.watcher
