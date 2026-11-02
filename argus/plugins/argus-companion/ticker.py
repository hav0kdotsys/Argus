"""The check-in ticker on laphvk: real signals in, ``presence.Scheduler`` opens a moment, Mira decides (``mind``).

Signals, all local and read-only:
- idle: ``~/.argus/companion/state.json`` ``{"idle_since": <unix s> | null}``, written by the pet's Wayland
  IdleMonitor (Wayland gives no idle time to a plain process);
- busy: the focused window is fullscreen (``hyprctl activewindow -j``), or MIRA's voice panel is mid-conversation;
- quiet: MIRA's voice panel quiet switch (``127.0.0.1:8769/status``), so one switch quiets MIRA and the pet alike,
  or the bodies' quiet key (a ``quiet`` file in the companion folder);
- where: MIRA's presence table through the panel (``/presence``: winhvk's camera detector, laphvk, the phone), so
  Hannah at winhvk is present even while laphvk sits idle; and winhvk's Lan Mouse Game Mode (she's gaming).

A missing signal reads as "not busy, not quiet, not idle": the ticker never blocks on MIRA or Hyprland being down.
Typing to her body (``ask.json``) gets a real ARGUS turn in one ongoing session, answered in her bubble and out
loud. Touches on her pet body (``event.json``: a pat, a toss, pokes, waking her) are offered to her straight away, unless
MIRA is quiet. What she says goes to ``~/.argus/companion/say.json`` (the pet's bubble), out loud through MIRA's voice panel
(``POST /speak``: refused while MIRA is mid-conversation or quiet, and then the bubble alone carries it), and a line in
``checkins.log``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from . import presence

logger = logging.getLogger(__name__)

PANEL_STATUS = "http://127.0.0.1:8769/status"
PANEL_SPEAK = "http://127.0.0.1:8769/speak"
PANEL_PRESENCE = "http://127.0.0.1:8769/presence"
GAME_MODE_EVERY = 300.0   # seconds between Game Mode checks on winhvk (an ssh round trip)
_game_mode = {"at": 0.0, "on": False}
TICK = 30.0


def companion_dir() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()) / "companion"


STATE_FRESH = 15.0   # seconds a body's state.json report stays current


def body_state(folder: Path) -> dict:
    """What this machine's body reports it sees (state.json): idle_since, and on Windows also window, fullscreen,
    playing and machine. {} when there's no fresh report."""
    try:
        data = json.loads((folder / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    at = data.get("at")
    if isinstance(at, (int, float)) and time.time() - at > STATE_FRESH:
        return {k: v for k, v in data.items() if k == "idle_since"}
    return data


def _idle_seconds(folder: Path, now: float) -> float:
    try:
        since = json.loads((folder / "state.json").read_text(encoding="utf-8")).get("idle_since")
    except (OSError, ValueError, AttributeError):
        return 0.0
    return max(0.0, now - float(since)) if isinstance(since, (int, float)) else 0.0


def _fullscreen(folder: Path | None = None) -> bool:
    state = body_state(folder) if folder else {}
    if "fullscreen" in state:
        return bool(state["fullscreen"])
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


def _talked_since(folder: Path, since: float) -> bool:
    """Hannah talked to Mira in ARGUS since *since* (the companion's turn hook touches ``talked``)."""
    try:
        return (folder / "talked").stat().st_mtime > since
    except OSError:
        return False


def _presence() -> dict:
    """{host: state} from MIRA's presence table (fresh rows only); {} when the panel can't say."""
    try:
        with urllib.request.urlopen(PANEL_PRESENCE, timeout=5) as reply:
            rows = json.loads(reply.read().decode("utf-8")).get("presence", [])
    except (OSError, ValueError, AttributeError):
        return {}
    return {str(r.get("host")): str(r.get("state")) for r in rows if isinstance(r, dict) and not r.get("stale")}


def game_mode() -> bool:
    """winhvk's Lan Mouse Game Mode, checked at most every GAME_MODE_EVERY seconds (an ssh round trip). On winhvk
    itself the body already reports a fullscreen game."""
    if sys.platform == "win32":
        return False
    now = time.time()
    if now - _game_mode["at"] >= GAME_MODE_EVERY:
        out = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", "winhvk",
             r"powershell -NoProfile -ExecutionPolicy Bypass -File %LOCALAPPDATA%\Programs\lan-mouse\lan-mouse-gamemode.ps1 status"],
            capture_output=True, text=True, timeout=20, check=False).stdout if _has_ssh() else ""
        _game_mode.update(at=now, on=out.strip().endswith("on"))
    return _game_mode["on"]


def _has_ssh() -> bool:
    import shutil
    return shutil.which("ssh") is not None


def here() -> str:
    """This machine's name as the estate knows it (laphvk, winhvk)."""
    return socket.gethostname().lower() if sys.platform != "win32" else (os.environ.get("COMPUTERNAME", "winhvk").lower())


def where(folder: Path, hosts: dict | None = None) -> str:
    """Where Hannah is: on winhvk the body there sees her directly; on laphvk, laphvk when she's using it, else
    winhvk when its camera sees her there, else laphvk."""
    if sys.platform == "win32":
        return "winhvk"
    hosts = _presence() if hosts is None else hosts
    if _idle_seconds(folder, time.time()) < 120 or hosts.get("winhvk") != "active":
        return "laphvk"
    return "winhvk"


