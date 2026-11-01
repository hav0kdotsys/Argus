"""One Mira: an ARGUS turn hears what she said on her own, once, and marks that Hannah talked to her."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[2] / "argus" / "plugins" / "argus-companion"


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("argus_companion_turns", _PKG / "__init__.py",
                                                  submodule_search_locations=[str(_PKG)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_companion_dir", lambda: tmp_path)
    return module


def _stamp(minutes_ago: int) -> str:
    return (datetime.now() - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M")


def test_a_new_session_hears_her_recent_words_once_and_later_turns_only_new_ones(plugin, tmp_path):
    log = tmp_path / "checkins.log"
    log.write_text(f"{_stamp(600)} water (aloud): Too old to mention.\n"
                   f"{_stamp(30)} session (aloud): Rivals can wait.\n"
                   f"{_stamp(20)} popin (passed)\n", encoding="utf-8")
    first = plugin._on_turn(session_id="s1")
    assert "Rivals can wait." in first["context"] and "Too old" not in first["context"]
    assert "passed" not in first["context"]
    assert plugin._on_turn(session_id="s1") is None
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(f"{_stamp(0)} late: Bed, HavoK.\n")
    later = plugin._on_turn(session_id="s1")
    assert "Bed, HavoK." in later["context"] and "Rivals" not in later["context"]
    assert "Rivals can wait." in plugin._on_turn(session_id="s2")["context"]


def test_every_turn_marks_that_hannah_talked_to_her(plugin, tmp_path):
    assert plugin._on_turn(session_id="s1") is None  # no log yet: nothing to tell her
    assert (tmp_path / "talked").is_file()


def test_own_words_skip_passes_and_malformed_lines(plugin):
    lines = ["2026-11-01 23:29 session (aloud): Wistful one?", "2026-11-01 23:40 popin (passed)", "garbage"]
    assert plugin.own_words_since(lines, "2026-11-01 00:00") == ['- 23:29 "Wistful one?"']
