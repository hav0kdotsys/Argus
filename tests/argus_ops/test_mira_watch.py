"""MIRA's watcher on debhvk: one alert when something breaks for two runs, one all-clear when it's back."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("mira_watch", Path(__file__).resolve().parents[2] / "argus" / "ops" / "mira_watch.py")
watch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(watch)


def test_a_failure_alerts_once_after_two_runs_and_the_fix_is_reported_once():
    state = {}
    down = [("voice-main", False, "Her ElevenLabs voice (main account) is refusing requests (payment issue).")]
    assert watch.judge(state, down, 100.0) == []                      # one bad run: could be a blip
    [(name, text, alert)] = watch.judge(state, down, 220.0)
    assert name == "voice-main" and alert and "payment issue" in text
    assert watch.judge(state, down, 340.0) == []                      # still down: no repeat
    assert watch.judge(state, [("voice-main", None, "")], 460.0) == []  # nothing to judge this run: no change
    [(_, fixed, alert)] = watch.judge(state, [("voice-main", True, "")], 580.0)
    assert not alert and fixed.startswith("✅") and "payment issue" in fixed
    assert watch.judge(state, [("voice-main", True, "")], 700.0) == []


def test_a_blip_that_passes_on_the_next_run_says_nothing():
    state = {}
    assert watch.judge(state, [("container-bark-tts", False, "bark-tts is restarting")], 100.0) == []
    assert watch.judge(state, [("container-bark-tts", True, "")], 220.0) == []
