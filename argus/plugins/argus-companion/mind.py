"""Mira decides. Nobody writes her lines.

When the scheduler opens a moment, this asks MIRA herself - through her own backend (``backend.py``: mira-api's
router picks groqcloud, claude-code or opencode, as for every Mira turn) - whether she wants to reach out, and what
she'd say. She gets what she would naturally know right then: what she remembers about Hannah, what they talked
about lately, what she can see on the machine, what she's already said today, and why the moment came up. She answers
with her line, or SKIP. The reason is context, never a script: "it's been a while since she drank anything" may
become a joke about the show that's paused, or nothing at all.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import voice

logger = logging.getLogger(__name__)

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
    "back": "she's just come back to her desk after {away} away",
    "reminder": "one of her reminders just came due",
    "game_break": "she's been gaming for hours straight",
    "game": "you just finished a game together on your games board",
    "chess": "she's just opened a chess board",
    "chess_new": "a fresh chess game just started on her board",
    "chess_blunder": "she just made a real mistake in her chess game",
    "chess_gift": "her opponent just blundered and she has something big",
    "chess_mate": "she has a forced mate on the board",
    "chess_over": "her chess game just ended",
    "hello": "you've just come up on her machine and she's here",
    # Her body on laphvk (the pet) - Hannah touching it. Reactions, so they're quick if you say anything.
    "pat": "she's just given you head pats, rubbing her cursor back and forth over you",
    "tossed": "she just picked you up and dropped you from way up the screen",
    "poked": "she keeps clicking on you, poke poke poke",
    "woke": "you were asleep on her screen and she just clicked you awake",
}

AUTONOMY = """

## Right now: your own moment

