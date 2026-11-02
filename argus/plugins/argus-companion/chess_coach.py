"""Mira in Hannah's corner at the chess board: she notices a game, offers to help, and when Hannah wants it, follows
the game move by move with a real engine (Stockfish), her own reactions on the big moments.

- Seeing the board: a chess.com / lichess window that's visible right now (laphvk: Hyprland's clients on the shown
  workspaces; winhvk: top-level windows). The position comes off the screen (``chess_eyes``), exact, every second.
- Fair play: engine help in a live game against a person is cheating on both sites and gets accounts closed. The
  window title tells the modes apart; against the computer, a coach, analysis, puzzles and lessons she coaches live;
  anywhere else she only offers to go over the game afterwards, unless Hannah says it's a bot (``--bot``).
- What she says: the best move, its score and line are the ENGINE's and go in the bubble as a readout ("▸"). Her own
  words (an offer, a blunder, a gift, a mate, the end) come from asking her, like every other moment.
- ``chess-now.json`` holds the latest position and engine lines for her ARGUS turns (``pre_llm_call``), so "why
  that move?" is answered from the engine, not a guess.
"""

from __future__ import annotations

import io
import json
import logging
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import chess_board as cb

logger = logging.getLogger(__name__)

SITES = re.compile(r"chess\.com|lichess", re.IGNORECASE)
SAFE = re.compile(r"computer|stockfish|\bbots?\b|coach|analys|puzzle|lesson|practice|training|study|learn|explorer|"
                  r"drill|endgame|opening", re.IGNORECASE)
STEP = 1.2               # seconds between looks while coaching
IDLE_STEP = 4.0          # ... and while only keeping track (coaching off)
SETTLE = 2               # the same position this many looks in a row before it counts (pieces mid-animation)
REACT_GAP = 40.0         # seconds between two of her reactions
BLUNDER = 150            # centipawns lost by one move that make a mistake worth a word
OFFER_AGAIN = 30 * 60.0  # a board seen again after this long earns another offer


@dataclass(frozen=True)
class Board:
    host: str
    title: str
    box: tuple[int, int, int, int]      # left, top, right, bottom on the screen
    handle: str = ""

    @property
    def live(self) -> bool:
        """Possibly a live game against a person: on a chess site, and not a mode the title says is safe."""
        return not SAFE.search(self.title)


def _hypr_boards() -> list[Board]:
    try:
        def hypr(what):
            return json.loads(subprocess.run(["hyprctl", what, "-j"], capture_output=True, text=True, check=False,
                                             timeout=3).stdout or "[]")
        clients, monitors = hypr("clients"), hypr("monitors")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    shown = {m.get("activeWorkspace", {}).get("id") for m in monitors}
    shown |= {m.get("specialWorkspace", {}).get("id") for m in monitors if m.get("specialWorkspace", {}).get("id")}
    out = []
    for c in clients:
        title = c.get("title") or ""
        if not (SITES.search(title) or str(c.get("class", "")).startswith("WebApp-Chess")):
            continue
        if c.get("workspace", {}).get("id") not in shown or c.get("hidden"):
            continue
        (x, y), (w, h) = c.get("at", (0, 0)), c.get("size", (0, 0))
        out.append((c.get("focusHistoryID", 99), Board("laphvk", title, (x, y, x + w, y + h), c.get("address", ""))))
    return [b for _, b in sorted(out, key=lambda t: t[0])]


def _win_boards() -> list[Board]:
    import ctypes
    from ctypes import wintypes
    user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except OSError:
        pass
    found: list[tuple[int, Board]] = []
    foreground = user32.GetForegroundWindow()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if SITES.search(buf.value):
            rect = wintypes.RECT()
            if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:   # extended frame
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
            found.append((0 if hwnd == foreground else 1,
                          Board("winhvk", buf.value, (rect.left, rect.top, rect.right, rect.bottom), str(hwnd))))
        return True

    user32.EnumWindows(visit, 0)
    return [b for _, b in sorted(found, key=lambda t: t[0])]


def on_screen(board: Board, shot_size: tuple[int, int], box) -> tuple[int, int, int, int]:
    """The board's squares (``box`` in the screenshot) in screen coordinates, the bodies' own: the screenshot may be
    in physical pixels and the window's box in logical ones."""
    left, top, right, bottom = board.box
    sx, sy = (right - left) / max(1, shot_size[0]), (bottom - top) / max(1, shot_size[1])
    return (round(left + box[0] * sx), round(top + box[1] * sy), round(left + box[2] * sx), round(top + box[3] * sy))


def arrow(folder: Path, what: dict | None) -> None:
    """The engine's move as an arrow over the board (``arrow.json`` for her body): {"box", "from", "to",
    "white_bottom", "id", "at"}, or cleared. Unchanged files aren't rewritten."""
    path = folder / "arrow.json"
    data = {**what, "id": f"{what['from']}{what['to']}{what['box']}", "at": time.time()} if what else {"at": 0}
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = None
    if isinstance(old, dict) and old.get("id") == data.get("id") and (what or not old.get("at")):
        return
    tmp = folder / "arrow.json.tmp"
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


