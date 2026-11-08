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
MIRA is quiet. What she says goes to her body's bubble (the mira-body fork's hands port, ``/show``; and
``~/.argus/companion/say.json``, which her retired bodies read), out loud through MIRA's voice panel (``POST /speak``:
refused while MIRA is mid-conversation or quiet, and then the bubble alone carries it), and a line in ``checkins.log``.
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


PANEL_MIRA = "http://127.0.0.1:8769/mira/"


MIRA_ROUTES = ("cockpit/agenda", "cockpit/music", "cockpit/notifications", "autonomy/status")


def _mira_request(route: str) -> urllib.request.Request | str:
    """laphvk: the voice panel's read-only proxy (it holds the token). winhvk: mira-api itself, the way MiraAgent
    reaches it (MIRA_API, default debhvk:5000, bearer MIRA_AUTH_TOKEN from the user's environment)."""
    if sys.platform != "win32":
        return PANEL_MIRA + route
    base = os.environ.get("MIRA_API", "http://debian-hvkt431s:5000").rstrip("/")
    return urllib.request.Request(f"{base}/v1/mira/{route}",
                                  headers={"Authorization": f"Bearer {os.environ.get('MIRA_AUTH_TOKEN', '')}"})


def mira(route: str) -> dict:
    """A read-only mira-api route (only ``MIRA_ROUTES``); {} when it can't be reached or can't say."""
    if route not in MIRA_ROUTES:
        return {}
    try:
        with urllib.request.urlopen(_mira_request(route), timeout=6) as reply:
            data = json.loads(reply.read().decode("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


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


AWAY_GRACE = 120.0   # seconds after `argus companion away` before her own input counts as her being back


def _forced_away(folder: Path, idle: float, now: float) -> float:
    """`argus companion away`: away now, without waiting for the idle clock, until she's seen using this machine
    again (after a short grace, so the keystroke that ran the command doesn't cancel it)."""
    marker = folder / "away"
    try:
        age = now - marker.stat().st_mtime
    except OSError:
        return idle
    if age > AWAY_GRACE and idle < 30:
        marker.unlink(missing_ok=True)
        return idle
    return max(idle, presence.AWAY + 1)


def moment(folder: Path, last_tick: float = 0.0) -> presence.Moment:
    now = time.time()
    panel = _panel()
    # Each machine with a body has its own companion (winhvk runs its body and `argus companion run` too), so a machine
    # only offers moments while it's the one in use: an idle laphvk is "away" even when the camera sees Hannah at
    # winhvk, and winhvk's companion reaches her there. One Mira at a time, never two at once.
    idle = _idle_seconds(folder, now)
    idle = _forced_away(folder, idle, now)
    return presence.Moment(now=datetime.fromtimestamp(now), idle=idle,
                           busy=_fullscreen(folder) or bool(panel.get("busy")),
                           quiet=bool(panel.get("quiet")) or (folder / "quiet").exists(),
                           talked=_talked_since(folder, last_tick) or bool(panel.get("busy")))


AGENT_SAY = "http://127.0.0.1:32768/say"   # winhvk: MiraAgent speaks in MIRA's voice (MIRA Link)


def _speak(text: str, folder: Path | None = None) -> bool:
    """Out loud in MIRA's voice on this machine: laphvk's voice panel (it refuses while she's mid-conversation or
    quiet), or winhvk's MiraAgent (bearer MIRA_AGENT_TOKEN from the user's environment; skipped while quiet)."""
    if sys.platform == "win32":
        token = os.environ.get("MIRA_AGENT_TOKEN", "")
        if not token or (folder is not None and (folder / "quiet").exists()):
            return False
        request = urllib.request.Request(AGENT_SAY, data=json.dumps({"text": text}).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    else:
        request = urllib.request.Request(PANEL_SPEAK, data=json.dumps({"text": text}).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=3) as reply:
            return reply.status == 200
    except OSError:  # HTTPError (409 busy/quiet) is an OSError too
        return False


SHOW_WAIT = 5.0


def _show(text: str, kind: str) -> None:
    """*text* in her body's bubble here, through its hands port (the mira-body fork doesn't read ``say.json``). Shown
    only: her voice is MIRA's. Her body down, or busy with a chat, and nothing shows; the voice still carries it."""
    from . import relay
    relay.hands("show", {"text": text, "kind": kind}, timeout=SHOW_WAIT)


def say(folder: Path, text: str, kind: str = "say", aloud: bool = True, log: bool = True) -> None:
    """Show *text* in her body's bubble (``say.json``, atomic replace, a fresh id per line, and her body's hands port),
    say it out loud when MIRA's voice is free, and log it (her own words only: replies and the thinking dots aren't
    logged)."""
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "say.json.tmp"
    tmp.write_text(json.dumps({"id": f"{time.time_ns()}", "text": text, "kind": kind}), encoding="utf-8")
    os.replace(tmp, folder / "say.json")
    _show(text, kind)
    from . import prefs
    spoken = aloud and prefs.speaks(folder, "replies" if kind == "reply" else prefs.voice_kind(kind)) and _speak(text, folder)
    if log:
        with open(folder / "checkins.log", "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M} {kind}{' (aloud)' if spoken else ''}: {text}\n")


CHAT_TIMEOUT = 300.0
_asking = threading.Lock()


def answer(folder: Path, text: str) -> str:
    """Hannah typed to her body: a real Mira turn through her own backend (``backend.py``: her router, her tools,
    her companion session), and her reply in her bubble and out loud. While she thinks the bubble shows the dots."""
    if not _asking.acquire(blocking=False):
        say(folder, "One at a time, I'm still on your last one.", "reply", aloud=False, log=False)
        return ""
    try:
        from . import backend
        say(folder, "…", "thinking", aloud=False, log=False)
        reply, who = backend.call(text, max_tokens=1500, timeout=CHAT_TIMEOUT)
        logger.info("companion: Hannah's message answered by %s", who or "nobody")
        say(folder, reply or "Lost my train of thought there. Say that again?", "reply", log=False)
        return reply
    finally:
        _asking.release()


def _ask(folder: Path) -> tuple[str, str]:
    """What Hannah typed to her body (``ask.json``: {"id", "text"}): (id, text), or ("", "")."""
    try:
        data = json.loads((folder / "ask.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", ""
    return (str(data.get("id", "")), str(data.get("text", "")).strip()) if isinstance(data, dict) else ("", "")


def _remember(folder: Path, sched: presence.Scheduler) -> None:
    tmp = folder / "scheduler.json.tmp"
    tmp.write_text(json.dumps(sched.remember()), encoding="utf-8")
    os.replace(tmp, folder / "scheduler.json")


EVENT_KINDS = ("pat", "tossed", "poked", "woke")
BODY_TOGGLES = ("coach",)    # menu items on her body that flip a setting rather than ask her anything
EVENT_POLL = 2.0


def _event(folder: Path) -> tuple[str, str]:
    """The pet's latest touch (``event.json``: {"id", "kind"}): (id, kind), or ("", "") when there is none."""
    try:
        data = json.loads((folder / "event.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", ""
    return (str(data.get("id", "")), str(data.get("kind", ""))) if isinstance(data, dict) else ("", "")


COME_OVER = ("popin", "bored")   # like Capri's check-ins: she glitches over to the pointer before she says it


def body(folder: Path, action: str) -> None:
    """Tell her body to do something (``body.json``: {"id", "do"}); ``come_here`` also reaches the mira-body fork
    through its hands port, as her own move_yourself."""
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "body.json.tmp"
    tmp.write_text(json.dumps({"id": str(time.time_ns()), "do": action}), encoding="utf-8")
    os.replace(tmp, folder / "body.json")
    if action == "come_here":
        from . import relay
        relay.hands("do", {"tool": "move_yourself", "args": {"action": "come_here"}}, timeout=SHOW_WAIT)


def moment_now(folder: Path, kind: str, present_for, idle: float = 0.0, away_for=None, extra: str = "") -> str | None:
    """Offer Mira this moment; say what she chose to say. Her line, None when she passed, or "" when the moment was held
    (she passed on the same thing already, so she wasn't asked)."""
    from . import mind
    line = mind.ask(kind, present_for, folder, idle, where=where(folder), gaming=game_mode(),
                    away_for=away_for or timedelta(0), extra=extra)
    if line:
        if kind in COME_OVER:
            body(folder, "come_here")
            time.sleep(1.2)       # her glitch over lands before the bubble
        say(folder, line, kind)
    else:
        with open(folder / "checkins.log", "a", encoding="utf-8") as log:
            log.write(f"{datetime.now():%Y-%m-%d %H:%M} {kind} ({'held: nothing new' if line == '' else 'passed'})\n")
    return line


_thinking = threading.Lock()


def moment_soon(folder: Path, kind: str, present_for, idle: float = 0.0, away_for=None, extra: str = "") -> bool:
    """``moment_now`` off the ticker's loop: her mind can take minutes when the provider is slow, and Hannah's
    clicks (the menu, her room, coaching) must never wait on it. One at a time; while she's still thinking, a new
    moment passes (False)."""
    if not _thinking.acquire(blocking=False):
        logger.info("companion: %s moment passed (still thinking about the last one)", kind)
        return False

    def think() -> None:
        try:
            moment_now(folder, kind, present_for, idle, away_for, extra)
        except Exception:     # her moment failing never takes the ticker down
            logger.warning("companion: %s moment failed", kind, exc_info=True)
        finally:
            _thinking.release()

    from agent.memory_provider import spawn_context_thread
    spawn_context_thread(think, name=f"companion-{kind}").start()
    return True


def _coach(folder: Path):
    """Her chess coach (Stockfish + her eyes on the board), or None when it can't run here."""
    from . import chess_coach

    def react(kind: str, facts: str) -> None:
        m = moment(folder)
        if not m.quiet:
            moment_soon(folder, kind, timedelta(0), m.idle, extra=facts)

    try:
        return chess_coach.Coach(folder, lambda text: say(folder, text, "chess", aloud=False, log=False), react)
    except Exception:  # no Pillow, no display: she just doesn't do chess here
        logger.warning("companion: chess coach unavailable", exc_info=True)
        return None


def _chess_tick(folder: Path, coach, m: presence.Moment) -> None:
    """A chess board on screen: follow it, and the first time in a while let her offer to help."""
    if coach is None:
        return
    seen = coach.notice(active=m.idle < presence.AWAY)
    from . import prefs
    if seen and not m.quiet and not m.busy and prefs.allowed(folder, "chess"):
        moment_soon(folder, "chess", timedelta(0), m.idle, extra=seen[1])


REMINDER_EVERY = 120.0      # seconds between agenda reads


def due_reminders(agenda: dict, told: set[str]) -> list[str]:
    """Overdue reminders she hasn't been told about today, most urgent (lowest priority number) first."""
    out = [r for r in agenda.get("reminders") or [] if isinstance(r, dict) and r.get("overdue") and r.get("summary")
           and r["summary"] not in told]
    return [r["summary"] for r in sorted(out, key=lambda r: r.get("priority") or 9)]


def _reminder_tick(folder: Path, m: presence.Moment, last: list[float]) -> None:
    """A reminder of hers just went overdue and she's here: Mira says it her way (once per reminder per day)."""
    from . import prefs
    if m.idle >= presence.AWAY or m.quiet or m.busy or time.time() - last[0] < REMINDER_EVERY \
            or not prefs.allowed(folder, "reminder"):
        return
    last[0] = time.time()
    path, today = folder / "reminded.json", datetime.now().strftime("%Y-%m-%d")
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    told = set(saved.get(today, []))
    due = due_reminders(mira("cockpit/agenda"), told)
    if not due:
        return
    path.write_text(json.dumps({today: sorted(told | {due[0]})}), encoding="utf-8")
    facts = f"Her reminder \"{due[0]}\" is now overdue." + (
        f" Also overdue: {', '.join(due[1:4])}." if len(due) > 1 else "")
    moment_soon(folder, "reminder", timedelta(0), m.idle, extra=facts)


GAME_BREAK = 2 * 3600.0     # a game stretch this long earns a nudge
GAME_GAP = 300.0            # out of the game this long ends a stretch


class GameClock:
    """How long she's been in a game (fullscreen or winhvk's Game Mode) without a real break, and whether that
    stretch has had its break nudge yet."""

    def __init__(self):
        self.since: float | None = None
        self.last_seen = 0.0
        self.nudged = False

    def due(self, now: float, gaming: bool) -> bool:
        if gaming:
            if self.since is None or now - self.last_seen > GAME_GAP:
                self.since, self.nudged = now, False
            self.last_seen = now
        if self.since is None or self.nudged or not gaming or now - self.since < GAME_BREAK:
            return False
        self.nudged = True
        return True


def _game_break_tick(folder: Path, m: presence.Moment, clock: GameClock) -> None:
    gaming = m.idle < presence.AWAY and (_fullscreen(folder) or game_mode())
    from . import prefs
    if clock.due(m.now.timestamp(), gaming) and not m.quiet and prefs.allowed(folder, "game_break"):
        hours = (m.now.timestamp() - clock.since) / 3600
        moment_soon(folder, "game_break", timedelta(0), m.idle,
                   extra=f"She's been gaming for about {hours:.1f} hours without a break (focused: {mind_window(folder)}).")


def mind_window(folder: Path) -> str:
    try:
        return str(json.loads((folder / "state.json").read_text(encoding="utf-8")).get("window") or "a game")
    except (OSError, ValueError):
        return "a game"


def _room(folder: Path):
    """Her games room (a local page): tic-tac-toe, connect four, rock paper scissors, chess against her."""
    from . import room

    def react(facts: str) -> None:
        m = moment(folder)
        if not m.quiet:
            moment_now(folder, "game", timedelta(0), m.idle, extra=facts)

    try:
        games = room.Room(folder, react)
        games.start()
        return games
    except OSError:  # the port's taken (another companion here): no room this run
        logger.warning("companion: games room unavailable", exc_info=True)
        return None


class VoiceCaptions:
    """MIRA's spoken replies on this machine (her voice conversations, in the voice agent's feed) shown in her
    body's bubble as she says them: one Mira, voice and body. Captions only - never spoken a second time."""

    def __init__(self, feed: Path):
        self.feed = feed
        self.mtime = 0.0
        self.since = datetime.now().timestamp()

    def new_lines(self) -> list[str]:
        try:
            mtime = self.feed.stat().st_mtime
        except OSError:
            return []
        if mtime == self.mtime:
            return []
        self.mtime = mtime
        from . import mind
        lines = []
        for stamp, line in mind.mira_feed(datetime.now().timestamp(), hours=1, path=self.feed):
            if stamp > self.since and "] You (voice): " in line:
                lines.append(line.split("] You (voice): ", 1)[1])
                self.since = stamp
        return lines


def _toggle_coach(folder: Path) -> None:
    from . import chess_coach
    on = not chess_coach.settings(folder)["coach"]
    chess_coach.set_coach(folder, on)
    say(folder, f"▸ chess coaching {'on' if on else 'off'}", "chess", aloud=False, log=False)


def run(folder: Path | None = None, tick: float = TICK) -> None:
    """Tick until interrupted. Talking to Mira (an ARGUS turn, or MIRA's voice busy) counts for ``bored``."""
    folder = folder or companion_dir()
    folder.mkdir(parents=True, exist_ok=True)
    # No `back`: MIRA already greets Hannah on her return (winhvk's camera presence -> mira-api's spoken greeting).
    from . import prefs
    sched = presence.Scheduler(prefs.scheduler_settings(folder))
    try:
        sched.recall(json.loads((folder / "scheduler.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    last_tick = 0.0
    seen_event = _event(folder)[0]   # what was already there when she started isn't news
    seen_ask = _ask(folder)[0]
    coach = _coach(folder)
    _room(folder)
    from . import link, relay
    host = "winhvk" if sys.platform == "win32" else "laphvk"
    link.start(folder, host)
    relay.start(host, folder)
    from . import bridge
    bridge.start(folder)
    from . import skills_sync     # her body's skill mods into MIRA's own skill store on debhvk
    skills_sync.start(relay.body_folder(), host, folder)
    if sys.platform == "win32":       # "Hey Mira" with HavoK's own wake model; laphvk's voice (mira-agent) hears it there
        from . import wake
        wake.start(relay.body_folder())
    if sys.platform != "win32":       # winhvk's body listens for music itself
        from agent.memory_provider import spawn_context_thread

        from . import ears
        spawn_context_thread(ears.listen, name="mira-ears", args=(folder, lambda: link.local_music(folder)["playing"])).start()
    reminder_read = [0.0]
    game_clock = GameClock()
    from . import mind
    captions = VoiceCaptions(mind.MIRA_FEED) if sys.platform != "win32" else None
    while True:
        ask_id, text = _ask(folder)
        if ask_id and ask_id != seen_ask:
            seen_ask = ask_id
            if text:
                threading.Thread(target=answer, args=(folder, text), name="companion-answer", daemon=True).start()
        event_id, kind = _event(folder)
        if event_id and event_id != seen_event:
            seen_event = event_id
            if kind == "coach":
                _toggle_coach(folder)
            elif kind in ("play", "settings"):
                from . import room
                room.open_window(folder, "settings" if kind == "settings" else "")
            elif kind in EVENT_KINDS:
                m = moment(folder, last_tick)
                if not m.quiet:
                    moment_soon(folder, kind, timedelta(0), m.idle)
        for line in captions.new_lines() if captions else []:
            say(folder, line, "voice", aloud=False, log=False)
        if time.time() - last_tick >= tick:
            m = moment(folder, last_tick)
            last_tick = time.time()
            _chess_tick(folder, coach, m)
            _reminder_tick(folder, m, reminder_read)
            _game_break_tick(folder, m, game_clock)
            sched.settings = prefs.scheduler_settings(folder)     # the settings tab applies at once
            opening = sched.tick(m)
            if opening:
                _remember(folder, sched)
                moment_soon(folder, opening.kind, opening.present_for, m.idle, opening.away_for)
        time.sleep(EVENT_POLL)
