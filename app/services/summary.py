"""Short extractive summary of a call.

This is a deterministic stand-in for a language model. It names the parties
and keeps the first two sentences that look like the point of the call
(an invoice, a ticket, a callback, a transfer). It does not paraphrase.
"""

import re

from app.services.metadata import CallMetadata

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_HINTS = ("invoice", "ticket", "callback", "transfer", "agreed", "will ", "outage", "unpaid")


def summarize_call(text: str, metadata: CallMetadata) -> str:
    """One or two sentences a technician can scan in the call list."""
    heading = _heading(metadata)
    picked: list[str] = []
    for sentence in _sentences(text):
        lowered = sentence.lower()
        if any(hint in lowered for hint in _HINTS):
            picked.append(sentence)
        if len(picked) == 2:
            break
    if not picked:
        picked = _sentences(text)[:1]
    body = " ".join(picked).strip()
    if not body:
        return heading
    return f"{heading} {body}"


def _heading(metadata: CallMetadata) -> str:
    caller = metadata.caller or "unknown"
    callee = metadata.callee or "unknown"
    state = _state(metadata.disposition)
    if metadata.direction:
        return f"{state} call from {caller} to {callee} ({metadata.direction})."
    return f"{state} call from {caller} to {callee}."


def _state(disposition: str | None) -> str:
    raw = (disposition or "Recorded").strip() or "Recorded"
    if raw.isupper():
        return raw.capitalize()
    return raw


def _sentences(text: str) -> list[str]:
    body = " ".join(text.split())
    if not body:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT.split(body) if part.strip()]