def boards() -> list[Board]:
    """Chess boards Hannah can see right now on this machine, the one she's most likely using first."""
    return _win_boards() if sys.platform == "win32" else _hypr_boards()


def capture(board: Board):
    """A screenshot of the board's window."""
    from PIL import Image
    left, top, right, bottom = board.box
    if sys.platform == "win32":
        from PIL import ImageGrab
        return ImageGrab.grab(bbox=board.box, all_screens=True)
    run = subprocess.run(["grim", "-g", f"{left},{top} {right - left}x{bottom - top}", "-t", "ppm", "-"],
                         capture_output=True, timeout=5, check=False)
    return Image.open(io.BytesIO(run.stdout)) if run.returncode == 0 and run.stdout else None


# ---------------------------------------------------------------------------------------------------------------
# What she knows about the coach, between processes (CLI, ticker, her turns)


def settings(folder: Path) -> dict:
    try:
        data = json.loads((folder / "chess.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"coach": bool(data.get("coach")), "bot": bool(data.get("bot")), "at": data.get("at", 0)}


def set_coach(folder: Path, on: bool, bot: bool = False) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "chess.json").write_text(json.dumps({"coach": on, "bot": bot and on, "at": time.time()}),
                                       encoding="utf-8")
    if not on:
        arrow(folder, None)


def now_state(folder: Path, fresh: float = 600.0) -> dict | None:
    try:
        data = json.loads((folder / "chess-now.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if time.time() - data.get("at", 0) < fresh else None


def turn_context(folder: Path) -> str:
    """For her ARGUS turns: the board she can see and what the engine says about it."""
    state = now_state(folder)
    if not state:
        return ""
    coach = settings(folder)
    lines = [f"[Chess] Hannah has a chess board open on {state['host']} ({state['title']})."]
    if state.get("live") and not coach["bot"]:
        lines.append("It may be a live game against a person: engine help there is cheating and gets her account "
                     "closed, so you don't give moves mid-game - offer to go through it with her afterwards. If she "
                     "says it's a bot, `argus companion chess on --bot` lets you coach.")
    else:
        lines.append(f"Your coaching is {'ON' if coach['coach'] else 'off'} (switch with `argus companion chess on` "
                     "/ `off` in the terminal).")
    if state.get("fen"):
        lines.append(f"Position (FEN): {state['fen']} - she plays {'White' if state.get('her') == 'w' else 'Black'}.")
    if state.get("best"):
        lines.append(f"Stockfish 19: best {state['best']} ({state['score']} for her), line {state.get('line', '')}."
                     + (f" Alternatives: {state['alts']}." if state.get("alts") else ""))
    lines.append("Engine numbers are exact; explain the ideas behind them in your own words.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------------------
# Following a game


class Coach:
    def __init__(self, folder: Path, say, react):
        """``say(text)`` puts a readout in her bubble; ``react(kind, facts)`` asks Mira for a moment of her own."""
        from .chess_engine import Engine, find_engine
        from .chess_eyes import Eyes
        self.folder, self.say, self.react = folder, say, react
        path = find_engine()
        self.engine = Engine(path) if path else None
        self.eyes = Eyes(folder)
        self.last_fen = ""
        self.pending = ("", 0)
        self.her_eval: int | None = None
        self.last_react = 0.0
        self.told_unlearnt = False
        self.offered: dict[str, float] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.screen_box: tuple[int, int, int, int] | None = None    # where the board's squares are on the screen

    # -- the loop --------------------------------------------------------------------------------------------
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running():
            return
        self._stop.clear()
        from agent.memory_provider import spawn_context_thread
        self._thread = spawn_context_thread(self._loop, name="mira-chess")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        gone_since = None
        while not self._stop.is_set():
            seen = boards()
            if not seen:
                arrow(self.folder, None)
                gone_since = gone_since or time.time()
                if time.time() - gone_since > 120:
                    break       # the board's been closed a while: the ticker starts us again when one shows up
                self._stop.wait(3)
                continue
            gone_since = None
            try:
                self.look(seen[0])
            except Exception:   # one bad frame must not end the game for her
                logger.warning("companion: chess look failed", exc_info=True)
            self._stop.wait(STEP if settings(self.folder)["coach"] else IDLE_STEP)

    # -- one look --------------------------------------------------------------------------------------------
    def look(self, board: Board) -> None:
        shot = capture(board)
        if shot is None:
            return
        read = self.eyes.read(shot, fallback_turn="w")
        if not read["found"]:
            return
        self.screen_box = on_screen(board, shot.size, read["box"])
        if not read["learnt"]:
            if not self.told_unlearnt:
                self.told_unlearnt = True
                self.say("▸ new board style: show me a starting position once and I'll read it from then on")
            return
        fen = read["fen"]
        placement = fen.split()[0]
        if placement != self.pending[0]:
            self.pending = (placement, 1)
            return
        self.pending = (placement, self.pending[1] + 1)
        if self.pending[1] < SETTLE or fen == self.last_fen:
            return
        new_game = read.get("start") and not self.last_fen.startswith(cb.START)
        self.last_fen = fen
        self.position(board, fen, "w" if read.get("white_bottom", True) else "b", new_game)

    def position(self, board: Board, fen: str, her: str, new_game: bool) -> None:
        coach = settings(self.folder)
        live_block = board.live and not coach["bot"]
        state = {"host": board.host, "title": board.title, "fen": fen, "her": her, "live": board.live,
                 "at": time.time()}
        arrow(self.folder, None)    # the last arrow was for the last position
        if live_block or self.engine is None or not coach["coach"]:
            self._write(state)      # no engine unless she asked for it, and never on a live game against a person
            return
        analysis = self.engine.analyse(fen)
        best = analysis.best
        mover = cb.to_move(fen)
        if best is None:
            self._write(state)
            self._react("chess_over", f"The game on {board.host} is over on the board: "
                                      f"{'checkmate' if self.engine.in_check(fen) else 'stalemate'}.")
            self.her_eval = None
            return
        mine = mover == her
        sign = 1 if mine else -1
        her_cp = (best.cp * sign) if best.cp is not None else (100000 if (best.mate or 0) * sign > 0 else -100000)
        state.update({"best": cb.readable(fen, best.move), "score": cb.score_text(
            best.cp * sign if best.cp is not None else None, best.mate * sign if best.mate is not None else None),
            "line": cb.line_text(fen, best.pv), "to_move": mover,
            "alts": ", ".join(f"{cb.readable(fen, ln.move)} ({cb.score_text(ln.cp, ln.mate)})"
                              for ln in analysis.lines[1:])})
        self._write(state)
        before, self.her_eval = self.her_eval, her_cp
        if new_game:
            self._react("chess_new", f"A new game just started on {board.host}; Hannah has "
                                     f"{'White' if her == 'w' else 'Black'}. Your engine is on it.")
        elif before is not None and abs(before) < 90000:
            drop = before - her_cp
            if not mine and drop >= BLUNDER:
                self._react("chess_blunder", f"Her last move dropped about {drop / 100:.1f} pawns of evaluation "
                                             f"(now {state['score']} for her). Their best reply: {state['best']}.")
            elif mine and -drop >= BLUNDER:
                self._react("chess_gift", f"Her opponent just blundered: she's gone to {state['score']}. "
                                          f"The punishing move is {state['best']} ({state['line']}).")
        if mine and coach["coach"]:
            self.say(f"▸ {state['best']}   {state['score']}   ({state['line']})")
            if self.screen_box:
                arrow(self.folder, {"box": self.screen_box, "from": best.move[:2], "to": best.move[2:4],
                                    "white_bottom": her == "w", "host": board.host})
            if best.mate is not None and best.mate > 0 and best.mate <= 5:
                self._react("chess_mate", f"She has mate in {best.mate}: {state['line']}.")

    def _react(self, kind: str, facts: str) -> None:
        if time.time() - self.last_react < REACT_GAP and kind not in ("chess_over", "chess_mate"):
            return
        self.last_react = time.time()
        from agent.memory_provider import spawn_context_thread
        spawn_context_thread(self.react, name="mira-chess-react", args=(kind, facts)).start()

    def _write(self, state: dict) -> None:
        tmp = self.folder / "chess-now.tmp"
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(self.folder / "chess-now.json")

    # -- noticing a board (ticker, every tick) -----------------------------------------------------------------
    def notice(self, active: bool) -> tuple[Board, str] | None:
        """A board on screen: keep following it (start the loop) and, the first time in a while, return it with
        the facts for an offer moment. Nothing while Hannah's away."""
        seen = boards() if active else []
        if not seen:
            return None
        board = seen[0]
        self.start()
        key = board.host + ":" + ("live" if board.live else "safe")
        if time.time() - self.offered.get(key, 0) < OFFER_AGAIN:
            return None
        self.offered[key] = time.time()
        coach = settings(self.folder)
        if coach["coach"]:
            return None
        if self.engine is None:
            facts = f"She has chess open on {board.host} ({board.title}). You have no engine on this machine yet."
        elif board.live:
            facts = (f"She has chess open on {board.host} ({board.title}) - it may be a live game against a person, "
                     "where engine help is cheating and gets accounts closed. You could offer to go through the game "
                     "with her afterwards with your engine (Stockfish 19), or say hi.")
        else:
            facts = (f"She has chess open on {board.host} ({board.title}). You have Stockfish 19 wired into your eyes "
                     "on her screen: you can read the exact position and give her the best move, the score and the "
                     "line every turn, and react to blunders. Offer to sit in her corner, your way, or don't; if she "
                     "wants it, `argus companion chess on` switches it on.")
        return board, facts
