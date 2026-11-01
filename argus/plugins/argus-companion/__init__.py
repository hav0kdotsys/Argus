"""argus-companion - Mira as a companion, not an assistant.

- Her voice, enforced in code (``voice.py``) on every reply through ``transform_llm_output``. It runs only on the
  reply being finished, never on earlier turns or the system prompt, so the prompt cache is untouched, and it leaves
  work output (code, lists, tables, long reports) exactly as written.
- Her check-ins (``presence.py`` decides, ``ticker.py`` feeds it laphvk's signals): ``argus companion run`` ticks and
  puts the line in her pet's bubble (argus/pet/mira-pet); ``argus companion say "..."`` makes her say anything.

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


USAGE = """argus companion run          tick check-ins and show them in Mira's bubble (foreground; Ctrl-C stops)
argus companion say TEXT     make Mira say TEXT in her bubble
argus companion status       the signals the ticker sees right now"""


def _cli_setup(parser) -> None:
    parser.add_argument("action", nargs="?", default="status", choices=("run", "say", "status"))
    parser.add_argument("text", nargs="*", help="for say: what she says")


def _cli_run(args) -> int:
    from . import ticker
    folder = ticker.companion_dir()
    if args.action == "run":
        try:
            ticker.run(folder)
        except KeyboardInterrupt:
            return 0
    if args.action == "say":
        text = " ".join(args.text).strip()
        if not text:
            print("companion: say needs some text")
            return 1
        ticker.say(folder, text)
        return 0
    m = ticker.moment(folder)
    print(f"idle {m.idle:.0f}s  busy {m.busy}  quiet {m.quiet}  (lines: {folder / 'check-ins.md'})")
    return 0


def register(ctx) -> None:
    ctx.register_hook("transform_llm_output", _on_reply)
    ctx.register_cli_command(name="companion", help="Mira's check-ins and her pet's bubble", setup_fn=_cli_setup,
                             handler_fn=_cli_run, description=USAGE)
