# ARGUS handoff (2026-11-01)

Self-contained brief for the next agent. Read this, then `argus/ARGUS.md` (design + roadmap) and
`argus/CORE-PATCHES.md` (what was changed in the inherited code and how to take upstream). Nothing else is needed
to carry on.


## What Mira can already do (researched 2026-11-02) - build on these, never beside them

- **ARGUS turns reach 150 MIRA tools** through the `mira` MCP server (relay, `argus mcp test mira` lists them):
  apps (`process_launch` on winhvk/laphvk/debhvk), real input and screen reading (`pc_screen`/`pc_input` winhvk,
  `lap_pc_screen`/`lap_pc_input` laphvk, accessibility-based), `screenshot`, live 30 fps camera/screen buffers
  (`vision_stream` + `vision_look`), music on every player (`musicbee`, `audacious`, `music_everywhere`,
  `music_download`, lyrics), calendar + reminders (`reminder_set` alarms go to Thunderbird), Discord as HavoK
  (`discord_client`), voice/notices on any device (`display_say` / `display_notify`, MIRA Link), phone control
  (`mobile_*`), TVs, PC locking, vault memory, autonomy goals/proposals, monitoring, ssh/files. So typed requests to
  her body already do Capri's "jobs" - don't rebuild app/music/input control.
- **The glance** (debhvk `mira/supervisor/glance.js`, live in `mira-supervisor`): 1-6 random looks per 2 h at
  whichever device HavoK is using, decides for itself (help when coding, coach chess from a screenshot, follow
  engagements every 20-300 s); actions: say, screen_notice, phone_widget, reminder, music, ... This IS "watch my
  screen" - the companion must not add a second watcher.
- **winhvk MiraAgent** (`D:\Network\Projects\MiraAgent`, `127.0.0.1:32768`, bearer `MIRA_AGENT_TOKEN` from the
  user env): `POST /say {text}` speaks in MIRA's voice (debhvk TTS), `POST /toast`, `/eyes/*` (vision-hub capture),
  `/desktop/input`, `/lock`, `/vi/*` (forwards to laphvk's voice). Voice interface itself is laphvk's.
- **laphvk mira-agent** (`~/.local/lib/mira-agent`): wake word, STT, TTS, follow-ups; panel `127.0.0.1:8769`
  (`POST say|speak|quiet|mic|mode|...`, `GET /status`, `/presence`, `/mira/<allowlisted read-only routes>`).
- **mira-api** (debhvk): `/greeting` (return greeting after camera+face presence), `/notify`, presence, cockpit
  agenda/music/notifications, autonomy. **No chess engine anywhere** before the companion's (Stockfish 19 is
  installed on laphvk, `/usr/bin/stockfish`).
- Chess on laphvk: chess.com in a Firefox web-app (class `WebApp-Chess4378`); winhvk: in the browser (no app).

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

## 4. Verification status of `argus-own` (second session, 2026-11-01 evening)

The first session's ~190 F marks were mostly runner artifacts (xdist crashes, and setting `HERMES_HOME` trips the
suite's real-home tripwire). Re-run per file, with a temp `HOME` and no `HERMES_HOME`, like `scripts/run_tests.sh`.

