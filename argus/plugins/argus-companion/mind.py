"""Mira decides. Nobody writes her lines.

When the scheduler opens a moment, this asks MIRA herself - her identity (SOUL.md), through ARGUS's provider chain
(auxiliary task ``companion``, which follows the main model and its fallbacks) - whether she wants to reach out, and
what she'd say. She gets what she would naturally know right then: what she remembers about Hannah, what they talked
about lately, what she can see on the machine, what she's already said today, and why the moment came up. She answers
with her line, or SKIP. The reason is context, never a script: "it's been a while since she drank anything" may
become a joke about the show that's paused, or nothing at all.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import voice

logger = logging.getLogger(__name__)

TASK = "companion"
RECENT_HOURS = 6
RECENT_LINES = 10
OWN_LINES = 8

# Why a moment came up, as context for her - never words for her to say.
REASONS = {
    "water": "she's been at the PC a good while without anyone nudging her to drink something",
    "stretch": "she's been sat still for a long stretch",
    "eyes": "she's been staring at screens for ages without a break",
    "session": "she's been at it for {present} straight without a real break",
    "meal": "it's {meal} time and she's been here since before it started",
    "late": "it's past her bedtime",
    "bored": "the two of you haven't talked in a while even though she's right there",
    "popin": "no particular reason - you might just feel like reacting to what she's doing, or not",
}

AUTONOMY = """

## Right now: your own moment

This is not a reply - nobody asked you anything. ARGUS noticed a moment and is asking whether YOU want to reach out
to Hannah on your own. It's entirely your call. If you do, write exactly what you'd say to her: one or two short lines,
spoken out loud on her laptop and shown in your bubble. Make it yours - use what you remember about her and what you
can see right now, react to her actual situation, and never sound like a wellness app or a reminder bot. If there's
nothing worth saying, you'd only be repeating yourself, or it would just be noise, reply with exactly SKIP.
Output only the line (or SKIP): no quotes, no emoji, no *actions*, no explanation."""


@dataclass(frozen=True)
class Seen:
    """What Mira can observe right now."""
    window: str = ""
    fullscreen: bool = False
    playing: str = ""
    idle: float = 0.0
    where: str = "laphvk"       # laphvk, or winhvk (her main PC: its screen isn't visible from here)
    gaming: bool = False        # winhvk's Lan Mouse Game Mode is on


def _home() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home())


def soul() -> str:
    """Her identity: the SOUL.md this home actually uses, else the built-in one."""
    path = _home() / "SOUL.md"
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        text = ""
    if not text:
        from hermes_cli.default_soul import DEFAULT_SOUL_MD
        text = DEFAULT_SOUL_MD
    return text


def memories() -> list[str]:
    """What she remembers about Hannah: the built-in memory store's entries (USER.md, MEMORY.md)."""
    found = []
    for name in ("USER.md", "MEMORY.md"):
        try:
            body = (_home() / "memories" / name).read_text(encoding="utf-8-sig")
        except OSError:
            continue
        found += [" ".join(entry.split()) for entry in body.split("§") if entry.strip()]
    return found


MIRA_FEED = Path.home() / ".local/state/mira-agent/history.json"


def mira_feed(now: float, hours: float = RECENT_HOURS, path: Path | None = None) -> list[tuple[float, str]]:
    """Exchanges with MIRA on her other surfaces (voice, phone, Discord), from the voice agent's local feed cache:
    (unix time, line) pairs, one each for Hannah and for Mira."""
    try:
        items = json.loads((path or MIRA_FEED).read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError, AttributeError):
        return []
    found = []
    for item in items:
        if not isinstance(item, dict) or item.get("kind") != "exchange":
            continue
        try:
            stamp = datetime.fromisoformat(str(item.get("at", ""))).timestamp()
        except ValueError:
            continue
        if stamp < now - hours * 3600:
            continue
        surface = str(item.get("client") or "voice")
        at = datetime.fromtimestamp(stamp)
        if item.get("user"):
            found.append((stamp, f"[{at:%H:%M}] Hannah ({surface}): {' '.join(str(item['user']).split())[:240]}"))
        if item.get("reply"):
            found.append((stamp + 0.001, f"[{at:%H:%M}] You ({surface}): {' '.join(str(item['reply']).split())[:240]}"))
    return found


def recent_talk(now: float, hours: float = RECENT_HOURS, limit: int = RECENT_LINES) -> list[str]:
    """Their latest exchanges - in ARGUS (any session) and with MIRA by voice, phone or Discord - newest last."""
    try:
        db = sqlite3.connect(f"file:{_home() / 'state.db'}?mode=ro", uri=True, timeout=2)
        try:
            rows = db.execute(
                "select timestamp, role, content from messages where role in ('user','assistant') and active = 1 "
                "and content is not null and content != '' and timestamp >= ? order by timestamp desc limit ?",
                (now - hours * 3600, limit)).fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        rows = []
    lines = []
    for stamp, role, content in rows:
        text = " ".join(str(content).split())
        if text.startswith(("Operation interrupted", "[System note")):
            continue
        who = "Hannah" if role == "user" else "You"
        lines.append((stamp, f"[{datetime.fromtimestamp(stamp):%H:%M}] {who}: {text[:240]}"))
    lines += mira_feed(now, hours)
    return [line for _, line in sorted(lines)[-limit:]]


