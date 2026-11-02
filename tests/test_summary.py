"""Extractive call summary."""

from datetime import datetime

from app.services.metadata import CallMetadata
from app.services.speakers import join_segments, parse_labelled_transcript
from app.services.summary import summarize_call
from app.services.transcription.fake import load_sample_call

SAMPLE = (
    "Good afternoon, this is Ada from billing. I am calling about invoice 1842. "
    "Hello Ada, this is the support desk. Invoice 1842 is still unpaid. "
    "We will send the transfer today. Please schedule a callback on Friday if it does not clear. "
    "Agreed. I will open ticket 5521 and call you back on Friday morning."
)


def test_sample_call_text_matches_the_summary_fixture() -> None:
    segments = parse_labelled_transcript(load_sample_call())
    assert join_segments(segments) == SAMPLE


def test_summary_names_the_parties_and_the_invoice() -> None:
    metadata = CallMetadata(
        caller="1001",
        callee="200",
        started_at=datetime(2026, 11, 2, 14, 30, 15),
    )
    assert summarize_call(SAMPLE, metadata) == (
        "Recorded call from 1001 to 200. "
        "I am calling about invoice 1842. "
        "Invoice 1842 is still unpaid."
    )


def test_answered_internal_call_uses_the_disposition() -> None:
    metadata = CallMetadata(
        caller="1001",
        callee="200",
        direction="internal",
        disposition="ANSWERED",
    )
    summary = summarize_call(SAMPLE, metadata)
    assert summary.startswith("Answered call from 1001 to 200 (internal). ")
    assert "ticket 5521" not in summary
