"""MIRA's own backend for her body's words: mira-api's ``/call``, so her router picks who answers exactly as it does
for every other Mira turn (groqcloud when it's short, claude-code then opencode otherwise; ARGUS is only ever a
manual pick there). Never ARGUS's own provider chain.

Her moments and what Hannah types to her body share one session of their own (``userId: companion`` with the
``api`` client: session scope ``agent:companion``), so she remembers what she said on her own and never lands in
Hannah's desktop, voice or Discord conversations.

Where mira-api is and its bearer: winhvk's user environment (MIRA_API, MIRA_AUTH_TOKEN, as MiraAgent reads them);
laphvk's voice agent config (``~/.config/mira-agent/config.env``). Read when needed, never logged or copied.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

SESSION = "companion"
DEFAULT_API = "http://debian-hvkt431s:5000"


def _config() -> tuple[str, str]:
    if sys.platform == "win32":
        return os.environ.get("MIRA_API", DEFAULT_API), os.environ.get("MIRA_AUTH_TOKEN", "")
    values: dict[str, str] = {}
    try:
        text = (Path.home() / ".config" / "mira-agent" / "config.env").read_text(encoding="utf-8")
    except OSError:
        text = ""
    for row in text.splitlines():
        key, sep, value = row.strip().partition("=")
        if sep and key in ("MIRA_API", "MIRA_AUTH_TOKEN"):
            values[key] = value.strip().strip('"').strip("'")
    return values.get("MIRA_API", DEFAULT_API), values.get("MIRA_AUTH_TOKEN", "")


def reply_text(data: dict) -> str:
    """Her words from a ``/call`` answer, without any thinking."""
    try:
        content = data["choice"]["message"]["content"] or ""
    except (KeyError, TypeError):
        return ""
    if isinstance(content, list):          # content parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return re.sub(r"<think>.*?(</think>|$)", "", str(content), flags=re.DOTALL | re.IGNORECASE).strip()


def call(text: str, max_tokens: int = 800, temperature: float = 0.9, timeout: float = 150,
         history: str = "") -> tuple[str, str]:
    """One Mira turn in her companion session: (her reply, who answered). ("", "") when she can't be reached.
    history: what the session keeps of *text* (mira-api's ``historyText``), when *text* is mostly instructions."""
    base, token = _config()
    if not token:
        logger.warning("companion: no MIRA_AUTH_TOKEN here; Mira's backend can't be asked")
        return "", ""
    body = {"messages": [{"role": "user", "content": text}], "mode": "agent", "userId": SESSION,
            "maxTokens": max_tokens, "temperature": temperature}
    if history:
        # A generated turn: its words are instructions, not something to look up on the web, and it needs no tools.
        body["historyText"], body["trustedWeb"], body["tools"] = history, False, False
    request = urllib.request.Request(f"{base.rstrip('/')}/v1/mira/call", data=json.dumps(body).encode("utf-8"),
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                              "X-Jarvis-Client": "api"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("companion: Mira's backend didn't answer (%s)", exc)
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    return reply_text(data), str(data.get("answeredBy") or data.get("provider") or "")
