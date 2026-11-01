# Changes to the inherited codebase - and how to take things from upstream

ARGUS owns its whole tree (see `ARGUS.md`, "Owning the codebase"); this file is no longer a list ARGUS tries
to keep short. It records the changes that matter when something is taken from Hermes upstream, so a conflict
is always explicable.

| # | Where | What | Note for an upstream merge |
|---|---|---|---|
| 1 | `apps/shared/src/skin.ts`, `ui-tui/src/theme.ts`, `ui-tui/src/components/branding.tsx`, `ui-tui/src/app/useMainApp.ts` | Skin tokens `branding.icon`, `.tagline`, `.byline`; terminal title from the skin's agent name. | Generic - also offerable upstream. |
| 2 | ~1,400 files (Python packages incl. `pm/`, `ui-tui/src`, `tests`, the `locales/*.yaml` i18n catalogues) | The rebrand: user-facing strings say ARGUS (`argus/tools/rebrand.py`; YAML: values only, keys untouched). | Take upstream's version of a conflicting file, then re-run the tool on it. |
| 3 | `ui-tui/src/theme.ts`, `ui-tui/src/banner.ts`, `hermes_cli/skin_engine.py` | ARGUS is the built-in brand, palette and art; the skin engine's `default` is `argus/skins/argus.yaml`, gold Hermes is `hermes-classic`. | Keep ARGUS's seeds/art; take upstream's logic. |
| 4 | `hermes_cli/default_soul.py`, `agent/prompt_builder.py` | The identity: "You are ARGUS ... built by HvkSys". The legacy list keeps the exact Hermes texts so older SOUL.md files are still recognised and upgraded. | Hand-edited (the tool skips `default_soul.py`); never rebrand the legacy entries. |
| 5 | Lines ending `# rebrand: keep` | Contracts that read Hermes-era text: profile wrappers (`hermes -p`), rc markers, update-log lines, desktop binary names, webhook `~/.hermes` paths, the Docker image's `hermes` user, and **text a program sends us** (Nous Portal's "serves anonymous Hermes Agent accounts only" in `hermes_cli/anon_auth.py`). | Keep both old and new forms; external text stays verbatim. |
| 6 | `hermes_cli/main_tui_launch.py` | Terminal-gone watcher: the TUI and its launcher exit once the controlling pty is deleted. | ARGUS fix; also offerable upstream. |
| 7 | `ui-tui/src/app/userMessages.ts` | The unavailable-method check matches "ARGUS" and "Hermes" backends. | Keep both. |
| 8 | `hermes_cli/_parser.py`, `hermes_cli/left_core_migration.py`, `hermes_cli/console_engine.py` | Code that compares against the program name says `argus` (the parsers' `prog`); the console accepts a leading `argus` or `hermes`. | Re-check any new `prog == "hermes"` from upstream. |
| 9 | `agent/redact.py` | `config.yaml` under a `.argus` directory counts as secret-bearing, like `.hermes`. | Keep `.argus` in `_HOME_DIR_NAMES`. |

**What the tool must not rewrite** (check the diff after every run): process argv fixtures (a real process line
always says `hermes`: the launcher execs `python <repo>/hermes`), chat-platform bot names in adapter tests, and
any string matched against external input. Test files that are pure fixtures of this kind are in the tool's
`_SKIP_FILES`.

## Taking from upstream

```bash
git fetch upstream
git merge upstream/main            # or: git cherry-pick <sha> for one fix
python3 argus/tools/rebrand.py <the changed paths>     # idempotent; prints how many files it changed
HERMES_TUI_FORCE_BUILD=1 argus     # rebuild the TUI
```
Then run the TUI checks (`cd ui-tui && npx tsc --noEmit -p tsconfig.json && npx vitest run`) and the Python
tests for what changed, and `argus --version` plus a TUI smoke test.
