"""Small, dependency-free chess bookkeeping for the coach: FEN in and out, readable moves, chess.com's TCN.

No move generation lives here; legality is Stockfish's job. This only turns what the coach SEES (a placement, the
last-move squares) into a FEN the engine accepts, and the engine's UCI back into something Hannah reads at a glance.
"""

from __future__ import annotations

FILES = "abcdefgh"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
START_FEN = START + " w KQkq - 0 1"
NAMES = {"p": "pawn", "n": "knight", "b": "bishop", "r": "rook", "q": "queen", "k": "king"}

Board = dict  # square name ("e4") -> piece letter (uppercase white, lowercase black)


def square(file: int, rank: int) -> str:
    """0-based file and rank -> 'a1'..'h8'."""
    return f"{FILES[file]}{rank + 1}"


def board_from_placement(placement: str) -> Board:
    board: Board = {}
    for row, text in enumerate(placement.split("/")):
        file = 0
        for ch in text:
            if ch.isdigit():
                file += int(ch)
            else:
                board[square(file, 7 - row)] = ch
                file += 1
    return board


def placement_of(board: Board) -> str:
    rows = []
    for rank in range(7, -1, -1):
        row, empty = "", 0
        for file in range(8):
            piece = board.get(square(file, rank))
            if piece:
                row += (str(empty) if empty else "") + piece
                empty = 0
            else:
                empty += 1
        rows.append(row + (str(empty) if empty else ""))
    return "/".join(rows)


def castling_from(board: Board) -> str:
    """Rights as far as the board can show them: king and rook still on their home squares."""
    rights = ""
    if board.get("e1") == "K":
        rights += ("K" if board.get("h1") == "R" else "") + ("Q" if board.get("a1") == "R" else "")
    if board.get("e8") == "k":
        rights += ("k" if board.get("h8") == "r" else "") + ("q" if board.get("a8") == "r" else "")
    return rights or "-"


def en_passant_from(board: Board, last: tuple[str, str] | None) -> str:
    """The en-passant target after a double pawn push (from the last move's two squares), else '-'."""
    if not last:
        return "-"
    a, b = last
    for frm, to in ((a, b), (b, a)):
        piece = board.get(to, "")
        if piece.lower() == "p" and frm[0] == to[0] and abs(int(frm[1]) - int(to[1])) == 2:
            return f"{to[0]}{(int(frm[1]) + int(to[1])) // 2}"
    return "-"


def fen_of(board: Board, to_move: str, last: tuple[str, str] | None = None, fullmove: int = 1) -> str:
    return f"{placement_of(board)} {to_move} {castling_from(board)} {en_passant_from(board, last)} 0 {fullmove}"


def to_move(fen: str) -> str:
    return fen.split()[1] if len(fen.split()) > 1 else "w"


def readable(fen: str, uci: str) -> str:
    """UCI -> short algebraic as far as needed to read it: Nf3, exd5, O-O, e8=Q (no check marks, no disambiguation)."""
    board = board_from_placement(fen.split()[0])
    frm, to, promo = uci[:2], uci[2:4], uci[4:5]
    piece = board.get(frm, "")
    if piece.lower() == "k" and frm[0] == "e" and to[0] in "cg":
        return "O-O" if to[0] == "g" else "O-O-O"
    capture = to in board or (piece.lower() == "p" and frm[0] != to[0])
    if piece.lower() == "p":
        text = (f"{frm[0]}x" if capture else "") + to
    else:
        text = piece.upper() + ("x" if capture else "") + to
    return text + (f"={promo.upper()}" if promo else "")


def line_text(fen: str, moves: tuple[str, ...], plies: int = 4) -> str:
    """A principal variation in readable moves, replayed on a scratch board (pieces moved, no legality)."""
    board = board_from_placement(fen.split()[0])
    out = []
    for uci in moves[:plies]:
        scratch = f"{placement_of(board)} w"
        out.append(readable(scratch, uci))
        piece = board.pop(uci[:2], None)
        if piece is None:
            break
        if piece.lower() == "k" and uci[0] == "e" and uci[2] in "cg":       # castling: the rook comes too
            rank = uci[1]
            rook_from, rook_to = ("h", "f") if uci[2] == "g" else ("a", "d")
            board[rook_to + rank] = board.pop(rook_from + rank, piece.replace("k", "r").replace("K", "R"))
        if piece.lower() == "p" and uci[0] != uci[2] and uci[2:4] not in board:   # en passant
            board.pop(uci[2] + uci[1], None)
        board[uci[2:4]] = (uci[4].upper() if piece.isupper() else uci[4]) if len(uci) > 4 else piece
    return " ".join(out)


def score_text(cp: int | None, mate: int | None) -> str:
    if mate is not None:
        return f"M{mate}" if mate > 0 else f"-M{-mate}"
    return f"{(cp or 0) / 100:+.1f}"


TCN = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?{~}(^)[_]@#$,./&-*++="


def tcn_moves(encoded: str) -> list[str]:
    """chess.com's compact move list (two characters a move) -> UCI moves."""
    moves = []
    for i in range(0, len(encoded) - 1, 2):
        frm, to = TCN.find(encoded[i]), TCN.find(encoded[i + 1])
        if frm < 0 or to < 0 or frm > 63:
            continue    # drops (variants) aren't chess
        promo = ""
        if to > 63:
            promo = "qnrbkp"[(to - 64) // 3]
            to = frm + (-8 if frm < 16 else 8) + (to - 1) % 3 - 1
        moves.append(square(frm % 8, frm // 8) + square(to % 8, to // 8) + promo)
    return moves
