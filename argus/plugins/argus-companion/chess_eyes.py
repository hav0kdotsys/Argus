"""Reading a chess position off the screen, exactly enough for an engine: Mira's eyes for chess.com vs the computer,
puzzles and anything else without a game id.

No piece art is shipped or guessed. The board is found as an 8x8 checker of two colours; which squares hold a piece is
plain contrast against each square's own background; and what each piece IS comes from templates learnt the first
time she sees a starting position in that piece set (the start is the one position whose contents are known). After
that every position on that board style reads back as a FEN placement. The side to move comes from the last-move
highlight both chess.com and lichess draw: the highlighted square that holds a piece holds the piece that just moved.

Pure Pillow (no numpy): boards are resampled to 512 px, 64 px a square, so the arithmetic is small.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from . import chess_board as cb

SIDE = 512
CELL = SIDE // 8
INNER = (10, 54)          # the part of a square the piece is read from (coordinates labels sit in the corners)
GRID = 22                 # template resolution
PIECE_DIST = 30           # colour distance from a square's background that counts as piece (chess.com white on light: ~55)
OCCUPIED = 0.06           # share of inner pixels that makes a square occupied
HIGHLIGHT_DIST = 40       # a square background this far from both board colours is highlighted

# Board colour pairs seen in the wild, tried before the generic search: chess.com green (new and classic), lichess
# brown and blue.
THEMES = (((235, 236, 208), (115, 149, 82)), ((238, 238, 210), (118, 150, 86)),
          ((240, 217, 181), (181, 136, 99)), ((222, 227, 230), (140, 162, 173)))


def _dist(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _lum(c) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


@dataclass
class Found:
    box: tuple[int, int, int, int]     # left, top, right, bottom in the screenshot
    light: tuple[int, int, int]
    dark: tuple[int, int, int]


def _run(counts: list[float], floor: float, gap: int = 4) -> tuple[int, int] | None:
    """The longest stretch of indexes whose value is at least ``floor``, bridging dips of up to ``gap`` (a rank of
    wide pieces leaves little background showing)."""
    best, start, last = None, None, None
    for i, n in enumerate(list(counts) + [0.0] * (gap + 1)):
        if n >= floor:
            if start is None or (last is not None and i - last > gap + 1):
                start = i
            last = i
            if best is None or last + 1 - start > best[1] - best[0]:
                best = (start, last + 1)
    return best


def _near(img: Image.Image, colour, tol: float) -> Image.Image:
    """An L mask (255 where the pixel is within tol of colour), computed in C."""
    diff = ImageChops.difference(img, Image.new("RGB", img.size, tuple(int(v) for v in colour)))
    r, g, b = diff.split()
    total = ImageChops.add(ImageChops.add(r, g), b)        # sum of channel gaps, saturating at 255
    return total.point(lambda v: 255 if v < tol * 1.7 else 0)


def _checker_score(img: Image.Image, box, light, dark, tol: float) -> float:
    """How well the 64 cells inside box alternate light/dark, sampled near each cell's corners."""
    left, top, right, bottom = box
    cw, ch = (right - left) / 8, (bottom - top) / 8
    good = 0
    for r in range(8):
        for c in range(8):
            want = light if (r + c) % 2 == 0 else dark
            other = dark if want is light else light
            px = img.getpixel((int(left + (c + 0.12) * cw), int(top + (r + 0.12) * ch)))[:3]
            if _dist(px, want) < tol and _dist(px, want) < _dist(px, other):
                good += 1
    return good / 64


def _candidate(small: Image.Image, light, dark, tol: float = 26.0):
    mask = ImageChops.lighter(_near(small, light, tol), _near(small, dark, tol))
    w, h = small.size
    rows = list(mask.resize((1, h), Image.Resampling.BOX).tobytes())
    cols = list(mask.resize((w, 1), Image.Resampling.BOX).tobytes())
    if max(rows, default=0) < 30:
        return None
    rr = _run(rows, max(rows) * 0.15)
    cr = _run(cols, max(cols) * 0.15)
    if not rr or not cr:
        return None
    box = (cr[0], rr[0], cr[1], rr[1])
    bw, bh = box[2] - box[0], box[3] - box[1]
    if bw < 64 or abs(bw - bh) > 0.08 * bw:
        return None
    score = _checker_score(small, box, light, dark, tol + 10)
    flipped = _checker_score(small, box, dark, light, tol + 10)
    if flipped > score:     # the top-left square is dark: name the pair the board's way round
        light, dark, score = dark, light, flipped
    return score, box, light, dark


def _frequent_colours(small: Image.Image, n: int = 6) -> list[tuple[int, int, int]]:
    tiny = small.resize((160, max(1, int(160 * small.height / small.width))))
    counts: dict[tuple, int] = {}
    for count, px in tiny.getcolors(160 * 160) or []:
        key = (px[0] // 12 * 12 + 6, px[1] // 12 * 12 + 6, px[2] // 12 * 12 + 6)
        counts[key] = counts.get(key, 0) + count
    return [c for c, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:n]]


