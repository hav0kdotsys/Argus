"""Mira's games room: tic-tac-toe, connect four, rock paper scissors and chess against her, in a small window.

Served by the companion on 127.0.0.1 only, behind a token made each run (``room.json`` holds the port and token for
``argus companion play``). The little games run in the page; chess is Stockfish's on both sides of the rules: it
lists the legal moves (so the page never needs a chess library) and plays her moves at the level Hannah picks.
Every finished game is a moment for Mira to react to in her own words.
"""

from __future__ import annotations

import json
import logging
import secrets
import shutil
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import chess_board as cb

logger = logging.getLogger(__name__)

PORT = 8771
GAMES = ("chess", "tictactoe", "connect4", "rps")
LEVELS = {"easy": 1320, "medium": 1700, "hard": 2200, "max": None}
PAGE = Path(__file__).with_name("room.html")


def status(engine, fen: str) -> tuple[list[str], str]:
    """Legal moves and how the game stands: "play", "checkmate" or "stalemate"."""
    legal = engine.legal(fen)
    if legal:
        return legal, "play"
    return legal, "checkmate" if engine.in_check(fen) else "stalemate"


def chess_turn(engine, fen: str, move: str, level: str) -> dict:
    """Hannah's move, then Mira's reply: the positions after each, and how the game stands."""
    legal = engine.legal(fen)
    if move not in legal:
        return {"error": "illegal", "fen": fen, "legal": legal, "status": "play"}
    after = engine.fen_after(fen, [move])
    legal, state = status(engine, after)
    reply = {"fen": after, "legal": legal, "status": state, "mine": cb.readable(fen, move)}
    if state != "play":
        return reply
    hers = engine.play(after, LEVELS.get(level, 1700))
    if not hers:
        return reply
    final = engine.fen_after(after, [hers])
    legal, state = status(engine, final)
    reply.update({"fen": final, "legal": legal, "status": state, "hers": hers, "hers_text": cb.readable(after, hers)})
    return reply


class Room:
    def __init__(self, folder: Path, react):
        """``react(facts)`` hands a finished game to Mira."""
        from .chess_engine import Engine, find_engine
        self.folder, self.react = folder, react
        path = find_engine()
        self.engine = Engine(path) if path else None
        self.token = secrets.token_urlsafe(16)
        self.server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        room = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def _send(self, code: int, body, kind: str = "application/json") -> None:
                data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def _allowed(self) -> bool:
                url = urlparse(self.path)
                return parse_qs(url.query).get("t", [""])[0] == room.token

            def do_GET(self):
                if not self._allowed():
                    return self._send(403, {"error": "no"})
                url = urlparse(self.path)
                if url.path == "/":
                    return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                if url.path == "/api/chess/new":
                    q = parse_qs(url.query)
                    return self._send(200, room.chess_new(q.get("color", ["w"])[0], q.get("level", ["medium"])[0]))
                return self._send(404, {"error": "not here"})

            def do_POST(self):
                if not self._allowed():
                    return self._send(403, {"error": "no"})
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._send(400, {"error": "bad json"})
                path = urlparse(self.path).path
                if path == "/api/chess/move":
                    if room.engine is None:
                        return self._send(503, {"error": "no chess engine on this machine"})
                    return self._send(200, chess_turn(room.engine, str(body.get("fen", "")), str(body.get("move", "")),
                                                      str(body.get("level", "medium"))))
                if path == "/api/result":
                    room.finished(body)
                    return self._send(200, {"ok": True})
                return self._send(404, {"error": "not here"})

        self.server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        (self.folder / "room.json").write_text(json.dumps({"port": PORT, "token": self.token}), encoding="utf-8")
        from agent.memory_provider import spawn_context_thread
        spawn_context_thread(self.server.serve_forever, name="mira-room").start()

    def chess_new(self, color: str, level: str) -> dict:
        if self.engine is None:
            return {"error": "no chess engine on this machine"}
        fen = cb.START_FEN
        reply = {"fen": fen, "status": "play", "level": level}
        if color == "b":           # she plays White, so she opens
            hers = self.engine.play(fen, LEVELS.get(level, 1700))
            fen = self.engine.fen_after(fen, [hers]) if hers else fen
            reply.update({"fen": fen, "hers": hers, "hers_text": cb.readable(cb.START_FEN, hers) if hers else ""})
        reply["legal"] = self.engine.legal(fen)
        return reply

    def finished(self, body: dict) -> None:
        game = str(body.get("game", ""))
        if game not in GAMES:
            return
        result = str(body.get("result", ""))[:20]
        score = str(body.get("score", ""))[:40]
        detail = str(body.get("detail", ""))[:200]
        names = {"chess": "chess", "tictactoe": "tic-tac-toe", "connect4": "connect four", "rps": "rock paper scissors"}
        outcome = {"win": "Hannah beat you", "loss": "you beat Hannah", "draw": "it was a draw"}.get(result, result)
        facts = f"You just played {names[game]} with her on your games board: {outcome}."
        if score:
            facts += f" Score this session: {score}."
        if detail:
            facts += f" {detail}"
        from agent.memory_provider import spawn_context_thread
        spawn_context_thread(self.react, name="mira-room-react", args=(facts,)).start()


def url(folder: Path, game: str = "") -> str | None:
    try:
        data = json.loads((folder / "room.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return f"http://127.0.0.1:{data['port']}/?t={data['token']}" + (f"#{game}" if game in GAMES else "")


def open_window(folder: Path, game: str = "") -> bool:
    """Her board in its own window: an Edge app window on Windows, a Firefox window with its own profile (so it
    isn't one of her tabs) on Linux."""
    address = url(folder, game)
    if not address:
        return False
    if sys.platform == "win32":
        for edge in (Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                     Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")):
            if edge.exists():
                subprocess.Popen([str(edge), f"--app={address}", "--window-size=760,820"])
                return True
    firefox = shutil.which("firefox")
    if firefox:
        profile = folder / "room-browser"
        profile.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([firefox, "--no-remote", "--profile", str(profile), "--class", "MiraRoom", "--name", "MiraRoom",
                          "--new-window", address], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    return webbrowser.open(address)
