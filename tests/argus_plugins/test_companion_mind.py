"""argus-companion's mind: Mira decides whether and what to say; nobody puts words in her mouth."""

from __future__ import annotations

import importlib
import importlib.util
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[2] / "argus" / "plugins" / "argus-companion"


@pytest.fixture
def mind(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("argus_companion_m", _PKG / "__init__.py",
                                                  submodule_search_locations=[str(_PKG)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    mind = importlib.import_module("argus_companion_m.mind")
    monkeypatch.setattr(mind, "_home", lambda: tmp_path)
    return mind


@pytest.mark.parametrize("raw", ["SKIP", "skip", " SKIP.", "Skip - nothing worth saying", "", "...", '"SKIP"'])
def test_a_pass_is_a_pass(mind, raw):
    assert mind.decide(raw) is None


def test_her_line_is_hers_with_only_the_assistant_habits_taken_off(mind):
    assert mind.decide('"Two hours on that handoff and Lucy\'s still paused. Blink, Hannah."') == \
        "Two hours on that handoff and Lucy's still paused. Blink, Hannah."
    assert mind.decide("Bed. Now. Hope this helps!") == "Bed. Now. Hope this helps!"  # too short to trim: kept


def test_the_brief_gives_reasons_and_observations_never_lines(mind):
    seen = mind.Seen(window="foot - HANDOFF.md", playing="Netflix - Edgerunners [Paused]", idle=12)
    text = mind.brief("session", timedelta(hours=2, minutes=40), seen, datetime(2026, 11, 1, 23, 25),
                      ["Hannah is learning F2L"], ["[23:11] Hannah: off to play Rivals"], ["22:19 water: Drink."])
    assert "2h 40m" in text and "HANDOFF.md" in text and "Edgerunners" in text
    assert "Hannah is learning F2L" in text and "off to play Rivals" in text and "22:19 water: Drink." in text
    assert "Why ARGUS flagged this moment" in text
    # Context, not a script: the reason describes the situation, it never hands her something to say.
    assert not any(quote in mind.REASONS[k] for k in mind.REASONS for quote in ('"', "Say ", "say: "))


def test_passed_moments_never_count_as_things_she_said(mind, tmp_path):
    (tmp_path / "checkins.log").write_text("2026-11-01 22:00 water: Drink up.\n2026-11-01 22:30 popin (passed)\n",
                                           encoding="utf-8")
    assert mind.own_lines(tmp_path) == ["2026-11-01 22:00 water: Drink up."]


def test_memories_come_from_the_memory_store(mind, tmp_path):
    (tmp_path / "memories").mkdir()
    (tmp_path / "memories" / "USER.md").write_text("Calls her Hannah.\n§\nLearning   F2L.\n", encoding="utf-8")
    assert mind.memories() == ["Calls her Hannah.", "Learning F2L."]


def test_recent_talk_reads_both_sides_newest_last_and_skips_system_noise(mind, tmp_path):
    db = sqlite3.connect(tmp_path / "state.db")
    db.execute("create table messages (timestamp real, role text, content text, active integer)")
    now = datetime(2026, 11, 1, 23, 0).timestamp()
    db.executemany("insert into messages values (?, ?, ?, 1)", [
        (now - 600, "user", "about to hop on Rivals"),
        (now - 590, "assistant", "Objectives win games."),
        (now - 580, "assistant", "Operation interrupted: waiting for model response"),
        (now - 570, "tool", "{}"),
        (now - 9 * 3600, "user", "far too old"),
    ])
    db.commit()
    db.close()
    assert mind.recent_talk(now) == ["[22:50] Hannah: about to hop on Rivals", "[22:50] You: Objectives win games."]
