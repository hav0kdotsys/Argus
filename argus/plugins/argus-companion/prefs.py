"""Hannah's settings for Mira's companion, from the SETTINGS tab of her room (``companion/settings.json``).

Read by the ticker every tick, so a change applies at once. Quiet and coaching keep their own files (the hotkeys,
the menu and the CLI write those too); this holds which moments Mira gets offered, how often she pops in, and which of
her lines she says out loud (``voice``). link.py carries the whole file to her other body, so both follow one setting.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import presence

# The moments Hannah can switch off, with what they are (shown in the settings tab).
MOMENTS = {
    "water": "Water", "stretch": "Stretch", "eyes": "Look away from the screen", "session": "Long sitting",
    "meal": "Meals", "late": "Bedtime nudge", "bored": "When you haven't talked in a while", "popin": "Pop-ins",
    "reminder": "Overdue reminders", "game_break": "Game breaks", "chess": "Chess offers",
}
POPIN = {"rarely": (90, 180), "sometimes": (40, 90), "often": (15, 35)}
# Which of her lines she says out loud (HavoK, 8 Nov), everywhere she speaks: her bodies on both PCs and this companion.
# Off, the line still shows in her bubble; it just isn't spoken (and spends no voice credits).
VOICE = {
    "replies": "Replies to you (what you say or type, calls, jobs)",
    "checkins": "Check-ins and reminders",
    "remarks": "Her own remarks (greetings, reactions, what she sees)",
    "commentary": "Game commentary",
}
DEFAULTS = {"off": [], "popin": "sometimes", "voice": dict.fromkeys(VOICE, True)}
# A touch on her body gets a reaction, which is a remark; every other moment the companion offers her is a check-in.
_REMARK_MOMENTS = {"pat", "tossed", "poked", "woke"}


def load(folder: Path) -> dict:
    try:
        data = json.loads((folder / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    off = [k for k in data.get("off", []) if k in MOMENTS] if isinstance(data.get("off"), list) else []
    popin = data.get("popin") if data.get("popin") in POPIN else DEFAULTS["popin"]
    saved = data.get("voice") if isinstance(data.get("voice"), dict) else {}
    voice = {k: saved[k] if isinstance(saved.get(k), bool) else True for k in VOICE}
    return {"off": off, "popin": popin, "voice": voice}


def save(folder: Path, data: dict) -> dict:
    clean = load(folder)
    if isinstance(data.get("off"), list):
        clean["off"] = sorted({k for k in data["off"] if k in MOMENTS})
    if data.get("popin") in POPIN:
        clean["popin"] = data["popin"]
    if isinstance(data.get("voice"), dict):
        clean["voice"].update({k: v for k, v in data["voice"].items() if k in VOICE and isinstance(v, bool)})
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "settings.json.tmp"
    tmp.write_text(json.dumps(clean), encoding="utf-8")
    tmp.replace(folder / "settings.json")
    return clean


def allowed(folder: Path, kind: str) -> bool:
    return kind not in load(folder)["off"]


def voice_kind(moment: str) -> str:
    """The voice setting a companion line falls under: a reaction to a touch is a remark, any other moment a check-in."""
    return "remarks" if moment in _REMARK_MOMENTS else "checkins"


def speaks(folder: Path, kind: str) -> bool:
    """Whether she says this kind of line out loud (an unknown kind counts as a reply)."""
    return load(folder)["voice"].get(kind if kind in VOICE else "replies", True)


def scheduler_settings(folder: Path) -> presence.Settings:
    """The scheduler's settings from Hannah's: her switched-off moments out, her pop-in pace in. (``back`` stays
    out: MIRA's own greeting does that.)"""
    prefs = load(folder)
    minutes = dict(presence.DEFAULT_MINUTES)
    minutes["popin_min"], minutes["popin_max"] = POPIN[prefs["popin"]]
    enabled = frozenset(presence.KINDS) - {"back"} - set(prefs["off"])
    return presence.Settings(enabled=enabled, minutes=minutes)