def moment(folder: Path, last_tick: float = 0.0) -> presence.Moment:
    now = time.time()
    panel = _panel()
    # Each machine with a body has its own companion (winhvk runs MiraPet and `argus companion run` too), so a machine
    # only offers moments while it's the one in use: an idle laphvk is "away" even when the camera sees Hannah at
    # winhvk, and winhvk's companion reaches her there. One Mira at a time, never two at once.
    idle = _idle_seconds(folder, now)
    return presence.Moment(now=datetime.fromtimestamp(now), idle=idle,
                           busy=_fullscreen(folder) or bool(panel.get("busy")),
                           quiet=bool(panel.get("quiet")) or (folder / "quiet").exists(),
                           talked=_talked_since(folder, last_tick) or bool(panel.get("busy")))


def _speak(text: str) -> bool:
    request = urllib.request.Request(PANEL_SPEAK, data=json.dumps({"text": text}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=3) as reply:
            return reply.status == 200
    except OSError:  # HTTPError (409 busy/quiet) is an OSError too
        return False


def say(folder: Path, text: str, kind: str = "say", aloud: bool = True, log: bool = True) -> None:
    """Show *text* in the pet's bubble (atomic replace, a fresh id per line), say it out loud when MIRA's voice is
    free, and log it (her own words only: replies and the thinking dots aren't logged)."""
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "say.json.tmp"
    tmp.write_text(json.dumps({"id": f"{time.time_ns()}", "text": text, "kind": kind}), encoding="utf-8")
    os.replace(tmp, folder / "say.json")
    spoken = aloud and _speak(text)
    if log:
        with open(folder / "checkins.log", "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M} {kind}{' (aloud)' if spoken else ''}: {text}\n")


CHAT_SESSION = "Mira (companion)"   # the ARGUS session typing to her body continues
CHAT_TIMEOUT = 300.0
_asking = threading.Lock()


def answer(folder: Path, text: str) -> str:
    """Hannah typed to her body: a real ARGUS turn (her whole self - SOUL, memory, tools) in one ongoing session,
    and her reply in her bubble and out loud. While she thinks the bubble shows the dots."""
    if not _asking.acquire(blocking=False):
        say(folder, "One at a time, I'm still on your last one.", "reply", aloud=False, log=False)
        return ""
    try:
        say(folder, "…", "thinking", aloud=False, log=False)
        repo = Path(os.environ.get("ARGUS_REPO") or Path(__file__).resolve().parents[3])
        command = [sys.executable, str(repo / "hermes"), "chat", "-Q", "--continue", CHAT_SESSION,
                   "--create-if-missing", "--query-file", "-"]
        try:
            run = subprocess.run(command, input=text, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=CHAT_TIMEOUT, check=False, cwd=str(Path.home()))
            reply = clean_reply(run.stdout) if run.returncode == 0 else ""
            if not reply:
                logger.warning("companion: her turn gave no reply (exit %s): %s", run.returncode, run.stderr[-800:])
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("companion: her turn couldn't run: %s", exc)
            reply = ""
        say(folder, reply or "Lost my train of thought there. Say that again?", "reply", log=False)
        return reply
    finally:
        _asking.release()


def clean_reply(out: str) -> str:
    """Her reply from `chat -Q` output: without the session footer and session notices."""
    out = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out or "")
    lines = [line for line in out.splitlines()
             if not line.startswith(("session_id:", "Session ")) and line.strip()]
    return "\n".join(lines).strip()


def _ask(folder: Path) -> tuple[str, str]:
    """What Hannah typed to her body (``ask.json``: {"id", "text"}): (id, text), or ("", "")."""
    try:
        data = json.loads((folder / "ask.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", ""
    return (str(data.get("id", "")), str(data.get("text", "")).strip()) if isinstance(data, dict) else ("", "")


EVENT_KINDS = ("pat", "tossed", "poked", "woke")
EVENT_POLL = 2.0


def _event(folder: Path) -> tuple[str, str]:
    """The pet's latest touch (``event.json``: {"id", "kind"}): (id, kind), or ("", "") when there is none."""
    try:
        data = json.loads((folder / "event.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", ""
    return (str(data.get("id", "")), str(data.get("kind", ""))) if isinstance(data, dict) else ("", "")


def moment_now(folder: Path, kind: str, present_for, idle: float = 0.0) -> str | None:
    """Offer Mira this moment; say what she chose to say. Her line, or None when she passed."""
    from . import mind
    line = mind.ask(kind, present_for, folder, idle, where=where(folder), gaming=game_mode())
    if line:
        say(folder, line, kind)
    else:
        with open(folder / "checkins.log", "a", encoding="utf-8") as log:
            log.write(f"{datetime.now():%Y-%m-%d %H:%M} {kind} (passed)\n")
    return line


def run(folder: Path | None = None, tick: float = TICK) -> None:
    """Tick until interrupted. Talking to Mira (an ARGUS turn, or MIRA's voice busy) counts for ``bored``."""
    folder = folder or companion_dir()
    folder.mkdir(parents=True, exist_ok=True)
    sched = presence.Scheduler()
    last_tick = 0.0
    seen_event = _event(folder)[0]   # what was already there when she started isn't news
    seen_ask = _ask(folder)[0]
    while True:
        ask_id, text = _ask(folder)
        if ask_id and ask_id != seen_ask:
            seen_ask = ask_id
            if text:
                threading.Thread(target=answer, args=(folder, text), name="companion-answer", daemon=True).start()
        event_id, kind = _event(folder)
        if event_id and event_id != seen_event:
            seen_event = event_id
            if kind in EVENT_KINDS:
                m = moment(folder, last_tick)
                if not m.quiet:
                    moment_now(folder, kind, timedelta(0), m.idle)
        if time.time() - last_tick >= tick:
            m = moment(folder, last_tick)
            last_tick = time.time()
            opening = sched.tick(m)
            if opening:
                moment_now(folder, opening.kind, opening.present_for, m.idle)
        time.sleep(EVENT_POLL)
