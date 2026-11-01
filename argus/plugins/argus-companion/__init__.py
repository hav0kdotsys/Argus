"""argus-companion - Mira as a companion, not an assistant.

- Her voice, enforced in code (``voice.py``) on every reply through ``transform_llm_output``. It runs only on the
  reply being finished, never on earlier turns or the system prompt, so the prompt cache is untouched, and it leaves
  work output (code, lists, tables, long reports) exactly as written.
- Her own check-ins: ``presence.py`` opens moments from laphvk's signals (``ticker.py``), and ``mind.py`` asks MIRA
  herself, through the provider, with her memory and what she can see, whether and what to say - nobody writes her
  lines. ``argus companion run`` ticks (the mira-companion unit runs it); what she says lands in her pet's bubble
  (argus/pet/mira-pet) and out loud through MIRA's voice panel.

- One Mira: every ARGUS turn tells her what she said on her own since that session last heard from her
  (``pre_llm_call`` context on the user message, never the system prompt), and marks that Hannah talked to her (the
  ticker's ``bored`` moment needs it).

Later slices: the day-by-day memory fold, screen glances, perching on windows, winhvk and the phone.
"""

from __future__ import annotations

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


def _on_turn(session_id: str = "", **_: Any) -> dict | None:
    from datetime import datetime, timedelta
    folder = _companion_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "talked").write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    try:
        lines = (folder / "checkins.log").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    key = session_id or ""
    since = _heard.pop(key, None) or (datetime.now() - timedelta(hours=_SEEN_HOURS)).strftime("%Y-%m-%d %H:%M")
    words = own_words_since(lines, since)
    _heard[key] = max([since] + [line[:16] for line in lines if len(line) >= 16])
    while len(_heard) > _SESSIONS:
        _heard.popitem(last=False)
    if not words:
        return None
    return {"context": "[What you said to Hannah on your own lately (out loud and in your bubble on laphvk), "
                       "so you know if she's answering it:\n" + "\n".join(words) + "]"}


USAGE = """argus companion run          offer Mira moments as they come up (foreground; Ctrl-C stops)
argus companion moment [KIND] [--dry]  offer her one now (water, stretch, eyes, session, meal, late, bored, popin);
                             --dry prints what she'd do without showing or saying it
argus companion status       the signals the ticker sees right now"""


def _cli_setup(parser) -> None:
    parser.add_argument("action", nargs="?", default="status", choices=("run", "moment", "status"))
    parser.add_argument("kind", nargs="?", default="popin", help="for moment: why it came up (default popin)")
    parser.add_argument("--dry", action="store_true", help="for moment: print her decision only")


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
    m = ticker.moment(folder)
    print(f"idle {m.idle:.0f}s  busy {m.busy}  quiet {m.quiet}  (lines: {folder / 'check-ins.md'})")
    return 0


def register(ctx) -> None:
    ctx.register_hook("transform_llm_output", _on_reply)
    ctx.register_hook("pre_llm_call", _on_turn)
    ctx.register_auxiliary_task("companion", display_name="Mira's own check-ins",
                                description="Mira deciding whether and what to say when a moment comes up "
                                            "(follows the main model unless set)", defaults={"timeout": 90})
    ctx.register_cli_command(name="companion", help="Mira's check-ins and her pet's bubble", setup_fn=_cli_setup,
                             handler_fn=_cli_run, description=USAGE)
