# ARGUS - Agent Runtime for General-purpose Utility Services

HavoK's agent harness and the cockpit for the whole MIRA estate: one application that does what MIRA Desktop,
MiraAgent, Claude Code / Hermes Agent and HvkDeck each do, from a terminal or a window, on Windows and Linux.

## What ARGUS is, in one paragraph

A **soft fork of [Hermes Agent](https://github.com/NousResearch/hermes-agent)** (MIT, Nous Research). Hermes
already is a multi-provider agent harness with MCP, agentskills.io skills, subagents, cron, memory, a terminal UI,
a desktop app and a plugin system. ARGUS keeps that core, merges upstream continuously, and adds - entirely under
`argus/` - its own identity, MIRA's providers, tools and skills, and the cockpit functions that today live in
four separate apps. MIRA's own apps keep their per-device jobs; ARGUS is the one place that can do all of it.

## Decisions (HavoK, 2026-10-31)

| Question | Decision |
|---|---|
| Fork style | **Soft fork.** Upstream keeps merging; ARGUS lives under `argus/` and in plugins. |
| Surfaces | **TUI + core server + Desktop**, with most of the effort on the TUI and the server side. The aim is a harness HavoK prefers to Claude Code and opencode. |
| Process model | `TUI process  <->  core server process  <->  Desktop process` (one core, two clients). |
| MIRA's services | **Front them, replicate their functions, never replace MIRA's apps.** mira-api, mira-mcp, hvkdeckd and MiraAgent keep running; MIRA Desktop / Mobile / laphvk VI keep their device roles. |
| Repository | GitHub fork `hav0kdotsys/argus` of NousResearch/hermes-agent. Developed on laphvk (`~/argus`). |
| Default free model | Big Pickle where it is available; see "Providers" for why ARGUS cannot rely on Zen's free tier. |

## Process model

```
 argus (TUI, Ink)            ARGUS Desktop (Electron)          other clients (dashboard, remote, scripts)
        \                              |                                  /
         \--- JSON-RPC over WebSocket (ws://127.0.0.1:<port>/api/ws, per-client ticket) ---/
                                        |
             ARGUS core server = the profile's gateway owner (`argus gateway run`, Python)
          agent loop - providers + fallback - MCP client - skills - memory - cron - subagents
                                        |
         MIRA's MCP (relay)  -  mira-api  -  hvkdeckd (debhvk)  -  MiraAgent (winhvk)  -  local tools
```

Hermes already ships this split: one owner process per profile home serves the JSON-RPC methods (`tui_gateway/`)
over WebSocket; each client gets a short-lived ticket from the owner's private control socket. `argus serve` is
a separate headless web backend (dashboard / remote Desktop). ARGUS makes the long-lived owner the default shape
(`argus gateway install`) rather than one that the first TUI starts and that exits when idle.

## How ARGUS stays a soft fork

1. **Everything ARGUS-specific is under `argus/`** (launchers, installers, skins, plugins, config, docs) or in
   `$ARGUS_HOME` - never sprinkled through Hermes' tree. Upstream merges then never conflict with ARGUS.
2. **Identity through Hermes' own seams:**
   - the home: `$ARGUS_HOME` (`~/.argus`, `%LOCALAPPDATA%\argus`), passed to the core as `HERMES_HOME`
     (7,000+ references; renaming it would be a hard fork);
   - the look and name: the `argus` skin (banner, palette, spinner, `ARGUS` branding) through the skin engine,
     which every surface - CLI, TUI, Desktop - reads;
   - the command: `argus` (`argus/bin/argus`, `argus.ps1`, `argus.cmd`), which runs this checkout's `hermes`
     entry in its managed environment and keeps the caller's working directory.
3. **New capability = a plugin** (Hermes' contract: plugins never touch core). Where Hermes lacks a seam, widen
   the generic plugin surface the way upstream would accept, and send it upstream.
4. **Core edits are the exception** and each one is listed in `argus/CORE-PATCHES.md` with why, so a merge
   conflict is always explicable. (Expected first ones: the Desktop app's product name, window title and icon.)
5. **Upstream sync:** `git fetch upstream && git merge upstream/main` on the `argus` branch, weekly or when a
   fix is wanted; run `scripts/check` and ARGUS's own smoke test before pushing.

## Layout (`argus/`)

```
argus/
  ARGUS.md              this file
  bin/argus             launcher (Linux/macOS/WSL)    bin/argus.ps1, bin/argus.cmd  (Windows)
  install.sh / .ps1     overlay -> $ARGUS_HOME (idempotent; links skins/plugins, seeds config once)
  config/config.yaml    the seed config (MIRA's MCP via the relay, MIRA's skills dir, argus skin)
  skins/argus.yaml      the ARGUS skin
  plugins/              (phase 2) model-providers/*, mira cockpit tools, delegation backends
  CORE-PATCHES.md       (when the first one exists) every edit outside argus/
```

## Providers

ARGUS uses Hermes' provider registry and fallback chain (`fallback_providers`); what HavoK has:

| Provider | Hermes id | Status |
|---|---|---|
| NVIDIA NIM | `nvidia` (`NVIDIA_API_KEY`) | **live, primary**: `minimaxai/minimax-m3.1-flash` (~4 s) and `mistralai/mistral-large-4-1t-a52b` (~14 s) call tools. Free-tier queues time some models out (DeepSeek v4.1 Flash, GLM-5.3 Flash at 60 s); Kimi K2.6, Nemotron Ultra and Mistral Large 2 are not enabled for the account. |
| Cloudflare Workers AI | named provider `cloudflare` (`providers:` map, `key_env: CLOUDFLARE_API_TOKEN`) | **live** on the Workers Free plan: gpt-oss-120b (0.7 s), nemotron-3-120b, llama-3.3-70b, qwen3-30b, qwen3.8-27b, glm-4.7-flash, gemma-4-26b, mistral-small-3.1 all call tools. GLM-5.3, Kimi K2.6/K2.7, DeepSeek V4 need a paid plan (403). Free plan has a daily allowance - a fallback, not the workhorse. |
| Z.ai (GLM) | `zai` (`GLM_API_KEY`) | key valid (lists glm-4.5 ... glm-5.3), but chat answers **"Insufficient balance or no resource package"** on both the standard and coding endpoints. Top of the chain once funded. |
| Gemini | `gemini` | MIRA's AI Studio key could be shared |
| Groq | (via `custom`/openrouter-style profile) | MIRA has a key; free tier is small |
| Ollama Cloud | `ollama-cloud` (`OLLAMA_API_KEY`) | gpt-oss:120b is in the free usage |
| OpenCode Zen | `opencode-zen` | **paid models only for ARGUS**: Zen serves its *free* models (Big Pickle, nemotron-3.5-lightning) only to OpenCode's own clients - not to direct API calls, not to `opencode serve` (tested 2026-10-31). ARGUS will not pose as OpenCode to get them. |
| Claude (subscription) | - | Not an API provider. Phase 2: MIRA's claude-code sidecar as a **delegation backend** (a subagent ARGUS can hand whole tasks to), not as a chat-completions model. |
| Local (winhvk qwen3:4b, LM Studio) | `custom` / `lmstudio` | offline last resort |

Keys live only in `$ARGUS_HOME/.env` (mode 600), referenced from config as `${VAR}`; never in git.

## MIRA integration

- **Tools:** MIRA's MCP server (`mira`, ~140 tools: phone, PCs, TV, music, calendar, vault, estate, guard)
  through the Cloudflare relay with `JARVIS_MCP_TOKEN`. Not the LAN: mira-mcp deliberately refuses `/mcp` from
  the LAN (2026-10-27 guard).
- **Skills:** MIRA's `SKILL.md` skills are agentskills.io-compatible; ARGUS reads them read-only from
  `$ARGUS_HOME/mira-skills` (`skills.external_dirs`), synced from debhvk's skills folder.
- **Autonomy:** MIRA's supervisor stays the owner of unattended work; ARGUS shows and steers it (goals,
  proposals, glance, approvals) rather than running a second autonomy loop.

## Cockpit functions to replicate (phase 3+)

| From | Functions |
|---|---|
| HvkDeck | estate overview (CPU/mem/net/temps/disks/failed units), containers (logs, inspect, start/stop/restart), stacks & deploys (manage.sh, mira-deploy), services + journal, processes, console, files, network, jobs |
| MIRA Desktop | conversation + sessions, cockpit widgets (vitals, core, agenda, music, notifications, minimap, screen, streams), map, camera/vision, MIRA Link broadcast, providers/budget, people & access, autonomy |
| MiraAgent (winhvk) | screen/window/input, process launch/end, lock + presence, eyes (camera/screen streams) - via MIRA's MCP, which already drives MiraAgent |
| Mobile | phone status, notifications, the widget canvas (kit), screen record, music |

In the TUI these become panels and slash commands (`/estate`, `/containers`, `/deploy`, `/phone`, `/widgets`,
`/autonomy` ...) backed by plugin tools; in the Desktop app, pages and cockpit widgets.

## Roadmap

1. **Foundation - done (2026-10-31):** fork, `argus` command (sub-second start), `~/.argus`, skin, seed
   config. MIRA's MCP live through the relay (150 tools), MIRA's 15 skills synced (`sync-mira-skills.sh`).
2. **Providers - mostly done (2026-10-31):** NIM primary + Cloudflare/NIM fallback chain live-tested; a real
   turn (`argus chat --oneshot`) answered from MIRA's tools. Still to do: Z.ai once funded, Gemini / Ollama Cloud
   keys, the claude-code sidecar as a delegation backend, `argus doctor` green.
3. **Server-first - built in upstream, verified (2026-10-31):** Hermes already runs ONE long-lived core server
   per profile home (the gateway "owner", `argus gateway run`): the Ink TUI asks a private control socket for a
   short-lived ticket and attaches over WebSocket (`ws://127.0.0.1:<port>/api/ws`, loopback, ticket in the
   subprotocol header); Desktop attaches to the same owner. Verified on laphvk: two separate TUI bootstraps
   got the same instance. ARGUS's part: make the TUI the default interface (`display.interface: tui`) and run
   the owner as a service instead of letting it idle-exit - `argus gateway install` (Hermes' own systemd /
   launchd / Windows-task installer; the unit pins HERMES_HOME=~/.argus and refuses to touch another install's).
4. **Cockpit plugin pack:** HvkDeck and MIRA Desktop functions as tools + TUI panels + Desktop pages.
5. **Desktop rebrand + builds:** ARGUS name/icon (CORE-PATCHES), Windows installer and Linux AppImage/deb.
6. **Polish to beat Claude Code / opencode:** the things HavoK uses daily, measured by HavoK.

## Licence

Hermes Agent is MIT-licensed (c) 2025 Nous Research; its LICENSE stays in the repository root unchanged.
ARGUS's additions are HavoK's.
