"""argus-companion - Mira as a companion, not an assistant.

- Her voice, enforced in code (``voice.py``) on every reply through ``transform_llm_output``. It runs only on the
  reply being finished, never on earlier turns or the system prompt, so the prompt cache is untouched, and it leaves
  work output (code, lists, tables, long reports) exactly as written.
- Her own check-ins: ``presence.py`` opens moments from laphvk's signals (``ticker.py``), and ``mind.py`` asks MIRA
  herself, through the provider, with her memory and what she can see, whether and what to say - nobody writes her
  lines. ``argus companion run`` ticks (the mira-companion unit runs it); what she says lands in her pet's bubble
  (argus/pet/mira-pet) and out loud through MIRA's voice panel.

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
            line = mind.ask(args.kind, timedelta(minutes=0), folder, m.idle)
        else:
            line = ticker.moment_now(folder, args.kind, timedelta(minutes=0), m.idle)
        print(line or "(Mira passed)")
        return 0
    m = ticker.moment(folder)
    print(f"idle {m.idle:.0f}s  busy {m.busy}  quiet {m.quiet}  (lines: {folder / 'check-ins.md'})")
    return 0


def register(ctx) -> None:
    ctx.register_hook("transform_llm_output", _on_reply)
    ctx.register_auxiliary_task("companion", display_name="Mira's own check-ins",
                                description="Mira deciding whether and what to say when a moment comes up "
                                            "(follows the main model unless set)", defaults={"timeout": 90})
    ctx.register_cli_command(name="companion", help="Mira's check-ins and her pet's bubble", setup_fn=_cli_setup,
                             handler_fn=_cli_run, description=USAGE)
