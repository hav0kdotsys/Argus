"""argus-companion - Mira as a companion, not an assistant.

- Her voice, enforced in code (``voice.py``) on every reply through ``transform_llm_output``. It runs only on the
  reply being finished, never on earlier turns or the system prompt, so the prompt cache is untouched, and it leaves
  work output (code, lists, tables, long reports) exactly as written.
- Her own check-ins: ``presence.py`` opens moments from laphvk's signals (``ticker.py``), and ``mind.py`` asks MIRA
  herself, through the provider, with her memory and what she can see, whether and what to say - nobody writes her
  lines. ``argus companion run`` ticks (the mira-companion unit runs it); what she says goes out loud through MIRA's
  voice panel (and ``say.json``, which her retired bodies drew as a bubble).

- One Mira: every ARGUS turn tells her what she said on her own since that session last heard from her
  (``pre_llm_call`` context on the user message, never the system prompt), and marks that Hannah talked to her (the
  ticker's ``bored`` moment needs it).

Later slices: the day-by-day memory fold, screen glances, perching on windows, winhvk and the phone.
"""

from __future__ import annotations

import re

from collections import OrderedDict, deque
from typing import Any

from . import voice

_SESSIONS = 256      # sessions whose recent openers are remembered (oldest dropped first)
_RECENT = 4          # openers per session a new reply may not repeat

_openers: OrderedDict[str, deque[str]] = OrderedDict()


def _recent(session_id: str) -> deque[str]:
    seen = _openers.pop(session_id, None) or deque(maxlen=_RECENT)
    _openers[session_id] = seen
    while len(_openers) > _SESSIONS:
        _openers.popitem(last=False)
    return seen


def _on_reply(response_text: str = "", session_id: str = "", **_: Any) -> str | None:
    if not isinstance(response_text, str) or not response_text:
        return None
    seen = _recent(session_id or "")
    polished = voice.polish(response_text, tuple(seen))
    word = voice.opener(polished)
    if word:
        seen.append(word)
    return polished if polished != response_text else None


_SEEN_HOURS = 6          # how far back a session's first turn looks for her own words
_heard: OrderedDict[str, str] = OrderedDict()   # session -> the newest check-in stamp it was told about


def _companion_dir():
    from . import ticker
    return ticker.companion_dir()


def own_words_since(log_lines: list[str], since: str) -> list[str]:
    """Spoken check-ins (``YYYY-MM-DD HH:MM kind[ (aloud)]: text``) stamped after *since*; passes are not words."""
    found = []
    for line in log_lines:
        stamp, _, rest = line[:16], line[16:17], line[17:]
        if len(stamp) == 16 and stamp > since and ": " in rest and not rest.endswith("(passed)"):
            found.append(f"- {stamp[11:]} \"{rest.split(': ', 1)[1]}\"")
    return found


_GAMES = re.compile(r"\b(play|game|games|chess|tic.?tac|connect.?four|connect ?4|rock.?paper|rps)\b", re.IGNORECASE)


def _on_turn(session_id: str = "", **_: Any) -> dict | None:
    from datetime import datetime, timedelta
    folder = _companion_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "talked").write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    try:
        lines = (folder / "checkins.log").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    key = session_id or ""
    since = _heard.pop(key, None) or (datetime.now() - timedelta(hours=_SEEN_HOURS)).strftime("%Y-%m-%d %H:%M")
    words = own_words_since(lines, since)
    _heard[key] = max([since] + [line[:16] for line in lines if len(line) >= 16])
    while len(_heard) > _SESSIONS:
        _heard.popitem(last=False)
    from .chess_coach import turn_context
    chess = turn_context(folder)
    if _GAMES.search(str(_.get("user_message") or "")):
        chess = (chess + "\n" if chess else "") + (
            "[Your games board: `argus companion play chess|tictactoe|connect4|rps` (terminal) opens it on her screen; "
            "chess there is against you at the level she picks. `argus companion chess on` coaches the board she has "
            "open on chess.com/lichess. You see how games end.]")
    if not words and not chess:
        return None
    parts = []
    if words:
        parts.append("[What you said to Hannah on your own lately (out loud and in your bubble), so you know if "
                     "she's answering it:\n" + "\n".join(words) + "]")
    if chess:
        parts.append(chess)
    return {"context": "\n".join(parts)}


USAGE = """argus companion run          offer Mira moments as they come up (foreground; Ctrl-C stops)
argus companion moment [KIND] [--dry]  offer her one now (water, stretch, eyes, session, meal, late, bored, popin);
                             --dry prints what she'd do without showing or saying it
argus companion body ACTION  her body: type, show, hide, hop, walk, sit, stand, lie, sleep, wake, dance,
                             stop_dancing, glitch, grin, drop, ride, hop_off, come_here, floor, elsewhere,
                             next_screen, this_screen, size small/medium/large/huge/giant,
                             perch WINDOW ("perch discord"), mini_player_on/off (bind `body type` to a key);
                             --there sends it to her body on the other machine (hop_in: she comes over)
argus companion link         how her two bodies are linked (music, quiet, coaching and settings cross over)
argus companion away         count as away now (no waiting for the idle clock) until you're back at this machine
argus companion chess [on|off|look|status] [--bot]  her chess coaching (Stockfish on the board she sees); --bot coaches
                             a game the title can't prove is against the computer
argus companion play [GAME]  her room: chess, tictactoe, connect4, rps (chess against her at any level), settings
argus companion hands kit|do|answer B64  her body's hands for MIRA's MCP: her tools here, one call ({"tool","args"} as
                                  base64 JSON), or HavoK's answer to a call she asked first about ({"args":{"text"}})
argus companion status       the signals the ticker sees right now"""