- **Runner:** `one2.sh <tree> <outdir> <file-or-nodeid>` in the session scratchpad. Its rules, keep them: temp `HOME`
  and `TMPDIR` under `~/.cache/argus-test-tmp` (NOT the system temp dir: on laphvk it is an 8 GB RAM tmpfs, and pytest's
  `pytest-of-havok` there filled it to 0 MB, which killed the Claude session and got lan-mouse OOM-killed), `--basetemp`
  inside it, deleted per file; `-P 3` at most (HavoK's live session shares the 4 cores).
- **Triage method:** run the failing files on `~/argus-base` (main) too (give it `node_modules ->
  ~/argus/node_modules` for the run, or JS tests skip there and look fixed); new = fails on argus-own only. Then swap
  in main's version of each failing test file: if main's test passes against the new code, decide by what the
  asserted string IS - text a person reads (rebrand the code) or data a program reads (revert the test).
- **Result on the 552 rebrand-touched files:** 185 new failures -> 0 (the two left, `test_update_finish` real-build
  tests, fail on main too with node_modules present).
- **Real regressions found and fixed** (all would have shipped silently - the rewritten tests agreed with the bugs):
  1. Cron lifecycle guard and terminal approval did not know the `argus` command word: `argus gateway restart`,
     `argus -p X gateway stop`, `pkill ... argus ... gateway`, `argus update` ran without approval/guard.
  2. Approval's home fold rewrote the resolved home to `~/.argus` while the policy-file patterns matched `~/.hermes`:
     `sed -i` on ARGUS's own config.yaml (the approval policy) was no longer flagged.
  3. Skill/plugin threat scanners missed `~/.argus/.env`, `config.yaml`, `SOUL.md` exfiltration.
  4. `agent/redact.py`: `config.yaml` under `.argus` now counts as secret-bearing.
  5. Worktree locks written `argus pid=` but parsed `hermes pid=`: a live `-w` worktree could be reaped.
  6. Desktop update scripts (posix.sh, windows.ps1) matched "hermes gateway restart" in a Python-produced reason.
  7. SSH/Daytona artifact paths rendered `~/.argus/...` but files sync to `~/.hermes` on the remote.
  8. Nous Portal's "serves anonymous Hermes Agent accounts only" matcher was rewritten (external text).
  9. Missed rewrites: `pm/` (never run), `locales/*.yaml` (the tool had no YAML mode), list-built commands
     (`" ".join(["hermes", ...])`), literals inside f-string `{expressions}`, bare `"hermes"` defaults, `prog ==
     "hermes"` comparisons (parser prog is `argus`), `ui-tui/scripts/gateway_bootstrap.py`.
- `argus/tools/rebrand.py`: YAML mode (values only), a `_SKIP_FILES` list of pure-fixture tests (argv, bot names,
  worktree lock reasons, service units, User-Agents, upstream tooling), documented blind spots. `CORE-PATCHES.md`
  rows 8-9 and "What the tool must not rewrite".
- **Wider run** of the 740 test files that import any module touched by these fixes: in progress at handoff time
  (results in the scratchpad `r4.summary`; compare against `b4` = main).
- `python scripts/check`: footguns, no-tmp, ruff fixed; health had 2 blocking (display.py blind except - removed, the
  call can't fail; profiles.py +2 lines - wrapper detection folded into `_WRAPPER_FLAG`, back at its 2414 cap) and the
  advisory HX012 (terminal watcher now uses `spawn_context_thread`). Re-run health before committing.

## 5. Next steps, in order

1. Finish the wider run (§4); fix anything new vs main. Re-run `python scripts/check` (health takes ~14 min).
2. Commit to `argus-own` (the worktree `~/argus-wt` holds everything, uncommitted at handoff time), push.
3. **Deploy:** `git checkout main && git merge --ff-only argus-own && git push origin main`; on laphvk
   `cd ~/argus && git pull origin main`; rebuild the TUI (`HERMES_TUI_FORCE_BUILD=1 argus`, or build in `ui-tui`).
   HavoK runs a live ARGUS TUI from `~/argus`: never kill it. Restart the gateway owner (`... gateway run --idle-exit`)
   only when idle. The live `~/.argus/SOUL.md` is still Hermes' default text: the identity upgrade rewrites it on the
   next start (legacy list).
4. Verify live: a pty capture of `argus` (no Hermes logo, "opening its eyes…"), `argus --version`, `argus estate`,
   `argus chat --oneshot -q "..."` (resume hint says `argus --resume`).
5. The Mira companion (§7), after HavoK reviews `argus/mira/SOUL.md`.
6. Roadmap (`ARGUS.md`): cockpit panes, Desktop rebrand (phase 5), ARGUS version line, Windows launcher on winhvk.

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
- Commit attribution: end commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  Don't open PRs unless asked.
- **lan-mouse (fixed 2026-11-01 22:07):** laphvk's `~/.config/lan-mouse/config.toml` had been rewritten without winhvk's
  fingerprint (restored from `JarvisInfrastructure/ops/lan-mouse/laphvk-config.toml`; the broken one kept as
  `config.toml.bak-*-emptyfp`); winhvk's daemon was wedged since 30 Oct ("no available capacity", 242 MB log) and was
  restarted via its scheduled task. What rewrote laphvk's config is unknown. Remote PowerShell on winhvk: send
  `powershell -EncodedCommand <UTF-16LE base64>`, nested quoting through ssh breaks otherwise.

## 7. One Mira: ARGUS + the companion + MIRA

HavoK (2026-11-01): MIRA is the entity and the brain, ARGUS is her house; a close best friend and partner in crime
(not romantic) who swears when Hannah does; **she is always autonomous - nobody writes her lines**. Capri Desktop
(PolyForm Noncommercial) supplied concepts only; its art is the exception, by HavoK's choice (`~/.argus/sprites/mira/`
with `NOTICE.md` and `clips.json`, git-ignored as `MiraSprites/`).

Live on laphvk (main = argus-own, deployed 2026-11-01 ~23:40):
- **Identity:** `argus/mira/SOUL.md` (+ `SOUL.compact.md`) is the one text. `DEFAULT_SOUL_MD` loads it; the live
  `~/.argus/SOUL.md` upgraded itself. Replies are labelled MIRA; ARGUS is the app name.
- **argus-companion plugin** (enabled):
  - `presence.py` only opens moments (water, stretch, eyes, session, meal, late, bored, popin) with their facts;
  - `mind.py` asks Mira herself through the provider chain (auxiliary task `companion` = the main model and its
    fallbacks; `max_tokens` 2000 because a reasoning model thinks first) with her SOUL, the memory store, recent
    talk (ARGUS sessions + MIRA's voice/phone/Discord feed cache), what she can see (laphvk window, playing,
    presence, winhvk Game Mode) and her own recent lines; she answers with her line or SKIP. Every decision is
    logged (`companion: <kind> moment -> ...` in agent.log; `checkins.log` in `~/.argus/companion/`);
  - `ticker.py` feeds signals (pet idle, Hyprland fullscreen, MIRA panel busy/quiet/presence) and delivers to the
    pet bubble + MIRA's panel `speak`;
  - a `pre_llm_call` hook tells ARGUS turns what she said on her own (once per session) and marks `talked`;
  - `voice.py` polishes chat replies (`transform_llm_output`).
  - `argus companion run | moment [KIND] [--dry] | status`; units `mira-pet`, `mira-companion` enabled.
- **MIRA voice agent** (laphvk, `~/.local/lib/mira-agent/panel.py`): loopback `POST /speak` and `GET /presence`
  (JarvisInfrastructure `ops/voice-ui/patch_panel_speak.py`, `patch_panel_presence.py`; backups `.bak-*`).
- **Lan Mouse Game Mode:** Ctrl+Alt+G on winhvk / `lan-mouse-gamemode` on laphvk (`ops/lan-mouse/README.md`).

Night of 2026-11-01/02 (HavoK asleep, asked for full Capri parity on winhvk too):
- **Pet rewrite on laphvk** (`argus/pet/mira-pet`: Sheet.qml, pet.js, shell.qml; sheets prepared by
  `argus/pet/build_sheets.py`): Capri's whole sprite life plus floor sitting/lying for tiling layouts, a body
  command channel (`body.json`, `argus companion body`-style actions), shadow, talk glow, glitch split.
- **winhvk**: ARGUS installed and running (`argus/bin/argus.ps1` fixed), the Windows body `MiraPet.exe` and the
  brain - see `argus/pet/windows/README.md` (setup, update steps, and the gotchas: brain via Startup shortcut, not a
  task; never run ARGUS turns over SSH there).
- **Her words come from MIRA's own backend** (`backend.py`, HavoK's call 2026-11-02): moments and typed messages go
  to mira-api `POST /v1/mira/call` (mode agent, `userId: companion`, `X-Jarvis-Client: api` -> session scope
  `agent:companion`), so her router picks groqcloud (short) or claude-code -> opencode, never ARGUS's provider.
  Each moment is a full Mira turn there (live-turn slot, tools, transcript): HavoK chose that over a new route.
  Credentials: winhvk user env MIRA_API/MIRA_AUTH_TOKEN; laphvk `~/.config/mira-agent/config.env`.
