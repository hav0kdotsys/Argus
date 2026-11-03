"""What MIRA's other body is doing, shown on this one (the mira-body fork), through its hands port.

Her old bodies read ``link.json`` themselves; the fork doesn't, so ARGUS moves it: music playing on her other PC (and
not here, where her body hears its own) has her dance here too, and stop when it stops; her other body coming back
online after a while gets a glitch here, the moment she arrives there. A move she was told to stop isn't restarted:
the bridge only acts when what it heard changes. Silent: it only moves her body.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from . import link, relay

logger = logging.getLogger(__name__)

EVERY = 3.0
AWAY = 120.0         # her other body unheard this long, then heard again, counts as arriving


class Bridge:
    def __init__(self, folder: Path, act=None):
        self.folder = folder
        self.act = act or (lambda tool, args: relay.hands("do", {"tool": tool, "args": args}, timeout=10))
        self.dancing = False
        self.heard_at = 0.0

    def heard(self) -> dict:
        try:
            data = json.loads((self.folder / "link.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def tick(self, here_playing: bool, now: float | None = None) -> list[str]:
        """One look: returns what it had her body do."""
        now = time.time() if now is None else now
        theirs = self.heard()
        at = float(theirs.get("at") or 0)
        fresh = now - at <= link.FRESH
        music = theirs.get("music") if isinstance(theirs.get("music"), dict) else {}
        there = fresh and bool(music.get("playing"))
        wanted = []
        if fresh and at > self.heard_at and self.heard_at and at - self.heard_at > AWAY:
            wanted.append("glitch")
        if fresh:
            self.heard_at = at
        if there and not here_playing and not self.dancing:
            wanted.append("dance")
        elif self.dancing and (not there or here_playing):
            wanted.append("stop_dancing")
        did = []
        for name in wanted:
            answer = self.act("animate", {"name": name})
            if isinstance(answer, dict) and "error" in answer:
                continue                     # her body isn't up here: nothing changed, so it's tried again next look
            did.append(name)
            if name in ("dance", "stop_dancing"):
                self.dancing = name == "dance"
        return did


def start(folder: Path) -> Bridge:
    bridge = Bridge(folder)

    def loop() -> None:
        while True:
            try:
                if (relay.body_folder() / "argus.json").exists():
                    bridge.tick(link.local_music(folder)["playing"])
            except Exception:                    # a bad tick must never end her bridge
                logger.exception("bridge: tick failed")
            time.sleep(EVERY)

    from agent.memory_provider import spawn_context_thread

    spawn_context_thread(loop, name="mira-bridge").start()
    return bridge