def find_board(shot: Image.Image) -> Found | None:
    """The chess board in a screenshot: the best 8x8 checker of two colours, known themes first."""
    shot = shot.convert("RGB")
    scale = max(1.0, shot.width / 640)
    small = shot.resize((int(shot.width / scale), int(shot.height / scale)))
    best = None
    for pairs in (THEMES, [p for p in combinations(_frequent_colours(small), 2) if _dist(*p) > 50]):
        for light, dark in pairs:
            cand = _candidate(small, light, dark)
            if cand and cand[0] >= 0.8 and (best is None or cand[0] > best[0] + 0.02):
                best = cand
        if best:
            break
    if not best:
        return None
    _, box, light, dark = best
    full = tuple(round(v * scale) for v in box)
    return Found(full, light, dark)


def _square_background(cell: Image.Image, expect) -> tuple[tuple[float, ...], bool]:
    """A square's own background from its corners, and whether it's highlighted. A corner holding the board colour
    the square should have wins (coordinate labels spoil up to two corners); when none does, the square is tinted
    (the last-move highlight) and its background is the two corners that agree best."""
    inset, size = 3, 4
    patches = [tuple(ImageStat.Stat(cell.crop((x, y, x + size, y + size))).mean[:3])
               for x, y in ((inset, inset), (CELL - inset - size, inset), (inset, CELL - inset - size),
                            (CELL - inset - size, CELL - inset - size))]
    nearest = min(patches, key=lambda p: _dist(p, expect))
    if _dist(nearest, expect) < HIGHLIGHT_DIST:
        return nearest, False
    a, b = min(combinations(patches, 2), key=lambda pair: _dist(*pair))
    return tuple((a[i] + b[i]) / 2 for i in range(3)), True


@dataclass
class Square:
    occupied: bool
    white_share: float = 0.0           # share of the piece's pixels that are bright
    mask: tuple[float, ...] = ()       # GRID x GRID occupancy, 0..1
    highlighted: bool = False


def read_squares(shot: Image.Image, found: Found) -> list[list[Square]]:
    """The 8x8 squares as seen, rows top to bottom of the screen."""
    board = shot.convert("RGB").crop(found.box).resize((SIDE, SIDE))
    bright_all = board.convert("L").point(lambda v: 255 if v > 150 else 0)
    lo, hi = INNER
    out = []
    for r in range(8):
        row = []
        for c in range(8):
            x0, y0 = c * CELL, r * CELL
            cell = board.crop((x0, y0, x0 + CELL, y0 + CELL))
            bg, highlighted = _square_background(cell, found.light if (r + c) % 2 == 0 else found.dark)
            inner = cell.crop((lo, lo, hi, hi))
            piece = ImageChops.invert(_near(inner, bg, PIECE_DIST))
            share = ImageStat.Stat(piece).mean[0] / 255
            if share < OCCUPIED:
                row.append(Square(False, highlighted=highlighted))
                continue
            bright = ImageChops.multiply(piece, bright_all.crop((x0 + lo, y0 + lo, x0 + hi, y0 + hi)))
            white_share = ImageStat.Stat(bright).mean[0] / max(1.0, ImageStat.Stat(piece).mean[0])
            grid = tuple(v / 255 for v in piece.resize((GRID, GRID), Image.Resampling.BOX).tobytes())
            row.append(Square(True, white_share, grid, highlighted))
        out.append(row)
    return out


def looks_like_start(squares: list[list[Square]]) -> bool | None:
    """Is this the starting position? None if not; else True when white is at the bottom, False when at the top."""
    occupied = [[s.occupied for s in row] for row in squares]
    if not all(all(occupied[r]) for r in (0, 1, 6, 7)) or any(any(occupied[r]) for r in range(2, 6)):
        return None
    top = sum(s.white_share for r in (0, 1) for s in squares[r]) / 16
    bottom = sum(s.white_share for r in (6, 7) for s in squares[r]) / 16
    if abs(top - bottom) < 0.15:
        return None
    return bottom > top


@dataclass
class Style:
    """What one piece set looks like, learnt from a starting position."""
    templates: dict[str, tuple[float, ...]]     # piece letter -> mask
    white_cut: float                             # white_share above this is a white piece
    white_bottom: bool = True

    def to_json(self) -> dict:
        return {"templates": {k: list(v) for k, v in self.templates.items()}, "white_cut": self.white_cut,
                "white_bottom": self.white_bottom}

    @classmethod
    def from_json(cls, data: dict) -> Style:
        return cls({k: tuple(v) for k, v in data["templates"].items()}, data["white_cut"],
                   data.get("white_bottom", True))


