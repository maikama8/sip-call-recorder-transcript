"""Filename and CDR parsing."""

import csv
import io
from datetime import datetime

from app.services.metadata import (
    CallMetadata,
    merge_metadata,
    parse_cdr,
    parse_clid,
    parse_filename,
    parse_timestamp,
)

DIALPLAN = "20261102-143015-1730554215.23-1001-200.wav"
FREEPBX_INTERNAL = "internal-102-100-20250116-102939-1737016179.6.wav"
FREEPBX_OUT = "out-08031234567-1001-20261102-143015-1730554215.23.wav"
FREEPBX_IN = "in-200-unknown-20261102-150201-1730557321.8.wav"
WITH_SYSTEM = "internal-102-100-20250116-102939-pbx01-1737016179.6.wav"
DIALPLAN_SYSTEM = "20261102-143015-pbx01-1730554215.23-1001-200.wav"


def test_dialplan_filename_names_the_parties_in_order() -> None:
    parsed = parse_filename(DIALPLAN)
    assert parsed.caller == "1001"
    assert parsed.callee == "200"
    assert parsed.uniqueid == "1730554215.23"
    assert parsed.started_at == datetime(2026, 11, 2, 14, 30, 15)
    assert parsed.direction is None
    assert parsed.filename == DIALPLAN


def test_freepbx_internal_is_destination_then_source() -> None:
    parsed = parse_filename(f"/var/spool/asterisk/monitor/2025/01/16/{FREEPBX_INTERNAL}")
    assert parsed.caller == "100"
    assert parsed.callee == "102"
    assert parsed.direction == "internal"
    assert parsed.uniqueid == "1737016179.6"
    assert parsed.started_at == datetime(2025, 1, 16, 10, 29, 39)
    assert parsed.filename == FREEPBX_INTERNAL


def test_freepbx_out_and_in_map_direction() -> None:
    outbound = parse_filename(FREEPBX_OUT)
    inbound = parse_filename(FREEPBX_IN)
    assert outbound.caller == "1001"
    assert outbound.callee == "08031234567"
    assert outbound.direction == "outbound"
    assert inbound.caller == "unknown"
    assert inbound.callee == "200"
    assert inbound.direction == "inbound"


def test_systemname_uniqueid_keeps_the_prefix() -> None:
    freepbx = parse_filename(WITH_SYSTEM)
    dialplan = parse_filename(DIALPLAN_SYSTEM)
    assert freepbx.uniqueid == "pbx01-1737016179.6"
    assert freepbx.caller == "100"
    assert freepbx.callee == "102"
    assert dialplan.uniqueid == "pbx01-1730554215.23"
    assert dialplan.caller == "1001"
    assert dialplan.callee == "200"


def test_dashed_destination_stays_intact() -> None:
    parsed = parse_filename("out-1-800-555-0100-1001-20261102-143015-1730554215.23.wav")
    assert parsed.caller == "1001"
    assert parsed.callee == "1-800-555-0100"
    assert parsed.direction == "outbound"


def test_uniqueid_only_and_unrecognized_names() -> None:
    only = parse_filename("1730554215.23.wav")
    assert only.uniqueid == "1730554215.23"
    assert only.caller is None
    assert only.started_at is None

    unknown = parse_filename("../../etc/passwd.wav")
    assert unknown.filename == "passwd.wav"
    assert unknown.uniqueid is None
    assert unknown.caller is None


def test_invalid_calendar_date_is_not_a_partial_parse() -> None:
    parsed = parse_filename("20261399-143015-1730554215.23-1001-200.wav")
    assert parsed.uniqueid is None
    assert parsed.caller is None


def test_gsm_suffix_does_not_change_the_parties() -> None:
    parsed = parse_filename("internal-102-100-20250116-102939-1737016179.6.gsm")
    assert parsed.caller == "100"
    assert parsed.callee == "102"
    assert parsed.filename.endswith(".gsm")


def test_clid_shapes() -> None:
    assert parse_clid('"Ada Obi" <1001>') == ("Ada Obi", "1001")
    assert parse_clid("Ada Obi <1001>") == ("Ada Obi", "1001")
    assert parse_clid("<1001>") == (None, "1001")
    assert parse_clid("1001") == (None, "1001")
    assert parse_clid("") == (None, None)


