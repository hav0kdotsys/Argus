# ARGUS handoff (2026-11-01)

Self-contained brief for the next agent. Read this, then `argus/ARGUS.md` (design + roadmap) and
`argus/CORE-PATCHES.md` (what was changed in the inherited code and how to take upstream). Nothing else is needed
to carry on.

## 1. Who and what

- **User: HavoK** (havokthedev@gmail.com). Wants autonomous work: deploy live, verify, then move on. Plain, short
  reports. Never echo or commit secrets (API keys live only in `~/.argus/.env` on laphvk).
- **ARGUS** = "Agent Runtime for General-purpose Utility Services". It started as a fork of NousResearch/hermes-agent
  (MIT). **Latest decision (2026-10-31): it is HavoK's own app**, no longer a soft fork:
  > "this is MY app now, something new, more than an agent harness like Hermes, a housing unit for Mira and every
  > device I own." ... "moving to refinement and improving the application, not cleaning up Hermes slop".
  So: change the core freely, ARGUS everywhere a person reads, and take from upstream only deliberately.
- **Target shape:** TUI <- core server (the gateway owner) -> Desktop. Most effort goes into the TUI and the server
  side ("a perfected, custom alternative to Claude Code and opencode"). The aim is a cockpit for the MIRA estate:
  replicate the MIRA Desktop / MiraAgent / HvkDeck functions, and **front MIRA's services, never replace them**.
  Windows and Linux.

## 2. Where things are

| Thing | Location |
|---|---|
| Repo | `github.com/hav0kdotsys/Argus` (remotes: `origin` = that, `upstream` = NousResearch/hermes-agent). Local clone in the cloud session: `/home/user/argus`. |
| Branches | `main` = last deployed state (`9ba3628f`). **`argus-own` = all of this session's work (head `a6a649d6`, 7 commits ahead of main, a fast-forward). NOT merged or deployed yet.** |
| Dev host | **laphvk** (CachyOS, Hyprland, **fish shell, so wrap commands in `bash -c '...'`**). Checkout `~/argus`, on branch `argus`, tracking `origin/main`. Launcher `~/.local/bin/argus` -> `~/argus/argus/bin/argus`. Home `~/.argus` (passed to the core as `HERMES_HOME`). |
| Test worktrees on laphvk | `~/argus-wt` (detached at `argus-own`) and `~/argus-base` (detached at main `9ba3628f`), for tests without touching the live `~/argus`. Remove both with `git worktree remove` when done. |
| Python env (laphvk) | Interpreter `~/.argus/tools/python-3.14.9+20261021-linux-x64/bin/python3`; site-packages `~/.argus/installs/ca43ce431c6bd99d/environments/613761177a1f4576b987ca0faf8debfd/venv/lib/python3.14/site-packages`; pytest tooling installed separately in `~/.cache/argus-pytest` (pytest 9.1.1, pytest-asyncio, xdist, anthropic). |
| Node (laphvk) | `~/.argus/tools/node-26.12.1-linux-x64/bin`; workspace `node_modules` is hoisted to the repo root (`~/argus-wt/node_modules -> ~/argus/node_modules`). |
| Access | jarvis MCP tools via the relay `jarvis-mcp-relay.moonauth.dpdns.org`: `mcp__jarvis__ssh_exec` (host `laphvk` / `debhvk`) **has a 15 s timeout**, so start long jobs with `setsid nohup ... &` and poll. The MCP server may need reconnecting after a session restart. To move files: push to GitHub, then `git fetch` on laphvk (or base64 through ssh_exec for small scripts). |
| Other repo | `hav0kdotsys/JarvisInfrastructure`, branch `havok/fervent-babbage-d64j7z`: MIRA ops (supervisor, mobile, providers). Its `ops/argus/README.md` points to Argus. |

## 3. Done this session (all on `argus-own` unless noted)

1. **debhvk disk: done and live.** `docker image prune -f` + `docker builder prune -af` reclaimed ~22 GB (86% -> 63%,
   37 GB free). Tagged images and volumes were untouched; all 29 containers stayed up.
