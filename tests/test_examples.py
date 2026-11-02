"""The files in examples/ and docs/ stay aligned with the parser."""

from pathlib import Path

from app.services.metadata import parse_cdr, parse_filename

ROOT = Path(__file__).resolve().parents[1]

# caller, callee, direction, uniqueid
EXPECTED = {
    "internal-102-100-20250116-102939-1737016179.6.wav": ("100", "102", "internal", "1737016179.6"),
    "out-08031234567-1001-20261102-143015-1730554215.23.wav": (
        "1001",
        "08031234567",
        "outbound",
        "1730554215.23",
    ),
    "in-200-unknown-20261102-150201-1730557321.8.wav": (
        "unknown",
        "200",
        "inbound",
        "1730557321.8",
    ),
    "internal-102-100-20250116-102939-pbx01-1737016179.6.wav": (
        "100",
        "102",
        "internal",
        "pbx01-1737016179.6",
    ),
    "20261102-143015-1730554215.23-1001-200.wav": ("1001", "200", None, "1730554215.23"),
    "20261102-143015-pbx01-1730554215.23-1001-200.wav": (
        "1001",
        "200",
        None,
        "pbx01-1730554215.23",
    ),
    "1730554215.23.wav": (None, None, None, "1730554215.23"),
}


def _documented_names() -> list[str]:
    names: list[str] = []
    for raw in (ROOT / "examples" / "filenames.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names


def test_documented_filenames_parse() -> None:
    names = _documented_names()
    assert names == list(EXPECTED)
    for name, expected in EXPECTED.items():
        parsed = parse_filename(name)
        assert (parsed.caller, parsed.callee, parsed.direction, parsed.uniqueid) == expected


def test_sample_asterisk_cdr() -> None:
    directory = parse_cdr((ROOT / "examples" / "sample_cdr.csv").read_text(encoding="utf-8"))
    row = directory.by_uniqueid["1730554215.23"]
    assert row.caller == "1001"
    assert row.callee == "200"
    assert row.caller_name == "Ada Obi"
    assert row.disposition == "ANSWERED"
    assert row.billsec == 142
    assert row.direction == "internal"


def test_sample_freepbx_cdr_export() -> None:
    directory = parse_cdr((ROOT / "examples" / "freepbx_cdr.csv").read_text(encoding="utf-8"))
    filename = "out-08031234567-1001-20261102-091500-1730538900.4.wav"
    row = directory.lookup(filename, None)
    assert row is not None
    assert row.caller == "1001"
    assert row.callee == "08031234567"
    assert row.direction == "outbound"
    assert row.linkedid == "1730538900.4"
    assert row.billsec == 88


def test_dialplan_snippet_uses_mixmonitor_and_filter() -> None:
    dialplan = (ROOT / "examples" / "extensions_custom.conf").read_text(encoding="utf-8")
    assert "MixMonitor" in dialplan
    assert "FILTER" in dialplan
    assert "bB(15)" in dialplan
    assert "AUDIOHOOK_INHERIT(MixMonitor)" in dialplan
    docs = (ROOT / "docs" / "asterisk-mixmonitor.md").read_text(encoding="utf-8")
    freepbx = (ROOT / "docs" / "freepbx.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "MixMonitor" in docs
    assert "extensions_additional.conf" in freepbx
    assert "https://github.com/maikama8" in readme
    assert "Abdulrasheed Oseni" in readme
    assert "```mermaid" in readme