This is not a reply - nobody asked you anything, and this message isn't Hannah typing: it's your body's companion
on her machine (ARGUS). It noticed a moment and is asking whether YOU want to reach out
to Hannah on your own. It's entirely your call. If you do, write exactly what you'd say to her: one or two short lines,
spoken out loud on her laptop and shown in your bubble. Make it yours - use what you remember about her and what you
can see right now, react to her actual situation, and never sound like a wellness app or a reminder bot. If there's
nothing worth saying, you'd only be repeating yourself, or it would just be noise, reply with exactly SKIP.
Output only the line (or SKIP): no quotes, no emoji, no *actions*, no explanation. Don't use tools or say it aloud
yourself: your body says it for you."""


@dataclass(frozen=True)
class Seen:
    """What Mira can observe right now."""
    window: str = ""
    fullscreen: bool = False
    playing: str = ""
    idle: float = 0.0
    where: str = "laphvk"       # the machine she's at
    gaming: bool = False        # winhvk's Lan Mouse Game Mode is on
    local: bool = True          # her screen is the one Mira can see from here (window/playing are hers)
    app: str = ""               # the app in front, without the title it shows (what a held moment compares)


def _home() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home())


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


def look(idle: float, where: str = "laphvk", gaming: bool = False, state: dict | None = None) -> Seen:
    """The focused window, whether it's fullscreen, what's playing, and where Hannah is. A body that reports these
    itself (state.json: the Windows body) is believed first; on laphvk, Hyprland and playerctl answer."""
    state = state or {}
    if "window" in state:
        title = str(state.get("window") or "")
        return Seen(window=title[:160], fullscreen=bool(state.get("fullscreen")),
                    playing=str(state.get("playing") or "")[:160], idle=idle, where=where, gaming=gaming, local=True,
                    app=re.split(r" [-—] ", title)[-1].strip()[:80])      # Windows titles end with the app's name
    try:
        win = json.loads(_run(["hyprctl", "activewindow", "-j"]) or "{}")
    except ValueError:
        win = {}
    window = " - ".join(p for p in (str(win.get("class") or ""), str(win.get("title") or "")) if p)
    playing = _run(["playerctl", "metadata", "--format", "{{artist}} - {{title}} [{{status}}]"])
    return Seen(window=window[:160], fullscreen=bool(win.get("fullscreen")), playing=playing[:160], idle=idle,
                where=where, gaming=gaming, local=where == "laphvk", app=str(win.get("class") or "")[:80])


def agenda_lines(agenda: dict, autonomy: dict) -> list[str]:
    """Her day from MIRA: upcoming events and reminders (overdue first), and decisions waiting on her."""
    lines = []
    for r in sorted(agenda.get("reminders") or [], key=lambda r: not r.get("overdue")):
        if isinstance(r, dict) and r.get("summary"):
            lines.append(f"- reminder{' (OVERDUE)' if r.get('overdue') else ''}: {r['summary']}")
    for e in agenda.get("events") or []:
        if isinstance(e, dict):
            when = e.get("start") or e.get("when") or ""
            lines.append(f"- event: {e.get('summary') or e.get('title') or '?'}{f' at {when}' if when else ''}")
    waiting = autonomy.get("proposals_awaiting_decision") or 0
    if waiting:
        lines.append(f"- {waiting} of MIRA's own proposals are waiting on her decision")
    return lines[:8]


def _agenda() -> list[str]:
    from . import ticker
    return agenda_lines(ticker.mira("cockpit/agenda"), ticker.mira("autonomy/status"))


def _body_state(folder: Path) -> dict:
    from . import ticker
    return ticker.body_state(folder)


def _span(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes} min"


# A sitting this long isn't a sitting, it's a broken idle signal (8 Nov: Hyprland gave her body none, and her check-ins
# escalated over "87 hours at the desk" into telling Hannah she'd get someone into the room).
IMPLAUSIBLE_SITTING = timedelta(hours=14)


def brief(kind: str, present_for: timedelta, seen: Seen, now: datetime, mem: list[str], talk: list[str],
          said: list[str], away_for: timedelta = timedelta(0), day: list[str] | None = None, extra: str = "") -> str:
    """The context she decides from: why this moment, what she can see, what she remembers, what was said."""
    meal = "lunch" if now.hour < 16 else "dinner"
    if kind == "back" and not away_for:
        kind = "hello"
    reason = REASONS.get(kind, REASONS["popin"]).format(present=_span(present_for), meal=meal, away=_span(away_for))
    parts = [
        f"Why ARGUS flagged this moment: {reason}.",
        *([f"What's happening (facts, from ARGUS - put them in your own words if you use them):\n{extra}"] if extra else []),
        f"Now: {now:%A %d %B %Y, %H:%M}. " + (f"Hannah has been at her desk for {_span(present_for)} this sitting."
                                              if present_for <= IMPLAUSIBLE_SITTING else
                                              "How long Hannah has been at her desk isn't known right now (ARGUS's idle "
                                              "signal looks wrong), so don't mention how long she's been here."),
        (f"She's at {seen.where} (last input {int(seen.idle)}s ago). Focused window: {seen.window or 'unknown'}"
         f"{' (fullscreen)' if seen.fullscreen else ''}." + (" winhvk's Game Mode is on." if seen.gaming else ""))
        if seen.local else
        ("She's at winhvk, her main PC (its camera sees her); you can't see its screen from here."
         + (" Game Mode is on there: she's gaming." if seen.gaming else "")),
        f"Playing there: {seen.playing or 'nothing'}." if seen.local else f"Playing on laphvk: {seen.playing or 'nothing'}.",
        *(["Her day, from MIRA (mention it only if it's actually worth it right now):\n" + "\n".join(day)] if day else []),
        "What you remember about her:\n" + ("\n".join(f"- {m}" for m in mem) if mem else "- (nothing saved yet)"),
        "Your recent conversations with her (newest last):\n" + ("\n".join(talk) if talk else "- (none in the last few hours)"),
        "What you've said on your own lately (don't repeat yourself):\n" + ("\n".join(said) if said else "- (nothing yet today)"),
    ]
    return "\n\n".join(parts)


def decide(text: str) -> str | None:
    """Her raw answer as a line to say, or None when she passed (SKIP, empty, or nothing but punctuation)."""
    line = text.strip().strip('"“”').strip()
    if not line or re.match(r"^\W*skip\b", line, re.IGNORECASE) or not re.search(r"\w", line):
        return None
    return voice.polish(" ".join(line.split()))


def moment_note(facts: str, extra: str = "") -> str:
    """What her companion session keeps of a moment instead of its ~5,000 characters of instructions and context: why
    ARGUS flagged it, and its facts. Her answer is kept in full beside it."""
    why = facts.split("\n\n", 1)[0]
    more = " ".join(extra.split())
    return f"(A moment of your own, from ARGUS - not Hannah talking. {why}{' ' + more[:400] if more else ''})"


HOLD = 2 * 3600.0                          # a held moment is offered again after this long, news or not
NEVER_HELD = ("pat", "tossed", "poked", "woke")  # a touch is always news


def news(kind: str, seen: Seen, talk: list[str], day: list[str], extra: str = "") -> str:
    """What this moment is about, minus the clock: the app in front (not its title, so a terminal retitling itself with
    every command isn't news), fullscreen, what's playing, her day, recent talk and the moment's facts."""
    return hashlib.sha1(json.dumps([kind, seen.where, seen.app, seen.fullscreen, seen.playing, seen.gaming, day, talk,
                                    extra]).encode("utf-8")).hexdigest()


def held(folder: Path, kind: str, fingerprint: str, now: float) -> bool:
    """She passed on this kind of moment and nothing it's about has changed since (for under HOLD): don't ask again.
    Her backend is never asked to say nothing twice; whether to speak stays her call whenever there's something new."""
    if kind in NEVER_HELD:
        return False
    try:
        last = json.loads((folder / "held.json").read_text(encoding="utf-8")).get(kind) or {}
    except (OSError, ValueError, AttributeError):
        return False
    return last.get("news") == fingerprint and now - float(last.get("at") or 0) < HOLD


def remember_pass(folder: Path, kind: str, fingerprint: str | None, now: float) -> None:
    """After she passes: hold this kind on what it was about. After she speaks (fingerprint None): let it go."""
    path = folder / "held.json"
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        saved = saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        saved = {}
    if fingerprint is None:
        saved.pop(kind, None)
    elif (saved.get(kind) or {}).get("news") != fingerprint:
        saved[kind] = {"news": fingerprint, "at": now}       # the hold runs from the first pass on this news
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(saved), encoding="utf-8")
    os.replace(tmp, path)