- **Talking to her body**: typing box (Ctrl+Alt+T on winhvk) -> `ask.json` -> the same backend session -> her
  bubble (and voice). Touch reactions via `event.json`. Moments run off the ticker loop, one at a time
  (`moment_soon`): a slow provider used to freeze the menu's Coach/Play/Settings for minutes.
- One Mira at a time: each machine's companion only reaches out while that machine is in use.
- **Greeting**: MIRA already greets Hannah on her return (winhvk camera presence + face recognition -> mira-api
  `/greeting`, facts: autonomy while away, reminders -> `/notify` -> laphvk voice). The companion's own `back`
  moment exists in presence.py but is disabled in the ticker so there's one greeting, not two. The greeting's
  persona line is part of `ops/persona/patch_mira_soul.py` (applied to source, backup, awaiting the mira-api deploy).
- **Her day in every moment**: the laphvk voice panel proxies an allowlist of read-only mira-api routes
  (`GET /mira/cockpit/agenda|cockpit/music|cockpit/notifications|autonomy/status`,
  `ops/voice-ui/patch_panel_mira_read.py`); check-ins get the agenda (overdue first) and waiting decisions.
- **Night fixes**: presence is input-based (the laphvk pet ignores idle inhibitors - a paused browser video kept her
  "present" all night); idle survives pet restarts; the scheduler remembers its gap/nights/meals across restarts
  (`scheduler.json`); `argus companion away` forces away until she's back at that machine; `quiet` file = quiet.