def learn(squares: list[list[Square]], white_bottom: bool) -> Style:
    """Templates from a starting position: every piece's mask, averaged per piece letter."""
    back = "rnbqkbnr"
    seen: dict[str, list[tuple[float, ...]]] = {}
    whites, blacks = [], []
    for r in (0, 1, 6, 7):
        for c in range(8):
            rank = 7 - r if white_bottom else r
            file = c if white_bottom else 7 - c
            letter = "p" if rank in (1, 6) else back[file]
            white = rank < 2
            sq = squares[r][c]
            (whites if white else blacks).append(sq.white_share)
            seen.setdefault(letter.upper() if white else letter, []).append(sq.mask)
    templates = {k: tuple(sum(m[i] for m in v) / len(v) for i in range(GRID * GRID)) for k, v in seen.items()}
    cut = (min(whites) + max(blacks)) / 2 if min(whites) > max(blacks) else (sum(whites) / 16 + sum(blacks) / 16) / 2
    return Style(templates, cut, white_bottom)


def classify(sq: Square, style: Style) -> str:
    white = sq.white_share > style.white_cut
    letters = "PNBRQK" if white else "pnbrqk"

    def gap(letter):
        t = style.templates.get(letter)
        return sum(abs(a - b) for a, b in zip(sq.mask, t)) if t else float("inf")
    return min(letters, key=gap)


def white_at_bottom(seen: dict[tuple[int, int], str], fallback: bool) -> bool:
    """Which way round the board is, from the pawns: White's pawns stand below Black's when White is at the bottom
    (a pawn never passes an enemy pawn on its own file, and on average the structure keeps that order)."""
    white = [r for (r, _), p in seen.items() if p == "P"]
    black = [r for (r, _), p in seen.items() if p == "p"]
    if white and black:
        gap = sum(white) / len(white) - sum(black) / len(black)
        if abs(gap) >= 0.5:
            return gap > 0
    kings = {p: r for (r, _), p in seen.items() if p in "Kk"}
    if "K" in kings and "k" in kings and kings["K"] != kings["k"] and not (white or black):
        return kings["K"] > kings["k"]
    return fallback


def position(squares: list[list[Square]], style: Style) -> tuple[cb.Board, tuple[str, str] | None, bool]:
    """The placement, the last move's two squares (if highlighted) and whether White is at the bottom."""
    seen = {(r, c): classify(sq, style) for r, row in enumerate(squares) for c, sq in enumerate(row) if sq.occupied}
    bottom = white_at_bottom(seen, style.white_bottom)
    style.white_bottom = bottom

    def name(r, c):
        return cb.square(c, 7 - r) if bottom else cb.square(7 - c, r)
    board = {name(r, c): piece for (r, c), piece in seen.items()}
    lit = [name(r, c) for r, row in enumerate(squares) for c, sq in enumerate(row) if sq.highlighted]
    return board, (lit[0], lit[1]) if len(lit) == 2 else None, bottom


def side_to_move(board: cb.Board, last: tuple[str, str] | None, fallback: str) -> str:
    """Whose move: the opposite colour of the piece standing on a highlighted last-move square."""
    if last:
        for name in last:
            piece = board.get(name)
            if piece:
                return "b" if piece.isupper() else "w"
    return fallback


class Eyes:
    """Remembers learnt piece sets by board colours, in ``<companion>/chess-styles.json``."""

    def __init__(self, folder: Path):
        self.file = folder / "chess-styles.json"
        try:
            raw = json.loads(self.file.read_text(encoding="utf-8"))
            self.styles = {k: Style.from_json(v) for k, v in raw.items()}
        except (OSError, ValueError, KeyError, TypeError):
            self.styles = {}

    @staticmethod
    def key(found: Found) -> str:
        return "/".join(f"{int(v) // 8}" for v in found.light + found.dark)

    def _save(self) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: v.to_json() for k, v in self.styles.items()}), encoding="utf-8")
        tmp.replace(self.file)

    def read(self, shot: Image.Image, fallback_turn: str = "w") -> dict:
        """What's on this screenshot: {"found": bool, "learnt": bool, "fen": str|None, "white_bottom": bool,
        "start": bool}. A starting position teaches (or re-teaches) this board style on the spot."""
        found = find_board(shot)
        if not found:
            return {"found": False, "learnt": False, "fen": None}
        squares = read_squares(shot, found)
        key = self.key(found)
        start = looks_like_start(squares)
        if start is not None:
            self.styles[key] = learn(squares, start)
            self._save()
            return {"found": True, "learnt": True, "fen": cb.START_FEN, "white_bottom": start, "start": True,
                    "box": found.box}
        style = self.styles.get(key)
        if not style:
            return {"found": True, "learnt": False, "fen": None, "box": found.box}
        board, last, bottom = position(squares, style)
        turn = side_to_move(board, last, fallback_turn)
        return {"found": True, "learnt": True, "fen": cb.fen_of(board, turn, last), "white_bottom": bottom,
                "start": False, "box": found.box, "last": last}