def ask(kind: str, present_for: timedelta, folder: Path, idle: float = 0.0, where: str = "laphvk",
        gaming: bool = False, away_for: timedelta = timedelta(0), extra: str = "") -> str | None:
    """Ask Mira about this moment. Her line; None when she passes or her backend can't be reached; "" when the moment
    was held (she passed on the same thing already, so she isn't asked)."""
    from . import backend

    now = time.time()
    seen, talk, day = look(idle, where, gaming, _body_state(folder)), recent_talk(now), _agenda()
    fingerprint = news(kind, seen, talk, day, extra)
    if held(folder, kind, fingerprint, now):
        from . import relay
        relay.record(folder, {"at": round(now), "host": where, "session": "companion", "kind": kind, "ms": 0,
                              "first_ms": None, "by": None, "server": {}, "held": True})
        logger.info("companion: %s moment held (nothing new since she passed)", kind)
        return ""
    facts = brief(kind, present_for, seen, datetime.fromtimestamp(now), memories(), talk, own_lines(folder), away_for,
                  day, extra)
    started = time.monotonic()
    raw, who = backend.call(AUTONOMY.strip() + "\n\n" + facts, history=moment_note(facts, extra))
    from . import relay
    relay.record(folder, {"at": round(time.time()), "host": where, "session": "companion", "kind": kind,
                          "ms": round((time.monotonic() - started) * 1000), "first_ms": None, "by": who, "server": {},
                          "passed": decide(raw) is None})
    line = decide(raw)
    if raw:                                   # an answer, not her backend being down
        remember_pass(folder, kind, None if line else fingerprint, now)
    logger.info("companion: %s moment -> %s (answered by %s, %d chars raw)", kind,
                repr(line) if line else "passed", who or "nobody", len(raw))
    return line