def test_headerless_asterisk_csv_survives_a_comma_in_lastdata() -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "",
            "1001",
            "200",
            "from-internal",
            '"Ada Obi" <1001>',
            "PJSIP/1001-0000001a",
            "PJSIP/200-0000001b",
            "Dial",
            "PJSIP/200,30",
            "2026-11-02 14:30:15",
            "2026-11-02 14:30:18",
            "2026-11-02 14:32:40",
            "145",
            "142",
            "ANSWERED",
            "DOCUMENTATION",
            "1730554215.23",
            "",
        ]
    )
    directory = parse_cdr(buffer.getvalue())
    row = directory.by_uniqueid["1730554215.23"]
    assert row.caller == "1001"
    assert row.callee == "200"
    assert row.caller_name == "Ada Obi"
    assert row.direction == "internal"
    assert row.dcontext == "from-internal"
    assert row.started_at == datetime(2026, 11, 2, 14, 30, 15)
    assert row.answered_at == datetime(2026, 11, 2, 14, 30, 18)
    assert row.ended_at == datetime(2026, 11, 2, 14, 32, 40)
    assert row.billsec == 142
    assert row.duration_seconds == 145
    assert row.disposition == "ANSWERED"


def test_answered_row_wins_over_a_later_no_answer() -> None:
    text = "\n".join(
        [
            ",1001,200,from-internal,,PJSIP/1001,PJSIP/200,Dial,PJSIP/200,2026-11-02 14:30:15,"
            "2026-11-02 14:30:18,2026-11-02 14:32:40,145,142,ANSWERED,DOCUMENTATION,1730554215.23,",
            ",1001,200,from-internal,,PJSIP/1001,PJSIP/200,Dial,PJSIP/200,2026-11-02 14:30:15,"
            ",,10,0,NO ANSWER,DOCUMENTATION,1730554215.23,",
        ]
    )
    row = parse_cdr(text).by_uniqueid["1730554215.23"]
    assert row.disposition == "ANSWERED"
    assert row.billsec == 142


def test_freepbx_export_uses_calldate_and_recordingfile() -> None:
    text = "\n".join(
        [
            "calldate,clid,src,dst,dcontext,duration,billsec,disposition,uniqueid,linkedid,recordingfile",
            "2026-11-02 09:15:00,Ada Obi <1001>,1001,08031234567,from-internal,90,88,ANSWERED,"
            "1730538900.4,1730538900.4,out-08031234567-1001-20261102-091500-1730538900.4.wav",
        ]
    )
    directory = parse_cdr(text)
    row = directory.lookup("odd-name.wav", None)
    assert row is None
    row = directory.lookup("out-08031234567-1001-20261102-091500-1730538900.4.wav", None)
    assert row is not None
    assert row.uniqueid == "1730538900.4"
    assert row.linkedid == "1730538900.4"
    assert row.started_at == datetime(2026, 11, 2, 9, 15, 0)
    assert row.direction == "outbound"
    assert row.caller_name == "Ada Obi"
    assert row.billsec == 88


def test_cnum_fills_a_blank_src() -> None:
    text = "uniqueid,src,cnum,dst,cnam\n1730554215.23,,1001,200,Ada\n"
    row = parse_cdr(text).by_uniqueid["1730554215.23"]
    assert row.caller == "1001"
    assert row.caller_name == "Ada"


def test_trunk_context_is_inbound() -> None:
    text = "uniqueid,src,dst,dcontext,disposition\n1730.1,08031234567,200,from-trunk,ANSWERED\n"
    row = parse_cdr(text).by_uniqueid["1730.1"]
    assert row.direction == "inbound"
    assert row.caller == "08031234567"
    assert row.callee == "200"


def test_cdr_overrides_parties_and_filename_keeps_direction() -> None:
    parsed = parse_filename(FREEPBX_INTERNAL)
    cdr = CallMetadata(caller="5555", callee="102", disposition="ANSWERED", billsec=10)
    merged = merge_metadata(parsed, cdr, None)
    assert merged.caller == "5555"
    assert merged.direction == "internal"
    assert merged.disposition == "ANSWERED"
    assert merged.duration_seconds == 10
    assert merged.uniqueid == "1737016179.6"


def test_explicit_fields_win() -> None:
    parsed = parse_filename(DIALPLAN)
    override = CallMetadata(
        caller="9999",
        direction="out",
        started_at=datetime(2026, 11, 2, 16, 0, 0),
    )
    merged = merge_metadata(parsed, None, override)
    assert merged.caller == "9999"
    assert merged.callee == "200"
    assert merged.direction == "outbound"
    assert merged.started_at == datetime(2026, 11, 2, 16, 0, 0)


def test_zero_billsec_is_kept() -> None:
    parsed = parse_filename(DIALPLAN)
    cdr = CallMetadata(billsec=0, duration_seconds=12, disposition="NO ANSWER")
    merged = merge_metadata(parsed, cdr, None)
    assert merged.duration_seconds == 0
    assert merged.billsec == 0
    assert merged.disposition == "NO ANSWER"


def test_parse_timestamp_keeps_the_clock_digits() -> None:
    assert parse_timestamp("2026-11-02 14:30:15") == datetime(2026, 11, 2, 14, 30, 15)
    assert parse_timestamp("2026-11-02T14:30:15+01:00") == datetime(2026, 11, 2, 14, 30, 15)
    assert parse_timestamp("") is None
    assert parse_timestamp("yesterday") is None
