"""MIRA's link between her bodies: one Mira across laphvk and winhvk, not two pets.

What crosses (and nothing else): what's playing on each machine (music on either and she dances on both, on the
beat the playing machine hears), the switches Hannah would expect to be hers rather than a machine's (quiet, chess
coaching, the settings tab - the newest change wins), body moves aimed at the other machine (``argus companion
body --there hop_in``), and her body's own lines (``words.json``, which MIRA writes when a body asks: the newer set
crosses and merges, so one ask a day serves both bodies).

laphvk's companion serves the link on 127.0.0.1:8772; winhvk's reaches it through laphvk's SSH reverse tunnel
(``mira-link.service``: laphvk already SSHes to winhvk, so no new port is opened anywhere). Every exchange is one POST:
each side sends its report and gets the other's back. ``link-token`` (made on laphvk, copied file to file to winhvk)
must ride in the ``X-Mira-Link`` header, which a web page can't send to a local port without being refused.

Each side writes what it hears to ``link.json`` for its body: {"peer", "at", "music": {...}}.
"""

from __future__ import annotations

import json
import logging
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logger = logging.getLogger(__name__)

PORT = 8772
EVERY = 3.0          # seconds between exchanges
FRESH = 15.0         # a report older than this is stale (the other machine asleep, the tunnel down)
HEADER = "X-Mira-Link"


# ---------------------------------------------------------------- what's playing here

def parse_track(track: str) -> dict:
    """winhvk's body reports ``"Artist - Title [Playing]"`` (or ``[Paused]``, or "") in state.json."""
    track = (track or "").strip()
    playing = track.endswith("[Playing]")
    track = track.removesuffix(" [Playing]").removesuffix(" [Paused]")
    artist, _, title = track.partition(" - ") if " - " in track else ("", "", track)
    return {"playing": playing and bool(track), "artist": artist, "title": title}


def _mpris() -> dict:
    """laphvk: the first MPRIS player that's playing (playerctl), or not playing."""
    playerctl = shutil.which("playerctl")
    if not playerctl:
        return {"playing": False, "artist": "", "title": ""}
    out = subprocess.run([playerctl, "-a", "metadata", "--format", "{{status}}\t{{artist}}\t{{title}}"],
                         capture_output=True, text=True, timeout=5, check=False).stdout
    for row in out.splitlines():
        status, _, rest = row.partition("\t")
        artist, _, title = rest.partition("\t")
        if status == "Playing":
            return {"playing": True, "artist": artist, "title": title}
    return {"playing": False, "artist": "", "title": ""}


