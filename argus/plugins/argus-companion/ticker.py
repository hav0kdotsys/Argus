"""The check-in ticker on laphvk: real signals in, ``presence.Scheduler`` opens a moment, Mira decides (``mind``).

Signals, all local and read-only:
- idle: ``~/.argus/companion/state.json`` ``{"idle_since": <unix s> | null}``, written by the pet's Wayland
  IdleMonitor (Wayland gives no idle time to a plain process);
- busy: the focused window is fullscreen (``hyprctl activewindow -j``), or MIRA's voice panel is mid-conversation;
- quiet: MIRA's voice panel quiet switch (``127.0.0.1:8769/status``), so one switch quiets MIRA and the pet alike.

A missing signal reads as "not busy, not quiet, not idle": the ticker never blocks on MIRA or Hyprland being down.
What she says goes to ``~/.argus/companion/say.json`` (the pet's bubble), out loud through MIRA's voice panel
(``POST /speak``: refused while MIRA is mid-conversation or quiet, and then the bubble alone carries it), and a line in
``checkins.log``.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from . import presence

PANEL_STATUS = "http://127.0.0.1:8769/status"
PANEL_SPEAK = "http://127.0.0.1:8769/speak"
TICK = 30.0


def companion_dir() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()) / "companion"


def _idle_seconds(folder: Path, now: float) -> float:
    try:
        since = json.loads((folder / "state.json").read_text(encoding="utf-8")).get("idle_since")
    except (OSError, ValueError, AttributeError):
        return 0.0
    return max(0.0, now - float(since)) if isinstance(since, (int, float)) else 0.0


def _fullscreen() -> bool:
    try:
        out = subprocess.run(["hyprctl", "activewindow", "-j"], capture_output=True, text=True, timeout=3,
                             check=False).stdout
        return bool(json.loads(out or "{}").get("fullscreen"))
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def _panel() -> dict:
    try:
        with urllib.request.urlopen(PANEL_STATUS, timeout=2) as reply:
            return json.loads(reply.read().decode("utf-8"))
    except (OSError, ValueError):
        return {}


def moment(folder: Path) -> presence.Moment:
    now = time.time()
    panel = _panel()
    return presence.Moment(now=datetime.fromtimestamp(now), idle=_idle_seconds(folder, now),
                           busy=_fullscreen() or bool(panel.get("busy")), quiet=bool(panel.get("quiet")))


def _speak(text: str) -> bool:
    request = urllib.request.Request(PANEL_SPEAK, data=json.dumps({"text": text}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=3) as reply:
            return reply.status == 200
    except OSError:  # HTTPError (409 busy/quiet) is an OSError too
        return False


def say(folder: Path, text: str, kind: str = "say", aloud: bool = True) -> None:
    """Show *text* in the pet's bubble (atomic replace, a fresh id per line), say it out loud when MIRA's voice is
    free, and log it."""
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "say.json.tmp"
    tmp.write_text(json.dumps({"id": f"{time.time_ns()}", "text": text, "kind": kind}), encoding="utf-8")
    os.replace(tmp, folder / "say.json")
    spoken = aloud and _speak(text)
    with open(folder / "checkins.log", "a", encoding="utf-8") as log:
        log.write(f"{datetime.now():%Y-%m-%d %H:%M} {kind}{' (aloud)' if spoken else ''}: {text}\n")


def moment_now(folder: Path, kind: str, present_for, idle: float = 0.0) -> str | None:
    """Offer Mira this moment; say what she chose to say. Her line, or None when she passed."""
    from . import mind
    line = mind.ask(kind, present_for, folder, idle)
    if line:
        say(folder, line, kind)
    else:
        with open(folder / "checkins.log", "a", encoding="utf-8") as log:
            log.write(f"{datetime.now():%Y-%m-%d %H:%M} {kind} (passed)\n")
    return line


def run(folder: Path | None = None, tick: float = TICK) -> None:
    """Tick until interrupted. ``bored`` stays off until the ticker can see that Hannah talked to Mira."""
    folder = folder or companion_dir()
    folder.mkdir(parents=True, exist_ok=True)
    settings = presence.Settings(enabled=frozenset(presence.KINDS) - {"bored"})
    sched = presence.Scheduler(settings)
    while True:
        m = moment(folder)
        opening = sched.tick(m)
        if opening:
            moment_now(folder, opening.kind, opening.present_for, m.idle)
        time.sleep(tick)
