"""Call metadata from MixMonitor filenames and Asterisk CDR exports.

Two filename shapes are recognized.

FreePBX ``sub-record-check`` writes this under
``/var/spool/asterisk/monitor/YYYY/MM/DD/``::

    {type}-{destination}-{source}-{YYYYMMDD}-{HHMMSS}-{UNIQUEID}.wav
    internal-102-100-20250116-102939-1737016179.6.wav

That is type, destination, source, date, time, uniqueid. ``internal-102-100``
is a call to extension 102 from extension 100.

The dialplan in ``examples/extensions_custom.conf`` names the parties in
order, which is easier to read when you control the dialplan::

    {YYYYMMDD}-{HHMMSS}-{UNIQUEID}-{caller}-{callee}.wav
    20261102-143015-1730554215.23-1001-200.wav

``UNIQUEID`` is ``{epoch}.{sequence}``. When ``systemname`` is set in
``asterisk.conf`` it becomes ``{systemname}-{epoch}.{sequence}``. The
system name is assumed to be letters and digits.

A file that is only the uniqueid (``1730554215.23.wav``) is filled in from
the CDR when a row with that uniqueid exists.

Timestamps are stored as the PBX clock, with no timezone. Asterisk CDR CSV
and FreePBX ``calldate`` do not carry a zone.
"""

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.services.errors import InvalidUploadError

_UNIQUEID_BODY = r"(?:[A-Za-z0-9]+-)?\d+\.\d+"
_UNIQUEID_RE = re.compile(rf"{_UNIQUEID_BODY}\Z")
_DATE_RE = re.compile(r"\d{8}\Z")
_TIME_RE = re.compile(r"\d{6}\Z")
_PARTY_RE = re.compile(r"[0-9A-Za-z*#+]+\Z")
# The destination is every token between the call type and the source, rejoined,
# so a dialed number such as 1-800-555-0100 survives. The source is one token.
_DEST_RE = re.compile(r"[0-9A-Za-z*#+]+(?:-[0-9A-Za-z*#+]+)*\Z")
_CLID_RE = re.compile(r'^(?:"(?P<quoted>[^"]+)"|(?P<plain>[^"<]+?))?\s*<(?P<number>[^>]+)>\s*$')

# FreePBX call-type token -> the direction stored on the call.
# Unknown tokens are kept as-is so a newer type is not thrown away.
_TYPE_DIRECTION = {
    "in": "inbound",
    "inbound": "inbound",
    "external": "inbound",
    "out": "outbound",
    "outbound": "outbound",
    "internal": "internal",
    "ext": "internal",
    "exten": "internal",
    "rg": "ringgroup",
    "ringgroup": "ringgroup",
    "q": "queue",
    "queue": "queue",
}

_CDR_COLUMNS = (
    "accountcode",
    "src",
    "dst",
    "dcontext",
    "clid",
    "channel",
    "dstchannel",
    "lastapp",
    "lastdata",
    "start",
    "answer",
    "end",
    "duration",
    "billsec",
    "disposition",
    "amaflags",
    "uniqueid",
    "userfield",
)

_HEADER_ALIASES = {
    "source": "src",
    "destination": "dst",
    "callerid": "clid",
    "calldate": "start",
    "starttime": "start",
    "answertime": "answer",
    "endtime": "end",
    "billableseconds": "billsec",
    "dstcontext": "dcontext",
    "destinationcontext": "dcontext",
}


@dataclass(frozen=True)
class CallMetadata:
    """Parties, times, and Asterisk ids for one recording."""

    caller: str | None = None
    callee: str | None = None
    caller_name: str | None = None
    uniqueid: str | None = None
    linkedid: str | None = None
    direction: str | None = None
    dcontext: str | None = None
    started_at: datetime | None = None
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    billsec: float | None = None
    disposition: str | None = None
    filename: str | None = None


@dataclass(frozen=True)
class CdrDirectory:
    """CDR rows indexed by uniqueid and by recording basename."""

    by_uniqueid: dict[str, CallMetadata]
    by_filename: dict[str, CallMetadata]

    def lookup(self, filename: str, uniqueid: str | None) -> CallMetadata | None:
        """Prefer the uniqueid, then the recording file name FreePBX stores."""
        if uniqueid and uniqueid in self.by_uniqueid:
            return self.by_uniqueid[uniqueid]
        return self.by_filename.get(Path(filename).name)


