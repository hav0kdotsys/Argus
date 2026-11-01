"""argus-companion's voice filters: assistant habits come off chat replies; work output is never touched."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "argus" / "plugins" / "argus-companion" / "voice.py"
_spec = importlib.util.spec_from_file_location("argus_companion_voice", _PATH)
voice = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(voice)


@pytest.mark.parametrize(("said", "kept"), [
    ("Great question! Ermac era JJ was untouchable.", "Ermac era JJ was untouchable."),
    ("Absolutely, the build is green on all three runners.", "The build is green on all three runners."),
    ("Your disk is back to 63% free. Let me know if you need anything else!", "Your disk is back to 63% free."),
    ("Water break, you've been at it three hours. Hope this helps!", "Water break, you've been at it three hours."),
    ("Called it, that boss never stood a chance. So what's next?", "Called it, that boss never stood a chance."),
    ("JJ's Scorpion is flatlining again. What are we getting into today?", "JJ's Scorpion is flatlining again."),
    ("*grins* You are VERY lazy away from a keyboard, Hannah.", "You are VERY lazy away from a keyboard, Hannah."),
    ("Objectives win games; ego loses them. If you want a soundtrack going, say the word and I'll spin something up.",
     "Objectives win games; ego loses them."),
])
def test_assistant_habits_come_off_chat(said, kept):
    assert voice.polish(said) == kept


@pytest.mark.parametrize("said", [
    "Fuck yes, that's the cleanest run you've done all week.",
    "The people that JJ play are fucking abysmal, bring back his Ermac era.",
    "Want to rant or want distracting?",
    "Okay.",
    "Let me know if it breaks again.",
    "**Bold** claim but I stand by it.",
])
def test_her_own_lines_are_left_alone(said):
    assert voice.polish(said) == said


@pytest.mark.parametrize("work", [
    "Fixed it:\n```python\nprint('Great question!')\n```\nLet me know if you need anything else!",
    "Three things changed:\n- the guard\n- the scanner\n- the lock\n\nWhat's next?",
    "| host | disk |\n|---|---|\n| debhvk | 63% |\nHope this helps!",
    "Certainly! " + "word " * 200,
])
def test_work_output_is_never_touched(work):
    assert voice.polish(work) == work


def test_a_repeated_opener_is_dropped_but_a_fresh_one_stays():
    assert voice.polish("Okay, the gateway restarted clean.", ("okay",)) == "The gateway restarted clean."
    assert voice.polish("Okay, the gateway restarted clean.", ("honestly",)) == "Okay, the gateway restarted clean."


def test_a_filter_never_guts_a_reply():
    assert voice.polish("Absolutely! Love it.") == "Absolutely! Love it."
    assert voice.polish("Okay, sure.", ("okay",)) == "Okay, sure."


def _plugin():
    pkg = _PATH.parent
    spec = importlib.util.spec_from_file_location("argus_companion", pkg / "__init__.py",
                                                  submodule_search_locations=[str(pkg)])
    module = importlib.util.module_from_spec(spec)
    sys.modules["argus_companion"] = module
    spec.loader.exec_module(module)
    return module


def test_the_hook_remembers_openers_per_session_and_passes_untouched_replies_through():
    plugin = _plugin()
    hooks = {}
    plugin.register(type("Ctx", (), {"register_hook": lambda self, name, fn: hooks.setdefault(name, fn),
                                     "register_cli_command": lambda self, **_: None})())
    on_reply = hooks["transform_llm_output"]
    assert on_reply(response_text="Honestly, the run is clean.", session_id="a") is None
    assert on_reply(response_text="Honestly, JJ needs new mains.", session_id="a") == "JJ needs new mains."
    assert on_reply(response_text="Honestly, JJ needs new mains.", session_id="b") is None
    assert on_reply(response_text="", session_id="a") is None
