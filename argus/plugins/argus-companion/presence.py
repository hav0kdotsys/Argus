"""When a moment MIGHT be worth Mira reaching out: the scheduler. It never decides what she says, or whether she
says anything - that is hers (``mind.py`` asks her, through the provider, with her memory and what she can see).

Pure logic, fed one ``Moment`` per tick by whatever watches the machines (``ticker.py``): the time, how long Hannah's
input has been idle, and whether she's busy (a fullscreen game or video, a call, mid-conversation with Mira) or has
asked for quiet. It answers with at most one ``Opening`` per tick, or nothing.

Rules:
- Away (idle past ``AWAY``) is not "at the PC": every timer starts over when she's back, so Mira is never prompted
  with "you've been at it for hours" after Hannah's been gone.
- Busy or quiet: no opening is offered; anything that came due waits until she's free.
- Two openings are never closer than ``GAP`` (whether Mira spoke or passed), and the kinds take turns.
- Interval kinds (water, stretch, eyes) count active time; ``session`` is one unbroken sitting; ``meal`` once per meal
  window she was present for; ``late`` once a night after bedtime; ``bored`` when Mira hasn't been talked to for a
  while though Hannah's right there; ``popin`` every so often with no reason at all - Mira may just want to react to
  what Hannah's doing, or pass.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

AWAY = 600.0          # seconds of idle input that count as away
GAP = 15 * 60.0       # minimum seconds between two openings

KINDS = ("water", "stretch", "eyes", "session", "meal", "late", "bored", "popin")

# Minutes for the interval kinds, the sitting length for ``session``, the quiet stretch for ``bored``, and the
# shortest and longest wait between pop-ins.
DEFAULT_MINUTES = {"water": 75, "stretch": 60, "eyes": 45, "session": 150, "bored": 50,
                   "popin_min": 40, "popin_max": 90}
DEFAULT_MEALS = ((12, 14), (18, 20))   # (start hour, end hour)
DEFAULT_BEDTIME = 1                     # 0-23; after midnight counts too


@dataclass(frozen=True)
class Moment:
    now: datetime
    idle: float = 0.0          # seconds since her last keyboard or mouse input
    busy: bool = False         # fullscreen game or video, a call, mid-conversation with Mira
    quiet: bool = False        # she asked Mira to keep quiet
    talked: bool = False       # she talked to Mira since the last tick


@dataclass(frozen=True)
class Opening:
    """A moment Mira may use: why it came up, and how long Hannah has been at the PC this sitting."""
    kind: str
    present_for: timedelta


@dataclass
class Settings:
    enabled: frozenset = frozenset(KINDS)
    minutes: dict = field(default_factory=lambda: dict(DEFAULT_MINUTES))
    meals: tuple = DEFAULT_MEALS
    bedtime: int = DEFAULT_BEDTIME


class Scheduler:
    def __init__(self, settings: Settings | None = None, rng: random.Random | None = None):
        self.settings = settings or Settings()
        self.rng = rng or random.Random()
        self._present_since: datetime | None = None
        self._last_offered: datetime | None = None
        self._last_talk: datetime | None = None
        self._due_at: dict[str, datetime] = {}
        self._pending: set[str] = set()
        self._meals_done: set[tuple] = set()
        self._night_done: set = set()
        self._turn = 0

    # What must survive a restart (an update or a crash): the gap since the last opening, which nights already had
    # their `late` and which meal windows their `meal`, and whose turn is next. Restarts used to reset these, and every
    # deploy one night brought another "go to bed" (2026-11-02).
    def remember(self) -> dict:
        return {"last_offered": self._last_offered.isoformat() if self._last_offered else None,
                "nights": sorted(d.isoformat() for d in self._night_done),
                "meals": sorted(f"{d.isoformat()}@{h}" for d, h in self._meals_done),
                "turn": self._turn}

    def recall(self, saved: dict) -> None:
        try:
            if saved.get("last_offered"):
                self._last_offered = datetime.fromisoformat(saved["last_offered"])
            self._night_done = {datetime.fromisoformat(d).date() for d in saved.get("nights", [])}
            self._meals_done = {(datetime.fromisoformat(m.split("@")[0]).date(), int(m.split("@")[1]))
                                for m in saved.get("meals", [])}
            self._turn = int(saved.get("turn", 0)) % len(KINDS)
        except (ValueError, TypeError, IndexError, AttributeError):
            pass  # a damaged file only costs what it held

    def _popin_wait(self) -> timedelta:
        low, high = self.settings.minutes["popin_min"], self.settings.minutes["popin_max"]
        return timedelta(minutes=self.rng.uniform(low, high))

    def _back(self, now: datetime) -> None:
        """She's at the PC again (or for the first time): every timer starts from now."""
        self._present_since = now
        self._last_talk = now
        self._pending.clear()
        for kind in ("water", "stretch", "eyes", "session"):
            self._due_at[kind] = now + timedelta(minutes=self.settings.minutes[kind])
        self._due_at["popin"] = now + self._popin_wait()

    def _mark_due(self, m: Moment) -> None:
        on = self.settings.enabled
        for kind in ("water", "stretch", "eyes", "session", "popin"):
            if kind in on and m.now >= self._due_at[kind]:
                self._pending.add(kind)
                if kind == "popin":
                    self._due_at[kind] = m.now + self._popin_wait()
                else:  # one sitting earns one session opening
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
            hour, bed = m.now.hour, self.settings.bedtime
            late = (bed <= hour < 6) if bed < 12 else (hour >= bed or hour < 6)
            if late and night not in self._night_done:
                self._night_done.add(night)
                self._pending.add("late")
        if "bored" in on and self._last_talk and \
                (m.now - self._last_talk).total_seconds() >= self.settings.minutes["bored"] * 60:
            self._pending.add("bored")
            self._last_talk = m.now  # one opening per quiet stretch

    def tick(self, m: Moment) -> Opening | None:
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
        if self._last_offered and (m.now - self._last_offered).total_seconds() < GAP:
            return None
        for offset in range(len(KINDS)):
            kind = KINDS[(self._turn + offset) % len(KINDS)]
            if kind in self._pending:
                self._pending.discard(kind)
                self._turn = (KINDS.index(kind) + 1) % len(KINDS)
                self._last_offered = m.now
                return Opening(kind, m.now - self._present_since)
        return None