def normalize_direction(value: str | None) -> str | None:
    """Canonical direction name. Unknown tokens are lower-cased and kept."""
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    return _TYPE_DIRECTION.get(cleaned, cleaned)


def parse_timestamp(value: str | None, *, strict: bool = False) -> datetime | None:
    """Parse a PBX timestamp. Aware values keep their clock digits, not UTC."""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        if strict:
            raise InvalidUploadError(
                "started_at must be an ISO timestamp such as 2026-11-02T14:30:15."
            ) from None
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def parse_filename(filename: str) -> CallMetadata:
    """Parse a recording name. Unrecognized names return empty metadata.

    Only the base name is used, so a FreePBX path
    ``2026/11/02/internal-102-100-....wav`` and a hostile ``../`` prefix
    cannot change the result or escape the recordings directory.
    """
    base = Path(filename).name
    suffix = Path(base).suffix
    stem = base[: -len(suffix)] if suffix else base
    parsed = _parse_dialplan(stem) or _parse_freepbx(stem) or _parse_uniqueid(stem)
    if parsed is None:
        return CallMetadata(filename=base)
    return CallMetadata(
        caller=parsed.caller,
        callee=parsed.callee,
        caller_name=parsed.caller_name,
        uniqueid=parsed.uniqueid,
        linkedid=parsed.linkedid,
        direction=parsed.direction,
        dcontext=parsed.dcontext,
        started_at=parsed.started_at,
        answered_at=parsed.answered_at,
        ended_at=parsed.ended_at,
        duration_seconds=parsed.duration_seconds,
        billsec=parsed.billsec,
        disposition=parsed.disposition,
        filename=base,
    )


def parse_cdr(text: str) -> CdrDirectory:
    """Parse Asterisk ``cdr_csv`` or a FreePBX CDR export.

    A header row is detected when it contains ``uniqueid`` and a source
    column. Without a header, Asterisk's default 18-column order is used.
    ``calldate`` is accepted as the start time, which is what FreePBX
    ``asteriskcdrdb.cdr`` exports. When several rows share a uniqueid, the
    latest ``ANSWERED`` row wins, otherwise the latest row.
    """
    by_uniqueid: dict[str, CallMetadata] = {}
    by_filename: dict[str, CallMetadata] = {}
    reader = csv.reader(_strip_bom(text).splitlines())
    header: list[str] | None = None
    for raw in reader:
        if not raw or all(not cell.strip() for cell in raw):
            continue
        if header is None and _looks_like_header(raw):
            header = [_normalize_header(cell) for cell in raw]
            continue
        row = _row_dict(raw, header)
        parsed = _metadata_from_cdr_row(row)
        if parsed is None or parsed.uniqueid is None:
            continue
        by_uniqueid[parsed.uniqueid] = _prefer(by_uniqueid.get(parsed.uniqueid), parsed)
        recording = (row.get("recordingfile") or "").strip()
        if recording:
            base = Path(recording).name
            by_filename[base] = _prefer(by_filename.get(base), parsed)
    return CdrDirectory(by_uniqueid=by_uniqueid, by_filename=by_filename)