- Drop gestures: Shift+drop sits her right there, Ctrl+drop leaves her hanging until clicked (both bodies).
- **Chess coach** (`chess_coach.py`, `chess_eyes.py`, `chess_engine.py`, `chess_board.py`): finds a chess.com/lichess
  window, reads the exact position off the screen (board = 8x8 checker; pieces learnt from any starting position,
  stored per board style in `companion/chess-styles.json`; orientation from pawns; side to move from the last-move
  highlight), Stockfish 19 (laphvk `/usr/bin/stockfish`; winhvk `%LOCALAPPDATA%\argus\tools\stockfish`, official
  sf_19 zip, sha256 checked) gives move/score/line in her bubble when coaching is on (`argus companion chess
  on|off|look|status`, Windows menu "Coach my chess"); her own reactions to blunders, gifts, mates, game ends.
  **Fair play: no engine at all on a possibly-live game against a person** (title not computer/analysis/puzzle/
  lesson...), unless Hannah says it's a bot (`--bot`); she offers a review afterwards instead. Her turns get the
  board + engine lines (`turn_context`).
- **Games room** (`room.py` + `room.html`, 127.0.0.1:8771, per-run token in `companion/room.json`): chess against
  her (Stockfish: legal moves via perft, her moves at easy/medium/hard/full strength), tic-tac-toe, connect four,
  rock paper scissors; `argus companion play [game]` or the Windows menu; results become her moments.
- **Mini player** on both bodies (MPRIS on laphvk, Windows media session on winhvk); a ledge she hops onto.
- **Moves**: `argus companion body come_here | floor | perch WINDOW | ride | hop_off | mini_player_on/off`;
  double-click rides (click-through while riding); pop-ins and bored check-ins bring her over to the pointer first.
- **winhvk voice** via MiraAgent `POST /say`; winhvk reads MIRA's agenda from mira-api directly.
- **Reminders**: an overdue reminder is a moment, once a day each. **Game break** after 2 h in a game.
- **Voice captions**: MIRA's spoken replies on laphvk appear in her bubble (from the voice feed), never re-spoken.
- **Settings tab** in her room (`prefs.py`, `companion/settings.json`): quiet, coaching, mini player, each moment
  on/off, pop-in pace; the ticker applies it every tick. Windows menu "Settings…".
- **One Mira, two bodies** (`link.py`): laphvk serves 127.0.0.1:8772, winhvk reaches it through `mira-link.service`
  (laphvk's SSH reverse tunnel; token `companion/link-token` copied file to file). Crossing over: what's playing
  (she dances on both), quiet/coaching/settings (newest change wins, `link-switches.json`), moves for the other
  body (`argus companion body --there hop_in`). `argus companion link` shows the link. Clocks aligned per exchange.
- **Her ears / beat** (`ears.py` via parec on laphvk, `MiraPet/Ears.cs` WASAPI loopback on winhvk): tempo + beat
  phase -> `beat.json`; she nods on the beat and music notes float off her, on the playing machine's beat on both.
- **Go somewhere else** = `body elsewhere` (always moves: other window, other screen, along the floor).
- Still to do vs Capri: sound effects (no assets of hers yet), startup tendrils, next-screen commands, drawing on
  screen, Discord status, watch-along with audio, a move arrow on the coached board, laphvk sizes/tray. JarvisInfrastructure ops/ patches are still uncommitted; the mira-api persona/greeting
  patch is applied to source (backups) and waits for HavoK's guarded mira-api deploy.

Waiting on HavoK:
- **mira-api persona** (voice/phone/Discord Mira): `ops/persona/patch_mira_soul.py` is APPLIED to debhvk's source
  (backup `server.js.bak-mira-soul-*`, syntax-checked) but needs a mira-api rebuild/redeploy through MIRA's guarded
  deploy before that Mira speaks with the same SOUL. Re-sync after any SOUL edit (`ops/persona/README.md`).
- JarvisInfrastructure changes (Game Mode, panel patches, persona) are uncommitted in that repo.

Next: winhvk screen glances (mira-eyes) for what she's doing there; the day-fold memory and a running-jokes ledger in
MIRA's vault; the pet reacting while MIRA talks; mobilehvk.