def beat(folder: Path) -> dict:
    """This machine's beat lock (``beat.json`` from her ears: {"bpm", "beat_at"}), {} when there's none fresh."""
    try:
        data = json.loads((folder / "beat.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or time.time() - float(data.get("at", 0)) > FRESH or not data.get("bpm"):
        return {}
    return {"bpm": float(data["bpm"]), "beat_at": float(data["beat_at"])}


def local_music(folder: Path) -> dict:
    if sys.platform == "win32":
        from .ticker import body_state
        music = parse_track(str(body_state(folder).get("playing") or ""))
    else:
        music = _mpris()
    if music["playing"]:
        music.update(beat(folder))
    return music


# ---------------------------------------------------------------- Hannah's switches (newest change wins)

def _quiet_get(folder: Path):
    return (folder / "quiet").exists()


def _quiet_set(folder: Path, on) -> None:
    quiet = folder / "quiet"
    if on:
        quiet.write_text("quiet", encoding="utf-8")
    else:
        quiet.unlink(missing_ok=True)


def _coach_get(folder: Path):
    from . import chess_coach
    s = chess_coach.settings(folder)
    return [s["coach"], s["bot"]]


def _coach_set(folder: Path, value) -> None:
    from . import chess_coach
    chess_coach.set_coach(folder, bool(value[0]), bool(value[1]))


def _settings_get(folder: Path):
    from . import prefs
    return prefs.load(folder)


def _settings_set(folder: Path, value) -> None:
    from . import prefs
    prefs.save(folder, value if isinstance(value, dict) else {})


SHARED = {"quiet": (_quiet_get, _quiet_set), "coach": (_coach_get, _coach_set),
          "settings": (_settings_get, _settings_set)}


class Switches:
    """Each switch's value and when Hannah last changed it (``link-switches.json``). A value seen for the first time
    is recorded as changed at 0, so a machine coming up never overrides a real change made on the other."""

    def __init__(self, folder: Path):
        self.folder = folder
        try:
            self.known = json.loads((folder / "link-switches.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.known = {}
        if not isinstance(self.known, dict):
            self.known = {}

    def _save(self) -> None:
        tmp = self.folder / "link-switches.json.tmp"
        tmp.write_text(json.dumps(self.known), encoding="utf-8")
        tmp.replace(self.folder / "link-switches.json")

    def report(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        changed = False
        for name, (get, _set) in SHARED.items():
            value = get(self.folder)
            seen = self.known.get(name)
            if not isinstance(seen, dict):
                self.known[name] = {"v": value, "at": 0}
                changed = True
            elif seen.get("v") != value:
                self.known[name] = {"v": value, "at": now}
                changed = True
        if changed:
            self._save()
        return dict(self.known)

    def take(self, theirs: dict) -> list[str]:
        """Apply the other machine's newer changes here; the names applied."""
        applied = []
        for name, (_get, put) in SHARED.items():
            rec, mine = theirs.get(name), self.known.get(name) or {"v": None, "at": 0}
            if not isinstance(rec, dict) or "v" not in rec:
                continue
            if float(rec.get("at", 0)) > float(mine.get("at", 0)) and rec["v"] != mine.get("v"):
                put(self.folder, rec["v"])
                self.known[name] = {"v": rec["v"], "at": float(rec["at"])}
                applied.append(name)
        if applied:
            self._save()
        return applied


# ---------------------------------------------------------------- moves for the other body

def send_there(folder: Path, action: str) -> None:
    """Queue a body move for the other machine (sent with the next exchange)."""
    tmp = folder / "link-out.json.tmp"
    tmp.write_text(json.dumps({"id": str(time.time_ns()), "do": action}), encoding="utf-8")
    tmp.replace(folder / "link-out.json")


def _outbox(folder: Path) -> dict | None:
    try:
        data = json.loads((folder / "link-out.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or time.time_ns() - int(data.get("id", 0)) > FRESH * 4 * 1e9:
        return None      # a move nobody delivered in a minute is no longer wanted
    return data


# ---------------------------------------------------------------- the exchange

def token(folder: Path, make: bool = False) -> str:
    path = folder / "link-token"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        if not make:
            return ""
    value = secrets.token_urlsafe(24)
    path.write_text(value, encoding="utf-8")
    return value


class Words:
    """Her body's lines on this machine (``words.json`` in the body's folder), shared across the link. Each report
    carries their fingerprint; the lines themselves cross only while the other side's fingerprint differs. A newer set
    from there merges in (its lines win, a moment only this body has stays) and is written in one fixed order, so both
    sides settle on the same file and stop sending. The merged file is fresh to the body, so it doesn't ask MIRA again."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self.peer = None            # the other side's last fingerprint

    def _path(self) -> Path:
        if self.path is None:
            from .relay import body_folder
            return body_folder() / "words.json"
        return self.path

    def _read(self) -> tuple[dict, str, float] | None:
        path = self._path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            at = path.stat().st_mtime
        except (OSError, ValueError):
            return None
        lines = {str(k): [str(x) for x in v] for k, v in data.items() if isinstance(v, list)} if isinstance(data, dict) else {}
        return (lines, _fingerprint(lines), at) if lines else None

    def report(self) -> dict:
        mine = self._read()
        if mine is None:
            return {}
        lines, sha, at = mine
        out = {"sha": sha, "at": at}
        if self.peer is not None and self.peer != sha:
            out["lines"] = lines
        return out

    def take(self, theirs: dict) -> bool:
        """Their words report; True when a newer set from there was merged into this body's file."""
        if not isinstance(theirs, dict) or not theirs.get("sha"):
            return False
        self.peer = str(theirs["sha"])
        lines = theirs.get("lines")
        if not isinstance(lines, dict):
            return False
        mine = self._read()
        if mine is not None and float(theirs.get("at") or 0) <= mine[2]:
            return False                       # ours is the newer set: ours goes to them instead
        merged = dict(mine[0]) if mine else {}
        merged.update({str(k): [str(x) for x in v][:20] for k, v in lines.items() if isinstance(v, list)})
        if mine is not None and _fingerprint(merged) == mine[1]:
            return False
        path = self._path()
        tmp = path.with_name(path.name + ".link")
        tmp.write_text(_canonical(merged), encoding="utf-8")
        tmp.replace(path)
        return True


def _canonical(lines: dict) -> str:
    return json.dumps(lines, sort_keys=True, ensure_ascii=False)


def _fingerprint(lines: dict) -> str:
    import hashlib
    return hashlib.sha1(_canonical(lines).encode("utf-8")).hexdigest()


class Link:
    def __init__(self, folder: Path, here: str):
        self.folder, self.here = folder, here
        self.switches = Switches(folder)
        self.words = Words()
        self.done_moves: set[str] = set()
        self.heard_at = 0.0
        self.clock = 0.0       # winhvk: laphvk's clock minus this one, from each exchange's round trip

    def report(self) -> dict:
        return {"host": self.here, "at": time.time(), "music": local_music(self.folder),
                "switches": self.switches.report(), "move": _outbox(self.folder), "words": self.words.report()}

    def hear(self, theirs: dict, shift: float = 0.0) -> None:
        """The other body's report: what's playing there for this body, their switch changes, a move for here.
        ``shift`` turns their clock into ours (their beat falls on our beat)."""
        if not isinstance(theirs, dict):
            return
        from .ticker import body
        self.heard_at = time.time()
        music = dict(theirs["music"]) if isinstance(theirs.get("music"), dict) else {}
        if isinstance(music.get("beat_at"), (int, float)):
            music["beat_at"] = float(music["beat_at"]) + shift
        tmp = self.folder / "link.json.tmp"
        tmp.write_text(json.dumps({"peer": str(theirs.get("host", ""))[:40], "at": self.heard_at, "music": music}),
                       encoding="utf-8")
        tmp.replace(self.folder / "link.json")
        if isinstance(theirs.get("switches"), dict):
            applied = self.switches.take(theirs["switches"])
            if applied:
                logger.info("companion link: %s changed on %s", ", ".join(applied), theirs.get("host"))
        if isinstance(theirs.get("words"), dict) and self.words.take(theirs["words"]):
            logger.info("companion link: her body's lines came over from %s", theirs.get("host"))
        move = theirs.get("move")
        if isinstance(move, dict) and move.get("id") and str(move["id"]) not in self.done_moves:
            self.done_moves.add(str(move["id"]))
            if len(self.done_moves) > 64:
                self.done_moves = set(sorted(self.done_moves)[-16:])
            body(self.folder, str(move.get("do", ""))[:80])

    def delivered(self, theirs: dict) -> None:
        """Our queued move made it across once they've echoed its id."""
        sent = _outbox(self.folder)
        if sent and str(sent.get("id")) in (theirs.get("got") or []):
            (self.folder / "link-out.json").unlink(missing_ok=True)

    # laphvk: serve
    def serve(self) -> ThreadingHTTPServer:
        link, secret = self, token(self.folder, make=True)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_POST(self):
                if self.path != "/link" or not secrets.compare_digest(self.headers.get(HEADER, ""), secret):
                    self.send_response(403)
                    self.end_headers()
                    return
                try:
                    theirs = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                except ValueError:
                    theirs = {}
                clock = theirs.get("clock") if isinstance(theirs, dict) else 0
                link.hear(theirs, float(clock) if isinstance(clock, (int, float)) else 0.0)
                link.delivered(theirs)
                mine = link.report()
                mine["got"] = sorted(link.done_moves)[-8:]
                data = json.dumps(mine).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        from agent.memory_provider import spawn_context_thread
        spawn_context_thread(server.serve_forever, name="mira-link").start()
        return server

    # winhvk: call
    def exchange(self) -> bool:
        secret = token(self.folder)
        if not secret:
            return False
        mine = self.report()
        mine["got"] = sorted(self.done_moves)[-8:]
        mine["clock"] = self.clock
        sent = time.time()
        request = urllib.request.Request(f"http://127.0.0.1:{PORT}/link", data=json.dumps(mine).encode("utf-8"),
                                         headers={HEADER: secret, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=6) as reply:
                theirs = json.loads(reply.read().decode("utf-8"))
        except (OSError, ValueError):
            return False
        back = time.time()
        if isinstance(theirs.get("at"), (int, float)) and back - sent < 1.0:
            seen = float(theirs["at"]) - (sent + back) / 2
            self.clock = seen if not self.clock else self.clock * 0.8 + seen * 0.2
        self.hear(theirs, -self.clock)
        self.delivered(theirs)
        return True

    def call_forever(self) -> None:
        while True:
            try:
                self.exchange()
            except Exception:   # one bad exchange never ends the link
                logger.warning("companion link: exchange failed", exc_info=True)
            time.sleep(EVERY)


def start(folder: Path, here: str) -> Link | None:
    """laphvk serves, winhvk calls. None when the port's taken (another companion here)."""
    link = Link(folder, here)
    if sys.platform == "win32":
        from agent.memory_provider import spawn_context_thread
        spawn_context_thread(link.call_forever, name="mira-link").start()
        return link
    try:
        link.serve()
    except OSError:
        logger.warning("companion link: port %s taken; no link this run", PORT)
        return None
    return link


def status(folder: Path) -> str:
    try:
        data = json.loads((folder / "link.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "never heard the other body"
    age = time.time() - float(data.get("at", 0))
    music = data.get("music") or {}
    playing = f"playing {music.get('artist', '')} - {music.get('title', '')}".strip(" -") if music.get("playing") else "no music"
    state = "linked" if age < FRESH else f"last heard {age / 60:.0f} min ago"
    return f"{state} with {data.get('peer') or 'the other body'} ({playing})"