def merge_metadata(
    parsed: CallMetadata,
    cdr: CallMetadata | None = None,
    overrides: CallMetadata | None = None,
) -> CallMetadata:
    """Combine filename, CDR, and explicit API fields.

    Explicit fields win. The CDR wins over the filename for parties, caller
    name, times, disposition, and talk time, because ``Master.csv`` is the
    call record. Direction stays with the filename when the FreePBX call
    type is present; the CDR context is only a fallback.
    """
    merged = parsed
    if cdr is not None:
        talk = cdr.billsec if cdr.billsec is not None else cdr.duration_seconds
        merged = CallMetadata(
            caller=cdr.caller or parsed.caller,
            callee=cdr.callee or parsed.callee,
            caller_name=cdr.caller_name or parsed.caller_name,
            uniqueid=parsed.uniqueid or cdr.uniqueid,
            linkedid=cdr.linkedid or parsed.linkedid,
            direction=parsed.direction or cdr.direction,
            dcontext=cdr.dcontext or parsed.dcontext,
            started_at=cdr.started_at or parsed.started_at,
            answered_at=cdr.answered_at or parsed.answered_at,
            ended_at=cdr.ended_at or parsed.ended_at,
            duration_seconds=talk if talk is not None else parsed.duration_seconds,
            billsec=cdr.billsec if cdr.billsec is not None else parsed.billsec,
            disposition=cdr.disposition or parsed.disposition,
            filename=parsed.filename,
        )
    if overrides is None:
        return merged
    return CallMetadata(
        caller=_or(overrides.caller, merged.caller),
        callee=_or(overrides.callee, merged.callee),
        caller_name=_or(overrides.caller_name, merged.caller_name),
        uniqueid=_or(overrides.uniqueid, merged.uniqueid),
        linkedid=_or(overrides.linkedid, merged.linkedid),
        direction=normalize_direction(_or(overrides.direction, merged.direction)),
        dcontext=_or(overrides.dcontext, merged.dcontext),
        started_at=overrides.started_at if overrides.started_at is not None else merged.started_at,
        answered_at=overrides.answered_at
        if overrides.answered_at is not None
        else merged.answered_at,
        ended_at=overrides.ended_at if overrides.ended_at is not None else merged.ended_at,
        duration_seconds=overrides.duration_seconds
        if overrides.duration_seconds is not None
        else merged.duration_seconds,
        billsec=overrides.billsec if overrides.billsec is not None else merged.billsec,
        disposition=_or(overrides.disposition, merged.disposition),
        filename=merged.filename or overrides.filename,
    )


