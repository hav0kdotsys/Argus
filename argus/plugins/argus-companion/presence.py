"""When Mira speaks up on her own: the check-in scheduler.

Pure logic, fed one ``Moment`` per tick by whatever watches the machines (the gateway's presence ticker): the time,
how long Hannah's input has been idle, and whether she's busy (a fullscreen game or video, a call, typing to Mira) or
has asked for quiet. It answers with at most one ``CheckIn`` per tick, or nothing.

Rules:
- Away (idle past ``AWAY``) is not "at the PC": every timer starts over when she's back, so a check-in never greets
  her with "you've been at it for hours" after she's been gone.
- Busy or quiet: nothing is said, and anything that came due waits until she's free.
- Two check-ins are never closer than ``GAP``; the kinds take turns, so water doesn't win every time.
- Interval kinds (water, stretch, eyes) count active time. ``session`` counts one unbroken sitting. ``meal`` fires once
  per meal window she's present for; ``late`` once a night after her bedtime. ``bored`` fires when Mira hasn't been
  talked to for a while although Hannah's right there.

The words come from ``check-ins.md`` (``CheckInLines``), which Hannah edits: a ``## kind`` heading per kind, one
``- line`` per bullet. Removing every bullet under a heading silences that kind.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

AWAY = 600.0          # seconds of idle input that count as away
GAP = 15 * 60.0       # minimum seconds between two check-ins

KINDS = ("water", "stretch", "eyes", "session", "meal", "late", "bored")

# Minutes for the interval kinds, the sitting length for ``session``, the quiet stretch for ``bored``.
DEFAULT_MINUTES = {"water": 75, "stretch": 60, "eyes": 45, "session": 150, "bored": 50}
# Meal windows (start hour, end hour), and the hour after which ``late`` may fire (0-23; after midnight counts too).
DEFAULT_MEALS = ((12, 14), (18, 20))
DEFAULT_BEDTIME = 1


@dataclass(frozen=True)
class Moment:
    now: datetime
    idle: float = 0.0          # seconds since her last keyboard or mouse input
    busy: bool = False         # fullscreen game or video, a call, mid-conversation with Mira
    quiet: bool = False        # she asked Mira to keep quiet
    talked: bool = False       # she talked to Mira since the last tick


@dataclass(frozen=True)
class CheckIn:
    kind: str
    line: str


@dataclass
class Settings:
    enabled: frozenset = frozenset(KINDS)
    minutes: dict = field(default_factory=lambda: dict(DEFAULT_MINUTES))
    meals: tuple = DEFAULT_MEALS
    bedtime: int = DEFAULT_BEDTIME


class Scheduler:
    def __init__(self, settings: Settings | None = None, lines: CheckInLines | None = None):
        self.settings = settings or Settings()
        self.lines = lines
        self._present_since: datetime | None = None
        self._last_said: datetime | None = None
        self._last_talk: datetime | None = None
        self._due_at: dict[str, datetime] = {}
        self._pending: set[str] = set()
        self._meals_done: set[tuple] = set()
        self._night_done: set = set()
        self._turn = 0

    # -- bookkeeping ---------------------------------------------------------------------------------------------

    def _back(self, now: datetime) -> None:
        """She's at the PC again (or for the first time): every timer starts from now."""
        self._present_since = now
        self._last_talk = now
        self._pending.clear()
        for kind in ("water", "stretch", "eyes", "session"):
            self._due_at[kind] = now + timedelta(minutes=self.settings.minutes[kind])

    def _mark_due(self, m: Moment) -> None:
        on = self.settings.enabled
        for kind in ("water", "stretch", "eyes", "session"):
            if kind in on and m.now >= self._due_at[kind]:
                self._pending.add(kind)
                # Interval kinds come round again; one sitting only earns one session nudge.
                step = self.settings.minutes[kind] if kind != "session" else 10 ** 6
                self._due_at[kind] = m.now + timedelta(minutes=step)
        if "meal" in on:
            for start, end in self.settings.meals:
                key = (m.now.date(), start)
                if start <= m.now.hour < end and key not in self._meals_done and self._present_since \
                        and self._present_since <= m.now.replace(hour=start, minute=0, second=0, microsecond=0):
                    self._meals_done.add(key)
                    self._pending.add("meal")
        if "late" in on:
            night = (m.now - timedelta(hours=12)).date()  # 01:00 on the 3rd belongs to the night of the 2nd
            hour = m.now.hour
            late = hour >= self.settings.bedtime and hour < 6 if self.settings.bedtime < 12 else \
                hour >= self.settings.bedtime or hour < 6
            if late and night not in self._night_done:
                self._night_done.add(night)
                self._pending.add("late")
        if "bored" in on and self._last_talk and \
                (m.now - self._last_talk).total_seconds() >= self.settings.minutes["bored"] * 60:
            self._pending.add("bored")
            self._last_talk = m.now  # one nudge per quiet stretch

    # -- the tick ------------------------------------------------------------------------------------------------

    def tick(self, m: Moment) -> CheckIn | None:
        if m.idle >= AWAY:
            self._present_since = None
            return None
        if self._present_since is None:
            self._back(m.now)
        if m.talked:
            self._last_talk = m.now
            self._pending.discard("bored")
        self._mark_due(m)
        if m.busy or m.quiet or not self._pending:
            return None
        if self._last_said and (m.now - self._last_said).total_seconds() < GAP:
            return None
        for offset in range(len(KINDS)):
            kind = KINDS[(self._turn + offset) % len(KINDS)]
            if kind not in self._pending:
                continue
            self._pending.discard(kind)
            line = self.lines.pick(kind) if self.lines else kind
            if not line:
                continue  # Hannah silenced this kind in check-ins.md
            self._turn = (KINDS.index(kind) + 1) % len(KINDS)
            self._last_said = m.now
            return CheckIn(kind, line)
        return None