def own_lines(folder: Path, limit: int = OWN_LINES) -> list[str]:
    """What she's said on her own lately (checkins.log), newest last."""
    try:
        lines = (folder / "checkins.log").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [line for line in lines if not line.endswith("(passed)")][-limit:]


def _run(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=3, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def look(idle: float, where: str = "laphvk", gaming: bool = False) -> Seen:
    """laphvk's focused window (Hyprland), whether it's fullscreen, what's playing (MPRIS via playerctl), and where
    Hannah is."""
    try:
        win = json.loads(_run(["hyprctl", "activewindow", "-j"]) or "{}")
    except ValueError:
        win = {}
    window = " - ".join(p for p in (str(win.get("class") or ""), str(win.get("title") or "")) if p)
    playing = _run(["playerctl", "metadata", "--format", "{{artist}} - {{title}} [{{status}}]"])
    return Seen(window=window[:160], fullscreen=bool(win.get("fullscreen")), playing=playing[:160], idle=idle,
                where=where, gaming=gaming)


def _span(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes} min"


def brief(kind: str, present_for: timedelta, seen: Seen, now: datetime, mem: list[str], talk: list[str],
          said: list[str]) -> str:
    """The context she decides from: why this moment, what she can see, what she remembers, what was said."""
    meal = "lunch" if now.hour < 16 else "dinner"
    reason = REASONS.get(kind, REASONS["popin"]).format(present=_span(present_for), meal=meal)
    parts = [
        f"Why ARGUS flagged this moment: {reason}.",
        f"Now: {now:%A %d %B %Y, %H:%M}. Hannah has been at her desk for {_span(present_for)} this sitting.",
        ("She's at winhvk, her main PC (its camera sees her); you can't see its screen from here."
         + (" Game Mode is on there: she's gaming." if seen.gaming else ""))
        if seen.where == "winhvk" else
        f"She's on laphvk (last input {int(seen.idle)}s ago). Focused window: {seen.window or 'unknown'}"
        f"{' (fullscreen)' if seen.fullscreen else ''}." + (" winhvk's Game Mode is on." if seen.gaming else ""),
        f"Playing on laphvk: {seen.playing or 'nothing'}.",
        "What you remember about her:\n" + ("\n".join(f"- {m}" for m in mem) if mem else "- (nothing saved yet)"),
        "Your recent conversations with her (newest last):\n" + ("\n".join(talk) if talk else "- (none in the last few hours)"),
        "What you've said on your own lately (don't repeat yourself):\n" + ("\n".join(said) if said else "- (nothing yet today)"),
    ]
    return "\n\n".join(parts)


def _answer_text(response) -> str:
    try:
        content = response.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError):
        return ""
    return re.sub(r"<think>.*?(</think>|$)", "", str(content), flags=re.DOTALL | re.IGNORECASE).strip()


def decide(text: str) -> str | None:
    """Her raw answer as a line to say, or None when she passed (SKIP, empty, or nothing but punctuation)."""
    line = text.strip().strip('"“”').strip()
    if not line or re.match(r"^\W*skip\b", line, re.IGNORECASE) or not re.search(r"\w", line):
        return None
    return voice.polish(" ".join(line.split()))


def ask(kind: str, present_for: timedelta, folder: Path, idle: float = 0.0, where: str = "laphvk",
        gaming: bool = False) -> str | None:
    """Ask Mira about this moment. Her line, or None when she passes or the provider can't be reached."""
    from agent.auxiliary_client import call_llm

    now = time.time()
    messages = [
        {"role": "system", "content": soul() + AUTONOMY},
        {"role": "user", "content": brief(kind, present_for, look(idle, where, gaming), datetime.fromtimestamp(now), memories(),
                                          recent_talk(now), own_lines(folder))},
    ]
    try:
        # Room for a reasoning model to think first: her line is short, the thinking may not be.
        response = call_llm(TASK, messages=messages, max_tokens=2000, temperature=0.9, timeout=90)
    except Exception as exc:  # the provider chain failed: she simply doesn't speak this time
        logger.warning("companion: Mira couldn't be asked (%s)", exc, exc_info=True)
        return None
    raw = _answer_text(response)
    line = decide(raw)
    finish = getattr((getattr(response, "choices", None) or [None])[0], "finish_reason", None)
    logger.info("companion: %s moment -> %s (finish=%s, %d chars raw)", kind,
                repr(line) if line else "passed", finish, len(raw))
    return line
