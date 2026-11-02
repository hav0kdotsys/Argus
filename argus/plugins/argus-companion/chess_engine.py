"""Stockfish, spoken to over UCI: the engine behind Mira's chess coaching.

One engine process per companion, started on first use and kept (a fresh Stockfish costs its NNUE load every time).
It's found on PATH (laphvk: /usr/bin/stockfish) or under ``<ARGUS_HOME>/tools/stockfish/`` (winhvk). Every answer
is the engine's, never a model's guess: the best move, the evaluation from the side to move, and its principal
variation, at a fixed think time per position.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

THINK_MS = 1500     # per position: ~3000+ Elo on a desktop CPU, still quick enough to follow a game
LINES = 3


@dataclass(frozen=True)
class Line:
    move: str                  # UCI, e.g. g1f3
    cp: int | None             # centipawns for the side to move, or None when it's a mate score
    mate: int | None           # moves to mate (negative: being mated)
    pv: tuple[str, ...] = ()


@dataclass
class Analysis:
    fen: str
    lines: list[Line] = field(default_factory=list)

    @property
    def best(self) -> Line | None:
        return self.lines[0] if self.lines else None


def find_engine(home: Path | None = None) -> str | None:
    on_path = shutil.which("stockfish")
    if on_path:
        return on_path
    if home is None:
        from hermes_constants import get_hermes_home
        home = get_hermes_home()
    folder = Path(home) / "tools" / "stockfish"
    for candidate in sorted(folder.rglob("stockfish*")) if folder.is_dir() else []:
        if candidate.is_file() and (candidate.suffix.lower() == ".exe" or os.access(candidate, os.X_OK)):
            return str(candidate)
    return None


def parse_info(line: str) -> tuple[int, Line] | None:
    """One UCI ``info ... multipv N score cp X ... pv a b c`` line -> (N, Line); None for anything else."""
    words = line.split()
    if not words or words[0] != "info" or "pv" not in words or "score" not in words:
        return None
    try:
        rank = int(words[words.index("multipv") + 1]) if "multipv" in words else 1
        kind, value = words[words.index("score") + 1], int(words[words.index("score") + 2])
    except (ValueError, IndexError):
        return None
    pv = tuple(words[words.index("pv") + 1:])
    if not pv:
        return None
    return rank, Line(pv[0], value if kind == "cp" else None, value if kind == "mate" else None, pv)


class Engine:
    def __init__(self, path: str):
        self.path = path
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def _start(self) -> subprocess.Popen:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen([self.path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, bufsize=1, creationflags=flags)
        threads = max(1, (os.cpu_count() or 2) // 2)
        for command in ("uci", f"setoption name Threads value {threads}", "setoption name Hash value 256",
                        f"setoption name MultiPV value {LINES}", "isready"):
            proc.stdin.write(command + "\n")
        proc.stdin.flush()
        for line in proc.stdout:
            if line.strip() == "readyok":
                break
        return proc

    def analyse(self, fen: str, think_ms: int = THINK_MS) -> Analysis:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = self._start()
            proc = self._proc
            proc.stdin.write(f"ucinewgame\nposition fen {fen}\ngo movetime {think_ms}\n")
            proc.stdin.flush()
            best: dict[int, Line] = {}
            for line in proc.stdout:
                if line.startswith("bestmove"):
                    if line.split()[1] == "(none)":
                        best.clear()        # no legal move: mate or stalemate on the board
                    break
                parsed = parse_info(line)
                if parsed:
                    best[parsed[0]] = parsed[1]
            return Analysis(fen, [best[k] for k in sorted(best)])

    def fen_after(self, start_fen: str, moves: list[str]) -> str | None:
        """The exact FEN after UCI moves from a start position (Stockfish's own board, so castling rights, en
        passant and counters are right), or None if it can't say."""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = self._start()
            proc = self._proc
            tail = f" moves {' '.join(moves)}" if moves else ""
            proc.stdin.write(f"position fen {start_fen}{tail}\nd\nisready\n")
            proc.stdin.flush()
            fen = None
            for line in proc.stdout:
                if line.startswith("Fen: "):
                    fen = line[5:].strip()
                if line.strip() == "readyok":
                    break
            return fen

    def legal(self, fen: str) -> list[str]:
        """Every legal move in the position (UCI), from Stockfish's own move generator (``go perft 1``)."""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = self._start()
            proc = self._proc
            proc.stdin.write(f"position fen {fen}\ngo perft 1\n")
            proc.stdin.flush()
            moves = []
            for line in proc.stdout:
                if line.startswith("Nodes searched"):
                    break
                head = line.split(":")[0].strip()
                if ":" in line and 4 <= len(head) <= 5 and head[0] in "abcdefgh" and head[1].isdigit():
                    moves.append(head)
            return moves

    def play(self, fen: str, elo: int | None = None, think_ms: int = 800) -> str | None:
        """Her move as an opponent: full strength, or limited to about ``elo`` (1320-3190)."""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = self._start()
            proc = self._proc
            limit = "true" if elo else "false"
            proc.stdin.write(f"setoption name MultiPV value 1\nsetoption name UCI_LimitStrength value {limit}\n"
                             + (f"setoption name UCI_Elo value {max(1320, min(3190, elo))}\n" if elo else "")
                             + f"position fen {fen}\ngo movetime {think_ms}\n")
            proc.stdin.flush()
            move = None
            for line in proc.stdout:
                if line.startswith("bestmove"):
                    move = line.split()[1]
                    break
            proc.stdin.write(f"setoption name UCI_LimitStrength value false\nsetoption name MultiPV value {LINES}\n")
            proc.stdin.flush()
            return None if move in (None, "(none)") else move

    def in_check(self, fen: str) -> bool:
        """Is the side to move in check? (Stockfish's board lists the checkers.)"""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = self._start()
            proc = self._proc
            proc.stdin.write(f"position fen {fen}\nd\nisready\n")
            proc.stdin.flush()
            checked = False
            for line in proc.stdout:
                if line.startswith("Checkers:"):
                    checked = bool(line[len("Checkers:"):].strip())
                if line.strip() == "readyok":
                    break
            return checked

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write("quit\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=3)
            except (OSError, subprocess.SubprocessError):
                self._proc.kill()
        self._proc = None