def _cli_setup(parser) -> None:
    parser.add_argument("action", nargs="?", default="status", choices=("run", "moment", "body", "away", "chess", "play", "link", "hands", "status"))
    parser.add_argument("kind", nargs="?", default="popin", help="for moment: why it came up (default popin); "
                                                                     "for body: the action")
    parser.add_argument("rest", nargs="*", help="for body: words after the action (perch discord)")
    parser.add_argument("--dry", action="store_true", help="for moment: print her decision only")
    parser.add_argument("--bot", action="store_true", help="for chess on: Hannah says this game is against a bot")
    parser.add_argument("--there", action="store_true", help="for body: her body on the other machine")


def _cli_run(args) -> int:
    from . import ticker
    folder = ticker.companion_dir()
    if args.action == "run":
        try:
            ticker.run(folder)
        except KeyboardInterrupt:
            return 0
    if args.action == "moment":
        from datetime import timedelta
        m = ticker.moment(folder)
        if args.dry:
            from . import mind
            line = mind.ask(args.kind, timedelta(minutes=0), folder, m.idle, where=ticker.where(folder),
                            gaming=ticker.game_mode())
        else:
            line = ticker.moment_now(folder, args.kind, timedelta(minutes=0), m.idle)
        print(line or "(Mira passed)")
        return 0
    if args.action == "away":
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "away").write_text("away", encoding="utf-8")
        print("Away. She'll wait until you're back at this machine.")
        return 0
    if args.action == "chess":
        return _cli_chess(folder, args)
    if args.action == "play":
        from . import room
        game = args.kind if args.kind in room.GAMES else ""
        if not room.open_window(folder, game):
            print("Her games room isn't up: is `argus companion run` running here?")
            return 1
        return 0
    if args.action == "body":
        action = " ".join([args.kind, *args.rest])
        if args.there:
            from . import link
            link.send_there(folder, action)
        else:
            ticker.body(folder, action)
        return 0
    if args.action == "link":
        from . import link
        print(link.status(folder))
        return 0
    if args.action == "hands":
        import base64
        import json

        from . import relay
        what = args.kind if args.kind in ("kit", "do", "answer") else "kit"
        call = json.loads(base64.b64decode(args.rest[0])) if what != "kit" and args.rest else None
        print(json.dumps(relay.hands(what, call)))
        return 0
    m = ticker.moment(folder)
    print(f"idle {m.idle:.0f}s  busy {m.busy}  quiet {m.quiet}  at {ticker.where(folder)}  (her log: {folder / 'checkins.log'})")
    return 0


def _cli_chess(folder, args) -> int:
    from . import chess_coach
    from .chess_engine import find_engine
    choice = args.kind if args.kind in ("on", "off", "look") else "status"
    if choice == "look":
        return _cli_chess_look(folder)
    if choice != "status":
        chess_coach.set_coach(folder, choice == "on", bot=args.bot)
    coach = chess_coach.settings(folder)
    state = chess_coach.now_state(folder)
    print(f"coaching {'on' if coach['coach'] else 'off'}{' (bot game)' if coach['bot'] else ''}; "
          f"engine {find_engine() or 'not found'}")
    if state:
        print(f"board on {state['host']}: {state['title']}\n  {state.get('fen', '(position not read yet)')}")
        if state.get("best"):
            print(f"  best {state['best']} {state['score']}  line {state.get('line', '')}")
    return 0


def _cli_chess_look(folder) -> int:
    """One look at the board on screen, and the engine's verdict (fair play applies)."""
    from . import chess_board as cb
    from . import chess_coach
    from .chess_engine import Engine, find_engine
    from .chess_eyes import Eyes
    seen = chess_coach.boards()
    if not seen:
        print("no chess board on screen")
        return 1
    board = seen[0]
    shot = chess_coach.capture(board)
    if shot is not None:
        shot.save(folder / "chess-look.png")       # what she saw, for when a board isn't found
    read = Eyes(folder).read(shot) if shot is not None else {"found": False}
    print(f"{board.host}: {board.title}{'  [maybe a live game vs a person]' if board.live else ''}")
    if not read.get("fen"):
        print("board found, but this piece set isn't learnt yet: show a starting position once" if read.get("found")
              else "couldn't find the board in the window")
        return 1
    print(read["fen"])
    path = find_engine()
    if board.live and not chess_coach.settings(folder)["bot"]:
        print("no engine: possibly a live game against a person")
    elif path:
        engine = Engine(path)
        try:
            best = engine.analyse(read["fen"]).best
        finally:
            engine.close()
        if best:
            print(f"best {cb.readable(read['fen'], best.move)} {cb.score_text(best.cp, best.mate)} (side to move)  "
                  f"line {cb.line_text(read['fen'], best.pv)}")
    return 0


def register(ctx) -> None:
    ctx.register_hook("transform_llm_output", _on_reply)
    ctx.register_hook("pre_llm_call", _on_turn)
    ctx.register_cli_command(name="companion", help="Mira's check-ins and her pet's bubble", setup_fn=_cli_setup,
                             handler_fn=_cli_run, description=USAGE)
