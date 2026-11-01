"""argus-companion's check-in scheduler: when Mira speaks up, and when she keeps quiet."""

from __future__ import annotations

import importlib.util
import itertools
import os
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


def test_lines_come_from_the_file_she_edits_and_an_empty_heading_silences_a_kind(tmp_path):
    lines_file = tmp_path / "check-ins.md"
    lines = presence.CheckInLines(lines_file, random.Random(1))
    assert lines.pick("water")  # the defaults were written
    lines_file.write_text("## water\n- Drink, Hannah.\n- Hydrate or die-drate.\n\n## stretch\n", encoding="utf-8")
    os.utime(lines_file, (1, 1))  # a new mtime, as an edit would give
    picks = {lines.pick("water") for _ in range(6)}
    assert picks == {"Drink, Hannah.", "Hydrate or die-drate."}
    assert lines.pick("stretch") == ""
    sched = presence.Scheduler(presence.Settings(enabled=frozenset({"stretch"}), minutes={**presence.DEFAULT_MINUTES,
                                                                                          "stretch": 5}), lines)
    assert _run(sched, T0, 10) == []


def test_never_the_same_line_twice_in_a_row(tmp_path):
    lines_file = tmp_path / "check-ins.md"
    lines_file.write_text("## water\n- One.\n- Two.\n", encoding="utf-8")
    lines = presence.CheckInLines(lines_file, random.Random(3))
    said = [lines.pick("water") for _ in range(10)]
    assert all(a != b for a, b in itertools.pairwise(said))
