"""Speaker-labelled transcript lines."""

from app.services.speakers import SEGMENT_SECONDS, parse_labelled_transcript, speaker_role


def test_known_roles_and_indexed_speakers() -> None:
    assert speaker_role("Agent") == "callee"
    assert speaker_role("customer") == "caller"
    assert speaker_role("speaker2") == "speaker2"
    assert speaker_role("Please") is None


def test_lines_become_timed_segments() -> None:
    text = "\n".join(
        [
            "agent: The queue is clear.",
            "",
            "customer: Thanks, I will call back.",
            "Please send this: the invoice is attached.",
        ]
    )
    segments = parse_labelled_transcript(text)
    assert [segment.speaker for segment in segments] == ["callee", "caller", "unknown"]
    assert segments[0].text == "The queue is clear."
    assert segments[0].start == 0
    assert segments[0].end == SEGMENT_SECONDS
    assert segments[1].start == SEGMENT_SECONDS
    assert "invoice" in segments[2].text
