"""Split a labelled transcript into speaker segments.

The offline provider uses this for text uploads and for the bundled sample
call. A line is a speaker turn only when the word before the colon is a known
role (``caller``, ``callee``, ``agent``, ``customer``) or a ``speaker1`` /
``s1`` tag. Any other line stays ``unknown``, so a sentence that happens to
contain a colon is not treated as a name.
"""

import re

from app.services.models import Segment

SEGMENT_SECONDS = 4.0

_LABEL = re.compile(r"^(?P<label>[A-Za-z][A-Za-z0-9_-]{0,40}):\s*(?P<text>.+?)\s*$")
_INDEXED = re.compile(r"(?:speaker|spk|s)\d+")

_ROLES = {
    "caller": "caller",
    "customer": "caller",
    "from": "caller",
    "callee": "callee",
    "agent": "callee",
    "support": "callee",
    "to": "callee",
}


def speaker_role(label: str) -> str | None:
    """Map a label onto a role, or return None when it is ordinary prose."""
    key = label.strip().lower().replace("-", "_")
    if key in _ROLES:
        return _ROLES[key]
    if _INDEXED.fullmatch(key):
        return key
    return None


def parse_labelled_transcript(text: str) -> tuple[Segment, ...]:
    """Turn speaker-prefixed lines into timed segments.

    Timing is synthetic: each line lasts ``SEGMENT_SECONDS``. The values exist
    so the UI can seek. They are not measured speech.
    """
    segments: list[Segment] = []
    cursor = 0.0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _LABEL.match(line)
        role = speaker_role(match.group("label")) if match else None
        if match and role and match.group("text").strip():
            body = match.group("text").strip()
            speaker = role
        else:
            body = line
            speaker = "unknown"
        end = cursor + SEGMENT_SECONDS
        segments.append(Segment(speaker=speaker, start=cursor, end=end, text=body))
        cursor = end
    return tuple(segments)


def join_segments(segments: tuple[Segment, ...]) -> str:
    """Join segment text into the string that search and the summary read."""
    return " ".join(segment.text for segment in segments).strip()
