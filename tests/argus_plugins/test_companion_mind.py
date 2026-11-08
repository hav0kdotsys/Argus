"""argus-companion's mind: Mira decides whether and what to say; nobody puts words in her mouth."""

from __future__ import annotations

import importlib
import json
import importlib.util
import sqlite3
import sys
import time
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
    monkeypatch.setattr(mind, "MIRA_FEED", tmp_path / "no-feed.json")
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


def test_talk_with_mira_elsewhere_joins_argus_talk_in_time_order(mind, tmp_path):
    import json
    db = sqlite3.connect(tmp_path / "state.db")
    db.execute("create table messages (timestamp real, role text, content text, active integer)")
    now = datetime(2026, 11, 1, 23, 0).timestamp()
    db.execute("insert into messages values (?, 'user', 'in the terminal', 1)", (now - 300,))
    db.commit()
    db.close()
    at = datetime.fromtimestamp(now - 900).astimezone().isoformat()
    (tmp_path / "no-feed.json").write_text(json.dumps({"items": [
        {"kind": "activity", "text": "guard noise", "at": at},
        {"kind": "exchange", "client": "voice", "user": "can you hear me?", "reply": "Yeah, I hear you.", "at": at},
    ]}), encoding="utf-8")
    assert mind.recent_talk(now) == ["[22:45] Hannah (voice): can you hear me?", "[22:45] You (voice): Yeah, I hear you.",
                                    "[22:55] Hannah: in the terminal"]


def test_at_winhvk_she_knows_she_cant_see_the_screen(mind):
    seen = mind.Seen(window="foot - ignored", where="winhvk", gaming=True, local=False)
    text = mind.brief("popin", timedelta(minutes=50), seen, datetime(2026, 11, 1, 21, 0), [], [], [])
    assert "winhvk" in text and "can't see its screen" in text and "gaming" in text and "foot - ignored" not in text


def test_a_body_that_reports_what_it_sees_is_believed_first(mind):
    state = {"window": "Spotify - Rosa Walton", "fullscreen": False, "playing": "Rosa Walton - Stay [Playing]"}
    seen = mind.look(4, where="winhvk", state=state)
    assert (seen.window, seen.playing, seen.local) == ("Spotify - Rosa Walton", "Rosa Walton - Stay [Playing]", True)
    text = mind.brief("popin", timedelta(minutes=30), seen, datetime(2026, 11, 2, 12, 0), [], [], [])
    assert "She's at winhvk" in text and "Spotify - Rosa Walton" in text and "can't see" not in text


def test_her_day_from_mira_puts_overdue_first_and_counts_waiting_decisions(mind):
    agenda = {"reminders": [{"summary": "Charge your phone"}, {"summary": "Bins out", "overdue": True}],
              "events": [{"summary": "Dentist", "start": "10:30"}]}
    lines = mind.agenda_lines(agenda, {"proposals_awaiting_decision": 2})
    assert lines[0] == "- reminder (OVERDUE): Bins out" and "- event: Dentist at 10:30" in lines
    assert lines[-1].startswith("- 2 of MIRA's own proposals")
    text = mind.brief("popin", timedelta(minutes=5), mind.Seen(), datetime(2026, 11, 2, 9, 0), [], [], [], day=lines)
    assert "Her day, from MIRA" in text and "Bins out" in text
    assert "Her day" not in mind.brief("popin", timedelta(minutes=5), mind.Seen(), datetime(2026, 11, 2, 9, 0), [], [], [])


def test_a_moment_leaves_its_reason_and_facts_in_her_session_not_its_instructions(mind):
    facts = "Why ARGUS flagged this moment: she's been at it for 2h.\n\nNow: Tuesday.\n\nWhat you remember about her:\n- likes tea"
    note = mind.moment_note(facts, "Her reminder \"Bins out\" is now overdue.")
    assert "she's been at it for 2h" in note and "Bins out" in note
    assert "Tuesday" not in note and "likes tea" not in note and mind.AUTONOMY.strip()[:40] not in note


def _asking(mind, monkeypatch, tmp_path, answers):
    """mind.ask with her backend answering from *answers*, and what's on screen settable; returns (calls, set_window)."""
    backend = importlib.import_module("argus_companion_m.backend")
    calls = []
    monkeypatch.setattr(backend, "call", lambda text, **kw: (calls.append(text), (answers.pop(0), "claude-code"))[1])
    window = {"w": "foot - HANDOFF.md", "app": "foot"}
    monkeypatch.setattr(mind, "look", lambda *a, **k: mind.Seen(window=window["w"], fullscreen=False, playing="",
                                                              idle=0, where="laphvk", gaming=False, local=True,
                                                              app=window["app"]))
    monkeypatch.setattr(mind, "_agenda", lambda: ["- reminder: Charge your phone"])
    monkeypatch.setattr(mind, "_body_state", lambda folder: {})
    return calls, window


def test_a_moment_she_passed_on_is_not_asked_again_until_something_changes(mind, monkeypatch, tmp_path):
    calls, window = _asking(mind, monkeypatch, tmp_path, ["SKIP", "Phone. Charger. Now.", "SKIP"])
    assert mind.ask("popin", timedelta(minutes=40), tmp_path) is None and len(calls) == 1
    assert mind.ask("popin", timedelta(minutes=55), tmp_path) == "" and len(calls) == 1      # same news: held
    window["w"] = "foot - vim pet.py"                     # a retitled terminal is the same app: still held
    assert mind.ask("popin", timedelta(minutes=70), tmp_path) == "" and len(calls) == 1
    window.update(w="zen - Chess.com", app="zen")              # something new: she decides again
    assert mind.ask("popin", timedelta(minutes=85), tmp_path) == "Phone. Charger. Now." and len(calls) == 2
    assert mind.ask("popin", timedelta(minutes=99), tmp_path) is None and len(calls) == 3   # she spoke: no hold
    timed = [json.loads(line) for line in (tmp_path / "turns.jsonl").read_text().splitlines()]
    assert [t.get("held", False) for t in timed] == [False, True, True, False, False]


def test_a_hold_runs_out_and_a_touch_is_never_held(mind, monkeypatch, tmp_path):
    calls, _ = _asking(mind, monkeypatch, tmp_path, ["SKIP", "SKIP", "SKIP", "SKIP"])
    mind.ask("bored", timedelta(hours=1), tmp_path)
    saved = json.loads((tmp_path / "held.json").read_text())
    saved["bored"]["at"] = time.time() - mind.HOLD - 1
    (tmp_path / "held.json").write_text(json.dumps(saved))
    assert mind.ask("bored", timedelta(hours=3), tmp_path) is None and len(calls) == 2
    mind.ask("pat", timedelta(0), tmp_path)
    assert mind.ask("pat", timedelta(0), tmp_path) is None and len(calls) == 4


def test_the_app_in_front_is_named_without_its_title(mind):
    seen = mind.look(0, "winhvk", state={"window": "Play Chess Online - Chess.com — Zen Browser"})
    assert seen.app == "Zen Browser" and seen.window.startswith("Play Chess")


def test_an_impossible_sitting_is_never_handed_to_her_as_fact(mind):
    seen = mind.Seen(window="foot", where="laphvk")
    sane = mind.brief("bored", timedelta(hours=3), seen, datetime(2026, 11, 8, 12, 0), [], [], [])
    broken = mind.brief("bored", timedelta(hours=87), seen, datetime(2026, 11, 8, 12, 0), [], [], [])
    assert "3h 00m this sitting" in sane
    assert "87h" not in broken and "don't mention how long" in broken
