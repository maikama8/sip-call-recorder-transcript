"""Command line access to the same archive as the API.

Examples::

    python -m app.cli ingest recording.wav
    python -m app.cli search "invoice 1842"
    python -m app.cli calls
    python -m app.cli watch-once
"""

import argparse
import json
import sys
from pathlib import Path

from app.config import Settings, get_settings
from app.db.records import StoredCall
from app.runtime import Runtime, close_runtime, open_runtime
from app.services.errors import (
    DuplicateCallError,
    InvalidUploadError,
    ProviderConfigError,
    ProviderError,
    UnsupportedMediaError,
)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Reads settings from the environment and an optional ``.env``."""
    get_settings.cache_clear()
    return run(get_settings(), argv)


def run(settings: Settings, argv: list[str] | None = None) -> int:
    """Run one command against ``settings`` and return a process status."""
    parser = _parser()
    args = parser.parse_args(argv)
    runtime = open_runtime(settings)
    try:
        return _dispatch(runtime, args)
    finally:
        close_runtime(runtime)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Ingest Asterisk recordings and search their transcripts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Transcribe one recording and store it.")
    ingest.add_argument("path", type=Path)
    search = sub.add_parser("search", help="Search stored transcripts.")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    calls = sub.add_parser("calls", help="List stored calls.")
    calls.add_argument("--limit", type=int, default=20)
    sub.add_parser("watch-once", help="Scan MONITOR_DIR a single time.")
    return parser


def _dispatch(runtime: Runtime, args: argparse.Namespace) -> int:
    try:
        if args.command == "ingest":
            return _ingest(runtime, args.path)
        if args.command == "search":
            hits = runtime.archive.search(args.query, limit=args.limit)
            payload = [{"snippet": hit.snippet, **_brief(hit.call)} for hit in hits]
            _print(payload)
            return 0
        if args.command == "calls":
            calls, total = runtime.archive.list_calls(limit=args.limit)
            _print({"total": total, "calls": [_brief(call) for call in calls]})
            return 0
        if args.command == "watch-once":
            ids = runtime.watcher.scan_once()
            _print({"ingested": ids})
            return 0
    except (
        InvalidUploadError,
        UnsupportedMediaError,
        DuplicateCallError,
        ProviderError,
        ProviderConfigError,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1


def _ingest(runtime: Runtime, path: Path) -> int:
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    stored = runtime.archive.ingest_path(path, source="upload")
    _print(_brief(stored))
    return 0


def _brief(call: StoredCall) -> dict[str, object]:
    return {
        "id": call.id,
        "uniqueid": call.uniqueid,
        "caller": call.caller,
        "callee": call.callee,
        "direction": call.direction,
        "started_at": call.started_at.isoformat(timespec="seconds") if call.started_at else None,
        "summary": call.summary,
        "filename": call.filename,
    }


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
