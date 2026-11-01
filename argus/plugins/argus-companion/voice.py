"""Mira's voice, enforced in code: the habits a prompt alone doesn't hold.

Models drift back to assistant-speak however the persona is written: a "Great question!" up front, a "Let me know if
you need anything!" or a "What's next?" on the end, *grins* in asterisks, and the same opening word every reply.
These filters take those off a conversational reply and leave everything else alone.

They never touch work output: a reply with a code block, a list, a table or more than a few short paragraphs is
returned unchanged, so a stack trace, a diff or a report reads exactly as the model wrote it. A filter that would
leave fewer than three words keeps the original.
"""

from __future__ import annotations

import re

# Longer than this, or shaped like a document, and it's work, not chat.
CHAT_LIMIT = 700

_WORK_SHAPE = re.compile(r"```|^\s*(?:[-*+]\s|\d+[.)]\s|\|.*\||#{1,6}\s)", re.MULTILINE)

# Customer-support openers. Only stripped when something follows them.
_STOCK_OPENER = re.compile(
    r"^(?:great question|good question|certainly|absolutely|of course|sure thing|happy to help|"
    r"i'?d be happy to help|i'?d be glad to help|no problem)[!,.]*\s+",
    re.IGNORECASE,
)

# Customer-support sign-offs: the whole trailing sentence goes.
_STOCK_CLOSER = re.compile(
    r"(?<=[.!?])\s+[^.!?]*\b(?:let me know if|is there anything else|anything else (?:i can|you need)|"
    r"hope (?:this|that) helps|feel free to|happy to help|don'?t hesitate to|(?:just )?say the word)\b[^.!?]*[.!?]*\s*$",
    re.IGNORECASE,
)

# A hollow invitation on the end: a question that asks nothing about what she just said.
_HOLLOW_CLOSER = re.compile(
    r"(?<=[.!?])\s+[^.!?]*\b(?:what'?s next|what'?s the plan|what now|what (?:are|r) (?:we|you) (?:doing|up to|getting "
    r"into|working on today)|what (?:do|should) we do (?:next|now|today)|shall we|ready (?:for|to) (?:the next|some|more)|"
    r"got any (?:plans|ideas)|what else (?:can|should) (?:i|we))\b[^.!?]*\?\s*$",
    re.IGNORECASE,
)

# *grins*, *leans back* - a stage direction, not markdown bold (**x**) or a lone asterisk.
_ACTION = re.compile(r"(?<![*\w])\*(?!\s)[^*\n]{1,40}(?<!\s)\*(?![*\w])")

# Interjections that wear thin when every reply starts with the same one.
_OPENING = re.compile(
    r"^(?P<word>okay|ok|alright|right|so|well|oh|ooh+|ah|aha|hmm+|huh|yeah|yep|nah|honestly|look|listen|dude|man|"
    r"girl|babe|bro|ugh|lmao|lol|haha+|heh|damn|fuck|shit|wow|whoa|yo|hey)[,.!?]*\s+",
    re.IGNORECASE,
)


def is_chat(text: str) -> bool:
    """True for a conversational reply: short, and not shaped like code, a list, a table or a document."""
    return len(text) <= CHAT_LIMIT and not _WORK_SHAPE.search(text) and text.count("\n\n") < 3


def opener(text: str) -> str:
    """The interjection a reply opens with, lowercased, or ''."""
    match = _OPENING.match(text or "")
    return match.group("word").lower() if match else ""


def _enough(text: str) -> bool:
    return len(re.findall(r"\S+", text)) >= 3


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def polish(text: str, recent_openers: tuple[str, ...] = ()) -> str:
    """The reply with the assistant habits taken off; the same string when nothing applied."""
    if not text or not is_chat(text):
        return text
    line = text.strip()
    for step in (
        lambda s: _STOCK_OPENER.sub("", s, count=1),
        lambda s: _STOCK_CLOSER.sub("", s),
        lambda s: _HOLLOW_CLOSER.sub("", s),
        lambda s: re.sub(r"[ \t]{2,}", " ", _ACTION.sub("", s)).strip(),
    ):
        candidate = step(line).strip()
        if candidate != line and _enough(candidate):
            line = _capital(candidate)
    word = opener(line)
    if word and word in recent_openers:
        candidate = _OPENING.sub("", line, count=1)
        if _enough(candidate):
            line = _capital(candidate)
    return line if line != text.strip() else text