# ---------------------------------------------------------------------------------------------------- the words

DEFAULT_LINES = """\
# Mira's check-ins

Edit the bullets under each heading to change what Mira says when she checks in on you. Delete a bullet to drop it,
or every bullet under a heading to stop that check-in. A line is said as written.

## water
- Drink some water, Hannah. You're running on caffeine and spite again.
- Water. Now. I'll keep your place.

## stretch
- Stand up and stretch before your spine files a complaint.
- Get up for a minute. Your chair won't miss you, I promise.

## eyes
- Look at something twenty feet away for twenty seconds. Not your phone.
- Eyes off the screen for a sec. I'll still be here.

## session
- You've been at this for hours. Take a proper break, I'll guard the desk.
- Long one today. Go touch some grass, or at least a window.

## meal
- Have you eaten? And no, energy drinks don't count.
- Food. Go. Even you can't debug on an empty stomach.

## late
- It's stupid o'clock, Hannah. Bed.
- It's way past late. Tomorrow-you is already annoyed.

## bored
- You've gone quiet. Blink twice if the code's winning.
- I'm bored. Entertain me or I start reorganising your dotfiles.
"""


class CheckInLines:
    """``check-ins.md``: re-read when it changes on disk, created with the defaults when missing."""

    def __init__(self, path: Path, rng: random.Random | None = None):
        self.path = Path(path)
        self.rng = rng or random.Random()
        self._stamp: float | None = None
        self._lines: dict[str, list[str]] = {}
        self._last: dict[str, str] = {}

    def _load(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(DEFAULT_LINES, encoding="utf-8")
        stamp = self.path.stat().st_mtime
        if stamp == self._stamp:
            return
        self._stamp = stamp
        lines: dict[str, list[str]] = {}
        kind = None
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            heading = re.match(r"^##\s+(\w+)\s*$", raw)
            if heading:
                kind = heading.group(1).lower()
                lines.setdefault(kind, [])
            elif kind and (bullet := re.match(r"^\s*[-*]\s+(.+?)\s*$", raw)):
                lines[kind].append(bullet.group(1))
        self._lines = lines

    def pick(self, kind: str) -> str:
        """A line for *kind*, never the one said last time when there's another; '' when silenced."""
        self._load()
        options = self._lines.get(kind, [])
        if not options:
            return ""
        fresh = [line for line in options if line != self._last.get(kind)] or options
        line = self.rng.choice(fresh)
        self._last[kind] = line
        return line