2. **Rebrand ("ARGUS is the product")**, via `argus/tools/rebrand.py`:
   - A string-literal-exact rewriter: Python via tokenize, TS via a literal scanner. It skips comments, docstrings
     and imports; a trailing `# rebrand: keep` protects a line; `_SKIP_FILES` covers the hand-edited files. It is
     idempotent (`--check` reports 0) and is applied to the Python packages, `ui-tui/src` and `tests`.
   - Left unchanged on purpose: `HERMES_*` env vars, module/package/toolset ids, Nous' Hermes **model** names, the
     "Hey Hermes" wake word (trained hotword model `hey_hermes`), and the Docker/s6 `hermes` user and binary.
   - Lines hand-fixed to accept both old and new forms (tagged keep):
     - profile wrappers (`hermes -p` / `argus -p`) in `profiles.py` and `doctor_state.py`;
     - the rc marker in `uninstall.py`;
     - update-log lines in `web_routers/actions.py`;
     - desktop binary and `.desktop` names in `linux_desktop_entry.py` and `main_desktop.py`;
     - webhook `~/.hermes` paths in `gateway/platforms/webhook_filters.py`;
     - the skill linter;
     - `_LOG_CHROME` in `kanban_db_dispatch.py`;
     - docker/s6 lines in `service_manager.py`, `gateway/pairing.py` and `cron.py`.
   - argparse `prog="argus"` (`_parser.py`, `console_engine.py`).
   - Identity: `hermes_cli/default_soul.py` and `agent/prompt_builder.py` now say "You are ARGUS ... HavoK's own agent
     runtime ... built by HvkSys". The legacy list keeps the exact Hermes texts, so an old SOUL.md is still
     recognised and upgraded in place (verified).
   - Skin engine: built-in `default` = `argus/skins/argus.yaml`; gold Hermes stays selectable as `hermes-classic`;
     shared built-in branding is ARGUS.
3. **Hermes logo flash at TUI start (user report): fixed** by making ARGUS the TUI's built-in defaults:
   - `ui-tui/src/theme.ts`: BRAND plus orchid DARK/LIGHT seeds;
   - `ui-tui/src/banner.ts`: ARGUS logo and the eye, redrawn at 28 columns so the banner layout isn't squeezed;
     the same art is in the skin's `banner_hero`.
   The flash happened on a boot-cache miss, when the stock Hermes defaults were drawn before the skin arrived.
4. **Orphaned TUI spinning at ~90% CPU** after its terminal closed: `hermes_cli/main_tui_launch.py` gained
   `_exit_when_terminal_closes()`. A watcher thread checks `/proc/self/fd/0` for "(deleted)" and, once the terminal
   is gone, kills the launcher's children (TERM, then KILL) and exits. Tested locally in a real pty with a
   hangup-immune child. The root cause was never reproduced; this guard holds whatever the cause.
5. **Cloudflare replies truncated** (`finish_reason=length`): **live config on laphvk** now has
   `providers.cloudflare.extra_body.max_tokens: 8192` (backup `~/.argus/config.yaml.bak-cfmax`). The seed config
   documents it too. Verified: 60 lines plus DONE, not cut off.
6. **`argus update` updates from ARGUS's own repo only.** `_sync_with_upstream_if_needed` returns early unless
   `ARGUS_UPDATE_FROM_UPSTREAM=1`. `tests/conftest.py` sets that variable so the inherited upstream-sync tests still
   run; `tests/hermes_cli/test_argus_update_origin_only.py` pins the default.
7. Tool rows: a tool without a curated verb shows its title ("Estate Overview" rather than "Estate_overview"), in
   `agent/display.py` `_cute_fallback_row`. Cockpit tool icons are in the skin (`tool_emojis`), because the
   one-shot client process doesn't load plugins.
8. TUI version-skew regex accepts both "ARGUS" and "Hermes" backends (`ui-tui/src/app/userMessages.ts`).
9. Docs: `ARGUS.md` reframed (owned app, "Owning the codebase"); `CORE-PATCHES.md` rewritten as a
   change log plus an "intake from upstream" guide.
10. Earlier (on main, deployed): the **argus-cockpit plugin**, `argus/plugins/argus-cockpit/`.
    - Six read-only `estate_*` tools backed by hvkdeckd, using the credentials in `~/.config/hvkdeck/credentials.json`
      (LAN first, then the Cloudflare Access remote).
    - Also exposed as `/estate` and `argus estate`. Enabled via `plugins.enabled: [argus-cockpit]`.
    - Verified live.

## 4. Verification status of `argus-own`