class CdrSource:
    """A CDR file reread when its mtime changes."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._mtime: float | None = None
        self._directory = CdrDirectory(by_uniqueid={}, by_filename={})

    def lookup(self, filename: str, uniqueid: str | None) -> CallMetadata | None:
        self.refresh()
        return self._directory.lookup(filename, uniqueid)

    def refresh(self, *, force: bool = False) -> int:
        """Reload the file when it changed. Returns the number of uniqueids."""
        if self.path is None or not self.path.is_file():
            self._directory = CdrDirectory(by_uniqueid={}, by_filename={})
            self._mtime = None
            return 0
        mtime = self.path.stat().st_mtime
        if not force and self._mtime == mtime:
            return len(self._directory.by_uniqueid)
        text = self.path.read_text(encoding="utf-8", errors="replace")
        self._directory = parse_cdr(text)
        self._mtime = mtime
        return len(self._directory.by_uniqueid)


def direction_from_context(dcontext: str, dst: str) -> str | None:
    """A coarse hint from the Asterisk context when the filename has no type.

    ``from-trunk`` / ``from-pstn`` / ``ext-did`` are inbound. ``from-internal``
    to a short extension is an internal call; a longer dial string is outbound.
    This is a hint for stock context names, not a full dialplan analysis.
    """
    ctx = dcontext.strip().lower()
    if not ctx:
        return None
    if ctx.startswith(("from-trunk", "from-pstn", "from-did", "ext-did", "from-external")):
        return "inbound"
    if ctx.startswith("from-internal"):
        if dst.isdigit() and len(dst) <= 6:
            return "internal"
        return "outbound"
    return None


def parse_clid(clid: str) -> tuple[str | None, str | None]:
    """Split ``"Ada Obi" <1001>`` into a name and a number."""
    raw = clid.strip()
    if not raw:
        return None, None
    match = _CLID_RE.match(raw)
    if match is None:
        if re.fullmatch(r"[0-9*#+]+", raw):
            return None, raw
        return raw, None
    name = (match.group("quoted") or match.group("plain") or "").strip() or None
    number = match.group("number").strip() or None
    return name, number


def _parse_dialplan(stem: str) -> CallMetadata | None:
    parts = stem.split("-")
    if len(parts) < 5:
        return None
    if not _DATE_RE.fullmatch(parts[0]) or not _TIME_RE.fullmatch(parts[1]):
        return None
    caller, callee = parts[-2], parts[-1]
    if not _PARTY_RE.fullmatch(caller) or not _PARTY_RE.fullmatch(callee):
        return None
    uniqueid = "-".join(parts[2:-2])
    if not _UNIQUEID_RE.fullmatch(uniqueid):
        return None
    started = _stamp(parts[0], parts[1])
    if started is None:
        return None
    return CallMetadata(
        caller=caller,
        callee=callee,
        uniqueid=uniqueid,
        started_at=started,
    )


def _parse_freepbx(stem: str) -> CallMetadata | None:
    match = re.fullmatch(
        rf"(?P<head>.+)-(?P<date>\d{{8}})-(?P<time>\d{{6}})-(?P<uniqueid>{_UNIQUEID_BODY})",
        stem,
    )
    if match is None:
        return None
    started = _stamp(match.group("date"), match.group("time"))
    if started is None:
        return None
    pieces = match.group("head").split("-")
    if len(pieces) < 3:
        return None
    call_type, source = pieces[0], pieces[-1]
    destination = "-".join(pieces[1:-1])
    if not _PARTY_RE.fullmatch(source) or not _DEST_RE.fullmatch(destination):
        return None
    if not call_type:
        return None
    return CallMetadata(
        caller=source,
        callee=destination,
        uniqueid=match.group("uniqueid"),
        direction=normalize_direction(call_type),
        started_at=started,
    )


def _parse_uniqueid(stem: str) -> CallMetadata | None:
    if not _UNIQUEID_RE.fullmatch(stem):
        return None
    return CallMetadata(uniqueid=stem)


def _stamp(date: str, time: str) -> datetime | None:
    try:
        return datetime.strptime(date + time, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def _normalize_header(cell: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", cell.strip().lower())
    return _HEADER_ALIASES.get(key, key)


def _looks_like_header(row: list[str]) -> bool:
    cells = {_normalize_header(cell) for cell in row}
    return "uniqueid" in cells and "src" in cells


def _row_dict(row: list[str], header: list[str] | None) -> dict[str, str]:
    if header is None:
        padded = list(row) + [""] * max(0, len(_CDR_COLUMNS) - len(row))
        return dict(zip(_CDR_COLUMNS, padded, strict=False))
    width = min(len(header), len(row))
    return {header[index]: row[index] for index in range(width)}


def _metadata_from_cdr_row(row: dict[str, str]) -> CallMetadata | None:
    uniqueid = (row.get("uniqueid") or "").strip()
    if not uniqueid:
        return None
    name, clid_number = parse_clid(row.get("clid") or "")
    cnam = (row.get("cnam") or "").strip() or None
    src = (row.get("src") or "").strip()
    cnum = (row.get("cnum") or "").strip()
    dst = (row.get("dst") or "").strip()
    dcontext = (row.get("dcontext") or "").strip() or None
    linkedid = (row.get("linkedid") or "").strip() or None
    disposition = (row.get("disposition") or "").strip() or None
    caller = src or cnum or clid_number or None
    return CallMetadata(
        caller=caller,
        callee=dst or None,
        caller_name=name or cnam,
        uniqueid=uniqueid,
        linkedid=linkedid,
        direction=direction_from_context(dcontext or "", dst),
        dcontext=dcontext,
        started_at=parse_timestamp(row.get("start")),
        answered_at=parse_timestamp(row.get("answer")),
        ended_at=parse_timestamp(row.get("end")),
        duration_seconds=_seconds(row.get("duration")),
        billsec=_seconds(row.get("billsec")),
        disposition=disposition,
    )


def _seconds(value: str | None) -> float | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _prefer(existing: CallMetadata | None, new: CallMetadata) -> CallMetadata:
    if existing is None:
        return new
    existing_answered = (existing.disposition or "").upper() == "ANSWERED"
    new_answered = (new.disposition or "").upper() == "ANSWERED"
    if new_answered or not existing_answered:
        return new
    return existing


def _or(value: str | None, fallback: str | None) -> str | None:
    return fallback if value is None else value
