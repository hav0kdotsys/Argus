"""argus-companion's check-in scheduler: when Mira speaks up, and when she keeps quiet."""

from __future__ import annotations

import importlib.util
import itertools
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "argus" / "plugins" / "argus-companion" / "presence.py"
_spec = importlib.util.spec_from_file_location("argus_companion_presence", _PATH)
presence = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = presence  # dataclasses resolve their module through sys.modules
_spec.loader.exec_module(presence)

T0 = datetime(2026, 11, 2, 9, 0)


def _only(*kinds, **minutes):
    settings = presence.Settings(enabled=frozenset(kinds))
    settings.minutes.update(minutes)
    return presence.Scheduler(settings)


def _run(sched, start, minutes, **moment):
    """Tick once a minute; the check-ins said, as (minute, kind)."""
    said = []
    for minute in range(minutes + 1):
        hit = sched.tick(presence.Moment(now=start + timedelta(minutes=minute), **moment))
        if hit:
            said.append((minute, hit.kind))
    return said


def test_water_comes_round_on_its_interval_of_active_time():
    assert _run(_only("water", water=30), T0, 95) == [(30, "water"), (60, "water"), (90, "water")]


def test_being_away_starts_every_timer_over():
    sched = _only("water", water=30)
    _run(sched, T0, 25)
    assert sched.tick(presence.Moment(now=T0 + timedelta(minutes=26), idle=presence.AWAY)) is None
    # Back at minute 40: the next water is 30 minutes of presence later, not at minute 30.
    assert _run(sched, T0 + timedelta(minutes=40), 31) == [(30, "water")]


def test_busy_or_quiet_holds_a_due_check_in_until_she_is_free():
    sched = _only("water", water=10)
    assert _run(sched, T0, 20, busy=True) == []
    assert _run(sched, T0 + timedelta(minutes=21), 0) == [(0, "water")]
    assert _run(_only("water", water=10), T0, 20, quiet=True) == []


def test_two_check_ins_are_never_closer_than_the_gap_and_kinds_take_turns():
    said = _run(_only("water", "stretch", water=20, stretch=20), T0, 60)
    assert [kind for _, kind in said][:2] == ["water", "stretch"]
    assert all(b - a >= presence.GAP / 60 for (a, _), (b, _) in itertools.pairwise(said))


def test_a_meal_nudge_only_when_she_was_here_before_the_window_and_only_once():
    sched = _only("meal")
    assert _run(sched, datetime(2026, 11, 2, 11, 30), 150) == [(30, "meal")]
    late_arrival = _only("meal")
    assert _run(late_arrival, datetime(2026, 11, 2, 12, 30), 60) == []


def test_late_fires_once_a_night_after_bedtime():
    sched = _only("late")
    assert _run(sched, datetime(2026, 11, 2, 0, 30), 120) == [(30, "late")]


def test_bored_needs_her_there_and_mira_ignored():
    sched = _only("bored", bored=30)
    assert _run(sched, T0, 31) == [(30, "bored")]
    talking = _only("bored", bored=30)
    assert _run(talking, T0, 60, talked=True) == []


def test_a_popin_comes_up_now_and_then_with_no_reason_inside_its_window():
    sched = presence.Scheduler(presence.Settings(enabled=frozenset({"popin"})), rng=random.Random(5))
    said = _run(sched, T0, 200)
    assert said and all(kind == "popin" for _, kind in said)
    assert 40 <= said[0][0] <= 90


def test_an_opening_carries_how_long_she_has_been_here():
    sched = _only("session", session=30)
    for minute in range(31):
        hit = sched.tick(presence.Moment(now=T0 + timedelta(minutes=minute)))
    assert hit.kind == "session" and hit.present_for == timedelta(minutes=30)



def test_a_restart_remembers_the_gap_and_that_tonight_already_had_its_goodnight():
    first = _only("late")
    assert _run(first, datetime(2026, 11, 2, 1, 30), 5) == [(0, "late")]
    again = _only("late")
    again.recall(first.remember())
    assert _run(again, datetime(2026, 11, 2, 2, 30), 60) == []
    gap = _only("water", water=1)
    gap.recall({"last_offered": datetime(2026, 11, 2, 9, 0).isoformat()})
    assert _run(gap, datetime(2026, 11, 2, 9, 5), 5) == []   # still inside the 15-minute gap


def test_a_damaged_memory_is_just_forgotten():
    sched = _only("late")
    sched.recall({"nights": ["not a date"], "turn": "x"})
    assert _run(sched, datetime(2026, 11, 2, 1, 30), 2) == [(0, "late")]


def test_coming_back_after_a_long_absence_is_a_back_moment_with_how_long_she_was_gone():
    sched = _only("back", "water")
    sched.tick(presence.Moment(now=T0))                                          # first sight: hello
    sched.tick(presence.Moment(now=T0 + timedelta(minutes=1)))
    sched._last_offered = None
    gone = T0 + timedelta(minutes=5)
    sched.tick(presence.Moment(now=gone, idle=presence.AWAY))                    # away since 4:50 in
    hit = sched.tick(presence.Moment(now=gone + timedelta(minutes=50)))          # back 50 min later
    assert hit.kind == "back" and hit.away_for >= timedelta(minutes=50)


def test_a_short_break_or_a_restart_is_no_greeting():
    sched = _only("back")
    sched.recall({"last_offered": (T0 - timedelta(minutes=5)).isoformat()})     # she spoke 5 min ago: a restart
    assert sched.tick(presence.Moment(now=T0)) is None
    sched.tick(presence.Moment(now=T0 + timedelta(minutes=20), idle=presence.AWAY))
    assert sched.tick(presence.Moment(now=T0 + timedelta(minutes=25))) is None  # gone ~15 min: not a return