- TUI: `tsc --noEmit` passes; **vitest 1906 passed / 0 failed** (in `~/argus-wt`).
- Python: the run of the **597 test files the rebrand touched** was still going (~42%, with ~190 F marks so far) when
  the session restarted. **The F marks are not yet triaged**; many may be pre-existing or environment-caused.
  - Runner: `~/.cache/argus-runtests.sh <tree> <list> <out>`. List: `~/.cache/argus-tests.list`.
    Outputs: `~/.cache/argus-tests-new.out` (argus-own) and then `~/.cache/argus-tests-base.out` (main), chained
    in one nohup job (`nice -n 15`, `-n 3`). The process may have died in the restart:
    `pgrep -af "pytest -q"` to check.
  - The commits after `6b6d6ccd` changed `tests/conftest.py`, `agent/display.py` and `update_cmd_git.py`; the
    worktree was moved to newer heads during the run, so **re-run on a clean checkout of the final head**.
  - **Faster plan:** when the new run ends, take its failing test IDs (`grep -E "^FAILED"`), kill the base pass, and
    run only those IDs in `~/argus-base`. A failure that occurs in both trees is pre-existing; one that only
    appears on `argus-own` is a regression to fix. The likely kind: a test asserting a string that the code side
    generates differently, or a Python-generated message that a test or another component matches.

## 5. Next steps, in order

1. Finish the test triage in §4 and fix the regressions. Re-run `python3 argus/tools/rebrand.py --check <paths>`
   after any edit; it must report 0.
2. **Deploy `argus-own`.**
   - Fast-forward: `git checkout main && git merge --ff-only argus-own && git push origin main`.
   - On laphvk: `cd ~/argus && git pull origin main`.
   - Then rebuild the TUI. `ui-tui/dist` is a single 4 MB `entry.js` bundle, which a running node holds in memory,
     so a rebuild is safe. Force it with `HERMES_TUI_FORCE_BUILD=1 argus`, or build in `ui-tui`.
   - **HavoK had a live ARGUS TUI session running from `~/argus`** (pid 760059 / node 760316 at the time). Don't kill
     it. The gateway owner (`... gateway run --idle-exit`) loads plugins and code once: restart it only when idle
     (`argus gateway restart`, or `kill` the owner pid; the next client starts a fresh one).
3. Verify live, then report back:
   - in a pty: `script -q -f -c "argus" /tmp/x.raw` under `timeout`, then grep the capture: there should be no
     Hermes logo, and the status should read "opening its eyes…";
   - `argus --version` and `argus estate`;
   - a one-shot turn: `argus chat --oneshot -q "..."`. The resume hint should now say `argus --resume`.
4. Continue the roadmap (`ARGUS.md` §Roadmap):
   - phase 4 cockpit: a live estate TUI pane, phone/widgets/autonomy views, and `/deploy` as a guarded write
     through MIRA's tools;
   - phase 5: Desktop rebrand (`apps/desktop` still says Hermes everywhere; run the rebrand tool there, but its
     Electron product name and binary need care) plus Windows/Linux builds;
   - an ARGUS version line and releases (currently it reports Hermes' `v0.22.5`);
   - Windows: `argus/bin/argus.ps1` / `.cmd` have never been tested on winhvk.

## 6. Known open items and gotchas

- **Stray `~/.hermes` on laphvk** (only `tools/`, 37 MB, from my first bootstrap at 06:20) and a
  `~/.local/bin/hermes` wrapper (`exec ~/argus/.hermes/bin/hermes`) written by Hermes' own setup. Deleting `~/.hermes`
  was **blocked by the permission classifier**: leave it for HavoK to remove.
- Plugin tools always sit behind the tool-search bridge (deferred). That's fine today: 162 deferred tools, and the
  full listing fits in the 4k budget.
- Enabling a plugin requires a fresh gateway owner.
- NIM (primary model `minimaxai/minimax-m3.1-flash`) rate-limits at times; the Cloudflare fallback chain works
  (verified live).
- Z.ai key: no balance. Zen free models only work in OpenCode's own clients. No Anthropic API keys; Azure was dropped.
- Permission classifier denials seen so far: deleting user files, putting a token in the shell, materialising
  credentials, running Python inside a downloaded clone in the sandbox, installing persistent services.
  `argus gateway install` is left for HavoK to run.
- Left for HavoK: `argus gateway install`; a Caelestia restart for the laphvk Safe Mode button; funding Z.ai;
  removing the `AZURE_*` env vars.
- JarvisInfrastructure open items:
  - winhvk fingerprint (needs HavoK's decision);
  - the mobile Safe Mode button;
  - 3 pre-existing supervisor test-executor failures;
  - merging `havok/fervent-babbage-d64j7z` to main.
- Commit attribution: end commit messages with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01RcQJHhH8JaGeAiVjjfohFQ`.
  Don't open PRs unless asked.
