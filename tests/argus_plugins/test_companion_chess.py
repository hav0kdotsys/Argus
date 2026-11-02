"""argus-companion's chess: exact positions off the screen, the engine's moves (never a guess), and fair play."""

from __future__ import annotations

import importlib
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

_PKG = Path(__file__).resolve().parents[2] / "argus" / "plugins" / "argus-companion"


@pytest.fixture(scope="module")
def pkg():
    spec = importlib.util.spec_from_file_location("argus_companion_c", _PKG / "__init__.py",
                                                  submodule_search_locations=[str(_PKG)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _mod(name):
    return importlib.import_module(f"argus_companion_c.{name}")


# -- bookkeeping -----------------------------------------------------------------------------------------------

def test_chess_com_move_lists_decode_to_uci(pkg):
    cb = _mod("chess_board")
    assert cb.tcn_moves("mCYIgv") == ["e2e4", "c7c5", "g1f3"]
    # a promotion: the second character beyond the board encodes the piece and direction (b7-b8=Q straight on)
    assert cb.tcn_moves("X" + cb.TCN[64 + 1]) == ["b7b8q"]


def test_engine_moves_read_like_chess(pkg):
    cb = _mod("chess_board")
    fen = "r1bqkb1r/1ppp1ppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 2 5"
    assert cb.readable(fen, "e1g1") == "O-O"
    assert cb.readable(fen, "f3e5") == "Nxe5"
    assert cb.readable(fen, "d2d4") == "d4"
    assert cb.readable("8/4P3/8/8/8/8/8/k6K w - - 0 1", "e7e8q") == "e8=Q"
    assert cb.line_text(fen, ("e1g1", "f8e7", "f1e1")) == "O-O Be7 Re1"
    assert cb.score_text(83, None) == "+0.8" and cb.score_text(None, 3) == "M3" and cb.score_text(None, -2) == "-M2"


def test_a_fen_from_what_the_board_shows(pkg):
    cb = _mod("chess_board")
    board = cb.board_from_placement("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR")
    assert cb.fen_of(board, "w", ("e7", "e5")) == "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 1"
    del board["h1"]
    assert cb.castling_from(board) == "Qkq"


def test_uci_info_lines_parse(pkg):
    eng = _mod("chess_engine")
    rank, line = eng.parse_info("info depth 20 seldepth 30 multipv 2 score cp -35 nodes 1 nps 1 pv d2d3 g8f6 b1c3")
    assert rank == 2 and line.move == "d2d3" and line.cp == -35 and line.pv == ("d2d3", "g8f6", "b1c3")
    assert eng.parse_info("info depth 5 score mate 3 pv h5f7")[1].mate == 3
    assert eng.parse_info("info string NNUE evaluation enabled") is None


# -- the eyes, on boards drawn here (no site's art) ------------------------------------------------------------

LIGHT, DARK, LIT = (235, 236, 208), (115, 149, 82), (245, 246, 130)


def _piece(draw, letter, x, y, s):
    """A stand-in piece set: one plain shape per piece kind, light or dark."""
    fill, edge = ((250, 250, 250), (40, 40, 40)) if letter.isupper() else ((30, 30, 30), (230, 230, 230))
    m = s * 0.2
    lo, hi = m, s - m
    shapes = {
        "p": lambda: draw.ellipse((x + s * .35, y + s * .35, x + s * .65, y + s * .75), fill=fill, outline=edge),
        "r": lambda: draw.rectangle((x + lo, y + lo, x + hi, y + hi), fill=fill, outline=edge),
        "n": lambda: draw.polygon([(x + lo, y + hi), (x + hi, y + hi), (x + hi, y + lo)], fill=fill, outline=edge),
        "b": lambda: draw.polygon([(x + s / 2, y + lo), (x + hi, y + hi), (x + lo, y + hi)], fill=fill, outline=edge),
        "q": lambda: draw.ellipse((x + lo, y + lo, x + hi, y + hi), fill=fill, outline=edge),
        "k": lambda: (draw.rectangle((x + s * .42, y + lo, x + s * .58, y + hi), fill=fill, outline=edge),
                      draw.rectangle((x + lo, y + s * .42, x + hi, y + s * .58), fill=fill, outline=edge)),
    }
    shapes[letter.lower()]()


def _screen(placement, white_bottom=True, lit=(), size=480):
    cb = _mod("chess_board")
    board = cb.board_from_placement(placement)
    img = Image.new("RGB", (1200, 800), (49, 46, 43))
    draw = ImageDraw.Draw(img)
    s, ox, oy = size // 8, 300, 120
    for r in range(8):
        for c in range(8):
            name = cb.square(c, 7 - r) if white_bottom else cb.square(7 - c, r)
            colour = LIT if name in lit else (LIGHT if (r + c) % 2 == 0 else DARK)
            draw.rectangle((ox + c * s, oy + r * s, ox + (c + 1) * s - 1, oy + (r + 1) * s - 1), fill=colour)
            if name in board:
                _piece(draw, board[name], ox + c * s, oy + r * s, s)
    return img


def test_she_learns_a_piece_set_from_the_start_and_reads_positions_exactly(pkg, tmp_path):
    eyes = _mod("chess_eyes").Eyes(tmp_path)
    first = eyes.read(_screen(_mod("chess_board").START))
    assert first["start"] and first["white_bottom"]
    mid = "r2q1rk1/pp2bppp/2n1bn2/3p4/3P4/2NB1N2/PP3PPP/R1BQ1RK1"
    assert eyes.read(_screen(mid))["fen"].startswith(mid)
    # the same pieces with the board turned round (she's playing Black), at another size
    flipped = eyes.read(_screen(mid, white_bottom=False, size=560))
    assert flipped["fen"].startswith(mid) and flipped["white_bottom"] is False


def test_the_last_move_highlight_says_whose_turn_it_is(pkg, tmp_path):
    eyes = _mod("chess_eyes").Eyes(tmp_path)
    eyes.read(_screen(_mod("chess_board").START))
    after_e5 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR"
    seen = eyes.read(_screen(after_e5, lit=("e7", "e5")))
    assert seen["fen"] == f"{after_e5} w KQkq e6 0 1"
    after_nf3 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R"
    assert eyes.read(_screen(after_nf3, lit=("g1", "f3")))["fen"].split()[1] == "b"


def test_an_unknown_board_style_asks_for_a_starting_position_instead_of_guessing(pkg, tmp_path):
    seen = _mod("chess_eyes").Eyes(tmp_path).read(_screen("4k3/8/8/8/8/8/8/4K2R"))
    assert seen["found"] and not seen["learnt"] and seen["fen"] is None


# -- the engine itself, where it's installed ------------------------------------------------------------------

@pytest.mark.skipif(not shutil.which("stockfish"), reason="no Stockfish on this machine")
def test_stockfish_finds_the_mate_and_knows_the_position(pkg):
    eng = _mod("chess_engine")
    engine = eng.Engine(shutil.which("stockfish"))
    try:
        mate = engine.analyse("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", think_ms=300)
        assert mate.best.move == "a1a8" and mate.best.mate == 1
        assert engine.fen_after(_mod("chess_board").START_FEN, ["e2e4"]).startswith(
            "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq")
        mated = "4R1k1/5ppp/8/8/8/8/8/6K1 b - - 0 1"       # back-rank mate: Black to move, no moves
        assert engine.in_check(mated) and engine.analyse(mated, think_ms=100).best is None
    finally:
        engine.close()


# -- fair play and what she says --------------------------------------------------------------------------------

def test_live_games_against_people_get_no_engine(pkg):
    coach = _mod("chess_coach")
    assert not coach.Board("laphvk", "Play Chess Online Against the Computer - Chess.com", (0, 0, 1, 1)).live
    assert not coach.Board("winhvk", "Analysis board • lichess.org", (0, 0, 1, 1)).live
    assert coach.Board("winhvk", "Play Chess Online for FREE - 2 Player Chess - Chess.com", (0, 0, 1, 1)).live
    assert coach.Board("laphvk", "Chess: GM Hikaru vs GM Sina-Movahed - Chess.com", (0, 0, 1, 1)).live


class _Engine:
    def __init__(self):
        self.asked = []

    def analyse(self, fen, think_ms=0):
        eng = _mod("chess_engine")
        self.asked.append(fen)
        return eng.Analysis(fen, [eng.Line("e1g1", 40, None, ("e1g1", "f8e7"))])

    def in_check(self, fen):
        return False


def _coach(tmp_path):
    coach = _mod("chess_coach")
    said, reacted = [], []
    c = coach.Coach(tmp_path, said.append, lambda kind, facts: reacted.append(kind))
    c.engine = _Engine()
    return coach, c, said


FEN = "r1bqkb1r/1ppp1ppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 1"


def test_coaching_gives_the_engines_move_only_when_she_asked_and_never_in_a_live_game(pkg, tmp_path):
    coach, c, said = _coach(tmp_path)
    safe = coach.Board("laphvk", "Play Chess Online Against the Computer - Chess.com", (0, 0, 1, 1))
    c.position(safe, FEN, "w", False)
    assert said == [] and c.engine.asked == []                           # coaching off: no engine at all
    coach.set_coach(tmp_path, True)
    c.position(safe, FEN, "w", False)
    assert said == ["▸ O-O   +0.4   (O-O Be7)"]
    assert "Stockfish 19: best O-O (+0.4 for her)" in coach.turn_context(tmp_path)
    live = coach.Board("winhvk", "Play Chess Online for FREE - 2 Player Chess - Chess.com", (0, 0, 1, 1))
    c.engine.asked.clear()
    c.position(live, FEN.replace("RNBQK2R", "RNBQK1R1"), "w", False)
    assert c.engine.asked == [] and len(said) == 1                        # a person on the other side: nothing
    assert "cheating" in coach.turn_context(tmp_path)
    coach.set_coach(tmp_path, True, bot=True)                             # Hannah: "it's a bot"
    c.position(live, FEN, "w", False)
    assert len(said) == 2


# -- her games room ------------------------------------------------------------------------------------------

@pytest.mark.skipif(not shutil.which("stockfish"), reason="no Stockfish on this machine")
def test_chess_against_her_follows_the_rules_and_she_answers(pkg):
    eng, room, cb = _mod("chess_engine"), _mod("room"), _mod("chess_board")
    engine = eng.Engine(shutil.which("stockfish"))
    try:
        assert len(engine.legal(cb.START_FEN)) == 20
        bad = room.chess_turn(engine, cb.START_FEN, "e2e5", "easy")
        assert bad["error"] == "illegal" and bad["fen"] == cb.START_FEN
        turn = room.chess_turn(engine, cb.START_FEN, "e2e4", "easy")
        assert turn["mine"] == "e4" and turn["hers"] and turn["fen"].split()[1] == "w" and turn["status"] == "play"
        # Fool's mate: Hannah delivers it, and Mira has no reply to make
        fools = "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2"
        over = room.chess_turn(engine, fools, "d8h4", "max")
        assert over["status"] == "checkmate" and "hers" not in over
    finally:
        engine.close()


def test_the_room_only_answers_with_its_token_and_hands_her_the_result(pkg, tmp_path, monkeypatch):
    import json as _json
    import time
    import urllib.error
    import urllib.request
    room = _mod("room")
    monkeypatch.setattr(room, "PORT", 0)        # any free port
    told = []
    r = room.Room(tmp_path, told.append)
    r.start()
    port = r.server.server_address[1]
    try:
        with pytest.raises(urllib.error.HTTPError) as no:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        assert no.value.code == 403
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/?t={r.token}").read().decode()
        assert "M I R A" in page
        body = _json.dumps({"game": "tictactoe", "result": "win", "score": "you 2, Mira 1"}).encode()
        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/result?t={r.token}", data=body,
                                                      headers={"Content-Type": "application/json"}))
        for _ in range(50):
            if told:
                break
            time.sleep(0.02)
        assert told == ["You just played tic-tac-toe with her on your games board: Hannah beat you. "
                        "Score this session: you 2, Mira 1."]
    finally:
        r.server.shutdown()


def test_her_settings_switch_moments_off_and_set_the_pop_in_pace(pkg, tmp_path):
    prefs = _mod("prefs")
    assert prefs.scheduler_settings(tmp_path).enabled >= {"water", "popin"}
    prefs.save(tmp_path, {"off": ["water", "not-a-moment"], "popin": "often"})
    s = prefs.scheduler_settings(tmp_path)
    assert "water" not in s.enabled and "back" not in s.enabled and "stretch" in s.enabled
    assert (s.minutes["popin_min"], s.minutes["popin_max"]) == prefs.POPIN["often"]
    assert not prefs.allowed(tmp_path, "water") and prefs.allowed(tmp_path, "reminder")
    assert prefs.load(tmp_path)["off"] == ["water"]
