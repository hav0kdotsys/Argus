# Mira on Windows (winhvk)

Her body (`MiraPet.exe`) and her brain (`argus companion run`) on Windows, set up 2026-11-02. Same sheets, rules and
companion protocol as laphvk (`argus/pet/mira-pet`): `%ARGUS_HOME%\companion\` holds `say.json`, `body.json`,
`ask.json`, `event.json`, `state.json` and `quiet`; `%ARGUS_HOME%` is `%LOCALAPPDATA%\argus`.

| piece | where | started by |
|---|---|---|
| ARGUS checkout | `D:\Network\Projects\Argus` (shallow clone of main) | - |
| ARGUS home | `%LOCALAPPDATA%\argus` (config.yaml and .env mirrored from laphvk; mira-skills path translated) | - |
| her sprites | `%LOCALAPPDATA%\argus\sprites\mira\grid` (built on laphvk by `argus/pet/build_sheets.py`, copied) | - |
| body | `argus\pet\windows\MiraPet\bin\Release\net9.0-windows10.0.19041.0\MiraPet.exe` | Scheduled Task **MIRA-Pet** (at logon) |
| brain | `argus.ps1 companion run` | Startup-folder shortcut **MIRA Companion** (not a task, see below) |

Update after a push: run `argus\pet\windows\deploy.ps1` on winhvk (it stops both, resets the checkout to main, rebuilds
the body, starts the body task and relaunches the brain through the shell).

Drop her with **Shift** held and she sits right there; with **Ctrl** she hangs there until clicked.
Double-click her to ride your cursor (clicks pass through her while she rides). Tell her where to go:
`argus companion body come_here | floor | perch discord | perch player` (she understands it when you ask her, too).
Her mini player shows bottom-left while anything plays (menu: Mini player); she hops onto it when it comes up.
Her keys (from anywhere): **Ctrl+Alt+T** type to her, **Ctrl+Alt+H** hide/show, **Ctrl+Alt+P** quiet, **Ctrl+Alt+C** ride your cursor / hop off (dragging her off ends it too). Middle-click
her to type; right-click or the tray icon for the menu (show/hide, quiet, dance, nap, go somewhere else, size, stay
over games, quit). She ducks out of fullscreen apps unless "Stay over games" is on.

Gotchas (all hit on the first night):
- **The brain must not run under Task Scheduler.** ARGUS starts its gateway with a job breakaway, which a
  scheduled task's job forbids (`windows_breakaway_unavailable`), so a task-run companion could never answer
  what you type. Shell-launched (the Startup shortcut, via `conhost --headless`) works. The body is fine as a task.
- **Never run ARGUS turns over SSH on winhvk**: they start a gateway in session 0, which the desktop session
  can't reach (`gateway_other_session`). Remote tests: write `ask.json` and read `say.json` instead.
- Remote PowerShell: scp a `.ps1` and `-File` it; inline `-Command` quoting through ssh breaks, and
  `-EncodedCommand` hits cmd's 8191-character limit. Desktop actions (screenshots, starting apps) need a
  one-shot task, since SSH runs in session 0.
- `argus gateway install` needs an admin (UAC) approval on this account; it wasn't done unattended.
- Not yet on Windows: speaking out loud (MIRA's voice lives on laphvk; winhvk shows the bubble only).
