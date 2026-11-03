# Mira on Windows (winhvk)

The ARGUS service (`argus/worker/windows`) houses her here: it starts her body (`Mira.exe`, the mira-body fork) and
her companion (`argus companion run`) in HavoK's session. Her first Windows body, MiraPet, was retired on 2026-11-03
(it's in git history).

| piece | where | started by |
|---|---|---|
| ARGUS checkout | `D:\Network\Projects\Argus` (shallow clone of main) | - |
| ARGUS home | `%LOCALAPPDATA%\argus` (config.yaml and .env mirrored from laphvk; mira-skills path translated) | - |
| her body | `%LOCALAPPDATA%\Programs\Mira\Mira.exe` | the ARGUS service |
| her companion | `argus.ps1 companion run`, through `conhost --headless` | the ARGUS service |

Update after a push: `argus\pet\windows\deploy.ps1` (ARGUS and her companion), `argus\worker\windows\deploy-body.ps1`
(her body, after pulling mira-body).

Gotchas (all hit on the first night):
- **Her companion must not run under Task Scheduler.** ARGUS starts its gateway with a job breakaway, which a
  scheduled task's job forbids (`windows_breakaway_unavailable`), so a task-run companion could never answer
  what you type. The service starts it as HavoK in the desktop session, which works.
- **Never run ARGUS turns over SSH on winhvk**: they start a gateway in session 0, which the desktop session
  can't reach (`gateway_other_session`).
- Remote PowerShell: scp a `.ps1` and `-File` it; inline `-Command` quoting through ssh breaks, and
  `-EncodedCommand` hits cmd's 8191-character limit. Desktop actions (screenshots, starting apps) need a
  one-shot task, since SSH runs in session 0.
- `argus gateway install` needs an admin (UAC) approval on this account; it wasn't done unattended.
