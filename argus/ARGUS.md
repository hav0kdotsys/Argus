# ARGUS - Agent Runtime for General-purpose Utility Services

HavoK's own application: the housing unit for MIRA and every device HavoK owns. One program that does what MIRA
Desktop, MiraAgent, Claude Code and HvkDeck each do, from a terminal or a window, on Windows and Linux. More than
an agent harness - the harness is the engine; the estate is the job.

## What ARGUS is, in one paragraph

ARGUS started from **[Hermes Agent](https://github.com/NousResearch/hermes-agent)** (MIT, Nous Research): a
multi-provider agent harness with MCP, skills, subagents, cron, memory, a terminal UI, a desktop app and a plugin
system. **It is HavoK's app now, not a skin over Hermes** (decision of 2026-10-31, see below): the repository, every
change and every release are HavoK's, the product says ARGUS everywhere a person looks, and upstream is a source
to take fixes and features from when they are worth it - not a base ARGUS must stay mergeable with. MIRA's own
apps keep their per-device jobs; ARGUS is the one place that can do all of it.

## Decisions (HavoK, 2026-10-31)

| Question | Decision |
|---|---|
| Ownership | **HavoK's own app** (2026-10-31, replacing the first day's "soft fork"): "this is MY app now, something new, more than an agent harness - a housing unit for Mira and every device I own." The whole repo is ARGUS's to change; upstream is taken from selectively. |
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

## Owning the codebase

1. **ARGUS is the product name everywhere a person reads.** `argus/tools/rebrand.py` rewrote every user-facing
   string (messages, hints, prompts, labels, the CLI's program name) from Hermes to ARGUS, and it is re-run on
   anything taken from upstream. What a program reads keeps its name: module names (`hermes_cli`), env vars
   (`HERMES_HOME` - `$ARGUS_HOME` is passed as it), package / toolset ids, file names, Nous' Hermes *model*
   names, the "Hey Hermes" hotword (a trained model; it changes when an ARGUS hotword exists), the Docker image's
   `hermes` user. A line that must keep a Hermes string ends in `# rebrand: keep`.
2. **ARGUS is the built-in look**, not a skin applied late: the TUI's default brand, palette and art, and the
   Python skin engine's `default`, are ARGUS (`argus/skins/argus.yaml` is the one source; gold Hermes stays
   selectable as `hermes-classic`). A cold start - no boot cache, no skin pushed yet - already draws ARGUS.
3. **Change the core whenever that is the right fix.** Plugins stay the right shape for optional capability
   (the cockpit, providers, delegation backends); identity, behaviour and polish change in place.
4. **Taking from upstream** (when a fix or feature is worth it): `git fetch upstream`, merge or cherry-pick,
   then `python3 argus/tools/rebrand.py <changed paths>`, rebuild the TUI and run the tests (see
   `argus/CORE-PATCHES.md` for the conflict notes).
5. **Release and versioning are ARGUS's** (still to set up: an ARGUS version line, tags, the Desktop installer).

## Layout (`argus/`)

```
argus/
  ARGUS.md              this file
  bin/argus             launcher (Linux/macOS/WSL)    bin/argus.ps1, bin/argus.cmd  (Windows)
  install.sh / .ps1     overlay -> $ARGUS_HOME (idempotent; links skins/plugins, seeds config once)
  config/config.yaml    the seed config (MIRA's MCP via the relay, MIRA's skills dir, argus skin)
  skins/argus.yaml      the ARGUS skin
  plugins/argus-cockpit the estate from HvkDeck: estate_* tools, /estate, `argus estate` (read-only)
  plugins/              (later) model-providers/*, more cockpit tools, delegation backends
  CORE-PATCHES.md       every edit outside argus/
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
4. **Cockpit plugin pack - first slice done (2026-10-31):** `argus-cockpit` reads debhvk through hvkdeckd with the
   HvkDeck apps' own credentials (`~/.config/hvkdeck/credentials.json`; LAN first, the Cloudflare Access URL as
   fallback). Six tools in the `estate` toolset (overview, containers, logs, health, jobs, stacks), the same views
   as `/estate ...` in a session and `argus estate ...` in a shell. Read-only on purpose: changing the estate
   (restart, deploy) stays with MIRA's guarded MCP tools so approvals and the audit trail live in one place.
   Verified on laphvk: `argus estate` / `estate health` / `estate containers mira` against the live API, and a
   oneshot turn that found the tools through tool search and answered from `estate_overview` +
   `estate_containers` (the NIM rate limit mid-turn also proved the Cloudflare fallback live).
   Next: TUI panels (a live estate pane, not just slash output), phone / widgets / autonomy views, `/deploy` as
   a guarded write.

   Notes from the slice:
   - Plugin tools always sit behind the tool-search bridge (there is no per-tool "keep eager" switch); the
     listing fits in full today (162 deferred, 4k budget), so the model finds them by name.
   - **Enabling a plugin needs a fresh core server**: the gateway owner loads plugins once at start. With no
     service it idle-exits after 10 min; otherwise `argus gateway restart`.
   - Seen once: a TUI whose terminal window was closed kept running at ~90% CPU on the deleted pty
     (`python .../hermes`, parent init). Upstream bug to chase in phase 6 (should exit on SIGHUP / EIO).
5. **Desktop rebrand + builds:** ARGUS name/icon (CORE-PATCHES), Windows installer and Linux AppImage/deb.
6. **Polish to beat Claude Code / opencode:** the things HavoK uses daily, measured by HavoK.

## Licence

Hermes Agent is MIT-licensed (c) 2025 Nous Research; its LICENSE stays in the repository root unchanged.
ARGUS's additions are HavoK's.
