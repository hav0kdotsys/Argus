"""argus-companion's ticker: laphvk's signals in, a line in Mira's bubble out; a missing signal never blocks it."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[2] / "argus" / "plugins" / "argus-companion"


def _ticker():
    spec = importlib.util.spec_from_file_location("argus_companion_t", _PKG / "__init__.py",
                                                  submodule_search_locations=[str(_PKG)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return importlib.import_module("argus_companion_t.ticker")


def test_idle_comes_from_the_pets_state_file_and_a_missing_or_broken_one_reads_as_present(tmp_path):
    ticker = _ticker()
    assert ticker._idle_seconds(tmp_path, 1000.0) == 0.0
    (tmp_path / "state.json").write_text("{not json", encoding="utf-8")
    assert ticker._idle_seconds(tmp_path, 1000.0) == 0.0
    (tmp_path / "state.json").write_text(json.dumps({"idle_since": None}), encoding="utf-8")
    assert ticker._idle_seconds(tmp_path, 1000.0) == 0.0
    (tmp_path / "state.json").write_text(json.dumps({"idle_since": 400}), encoding="utf-8")
    assert ticker._idle_seconds(tmp_path, 1000.0) == 600.0


def test_say_replaces_the_bubble_file_with_a_fresh_id_and_logs_the_line(tmp_path, monkeypatch):
    ticker = _ticker()
    monkeypatch.setattr(ticker, "PANEL_SPEAK", "http://127.0.0.1:9/speak")  # MIRA's voice down: the bubble still shows
    ticker.say(tmp_path, "Water. Now.", "water")
    first = json.loads((tmp_path / "say.json").read_text(encoding="utf-8"))
    ticker.say(tmp_path, "Water. Now.", "water")
    second = json.loads((tmp_path / "say.json").read_text(encoding="utf-8"))
    assert first["text"] == second["text"] == "Water. Now." and first["id"] != second["id"]
    assert not (tmp_path / "say.json.tmp").exists()
    assert (tmp_path / "checkins.log").read_text(encoding="utf-8").count("water: Water. Now.") == 2


def test_with_mira_and_hyprland_unreachable_the_moment_is_free_and_present(tmp_path, monkeypatch):
    ticker = _ticker()
    monkeypatch.setattr(ticker, "PANEL_STATUS", "http://127.0.0.1:9/status")
    monkeypatch.setenv("PATH", str(tmp_path))  # no hyprctl
    m = ticker.moment(tmp_path)
    assert (m.idle, m.busy, m.quiet) == (0.0, False, False)


def test_the_pets_touch_events_are_read_by_id_and_a_broken_file_is_no_event(tmp_path):
    ticker = _ticker()
    assert ticker._event(tmp_path) == ("", "")
    (tmp_path / "event.json").write_text(json.dumps({"id": "171", "kind": "pat", "at": "x"}), encoding="utf-8")
    assert ticker._event(tmp_path) == ("171", "pat")
    (tmp_path / "event.json").write_text("{half", encoding="utf-8")
    assert ticker._event(tmp_path) == ("", "")
    assert set(ticker.EVENT_KINDS) <= set(importlib.import_module("argus_companion_t.mind").REASONS)


def test_what_hannah_types_is_read_by_id_and_the_quiet_key_quiets_her(tmp_path, monkeypatch):
    ticker = _ticker()
    assert ticker._ask(tmp_path) == ("", "")
    (tmp_path / "ask.json").write_text(json.dumps({"id": "9", "text": "  you awake?  "}), encoding="utf-8")
    assert ticker._ask(tmp_path) == ("9", "you awake?")
    monkeypatch.setattr(ticker, "PANEL_STATUS", "http://127.0.0.1:9/status")
    monkeypatch.setattr(ticker, "PANEL_PRESENCE", "http://127.0.0.1:9/presence")
    assert ticker.moment(tmp_path).quiet is False
    (tmp_path / "quiet").write_text("on", encoding="utf-8")
    assert ticker.moment(tmp_path).quiet is True


def test_replies_and_thinking_dots_are_not_logged_as_her_own_words(tmp_path, monkeypatch):
    ticker = _ticker()
    monkeypatch.setattr(ticker, "PANEL_SPEAK", "http://127.0.0.1:9/speak")
    ticker.say(tmp_path, "…", "thinking", aloud=False, log=False)
    ticker.say(tmp_path, "Water.", "water")
    assert (tmp_path / "checkins.log").read_text(encoding="utf-8").splitlines()[-1].endswith("water: Water.")
    assert "thinking" not in (tmp_path / "checkins.log").read_text(encoding="utf-8")


def test_forced_away_holds_until_shes_seen_back_after_the_grace(tmp_path):
    import os
    ticker = _ticker()
    marker = tmp_path / "away"
    marker.write_text("away", encoding="utf-8")
    now = marker.stat().st_mtime
    assert ticker._forced_away(tmp_path, 3.0, now + 10) > ticker.presence.AWAY          # just ran the command: away
    assert ticker._forced_away(tmp_path, 900.0, now + 500) > ticker.presence.AWAY       # still gone
    assert ticker._forced_away(tmp_path, 2.0, now + 500) == 2.0                          # back: the marker goes
    assert not marker.exists()
    assert ticker._forced_away(tmp_path, 2.0, now + 600) == 2.0


def test_overdue_reminders_come_up_once_most_urgent_first():
    ticker = _ticker()
    agenda = {"reminders": [{"summary": "Charge your phone", "overdue": True, "priority": 5},
                            {"summary": "Bins out", "overdue": True, "priority": 1},
                            {"summary": "Call the vet", "overdue": False}]}
    assert ticker.due_reminders(agenda, set()) == ["Bins out", "Charge your phone"]
    assert ticker.due_reminders(agenda, {"Bins out"}) == ["Charge your phone"]
    assert ticker.due_reminders({}, set()) == []


def test_only_allowlisted_mira_routes_are_read():
    assert _ticker().mira("users") == {}


def test_a_long_game_stretch_earns_one_break_nudge_and_a_real_break_resets_it():
    ticker = _ticker()
    clock = ticker.GameClock()
    t0 = 1_000_000.0

    def play(start, minutes, gaming=True):
        return [t for t in range(int(start), int(start + minutes * 60), 30) if clock.due(float(t), gaming)]

    nudges = play(t0, 150)
    assert len(nudges) == 1 and nudges[0] - t0 >= 2 * 3600             # once, at two hours in
    play(t0 + 150 * 60, 10, gaming=False)                               # a real break (10 min)
    again = play(t0 + 160 * 60, 130)
    assert len(again) == 1 and again[0] - (t0 + 160 * 60) >= 2 * 3600  # a fresh stretch


def test_mira_s_spoken_replies_become_captions_once_and_only_new_ones(tmp_path):
    import json
    import os
    from datetime import datetime, timedelta
    ticker = _ticker()
    feed = tmp_path / "history.json"
    old = (datetime.now() - timedelta(minutes=5)).isoformat()
    feed.write_text(json.dumps({"items": [{"kind": "exchange", "client": "voice", "user": "hi", "reply": "Old news.", "at": old}]}))
    captions = ticker.VoiceCaptions(feed)
    assert captions.new_lines() == []                                   # what was said before she started isn't news
    now = datetime.now().isoformat()
    feed.write_text(json.dumps({"items": [
        {"kind": "exchange", "client": "voice", "user": "how are you?", "reply": "Running fine, Hannah.", "at": now},
        {"kind": "exchange", "client": "discord", "user": "yo", "reply": "Not a voice line.", "at": now}]}))
    os.utime(feed, (1e9, 2e9))
    assert captions.new_lines() == ["Running fine, Hannah."]
    os.utime(feed, (1e9, 2e9 + 5))
    assert captions.new_lines() == []
