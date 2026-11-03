# ARGUS houses MIRA: plan

Status: **AGREED** with HavoK, 2026-11-03. Implementation starts at P0.

## The shape

- **MIRA** is the entity: a fast collection of brains (mira-api on debhvk and its router). Her infrastructure is
  hers: Mira Desktop (cockpit), the Voice Interface (mira-agent + voice-services), Mira Mobile, the Discord
  bridge, and her **body** on each PC.
- **ARGUS** isn't an entity. It's the connector on every device HavoK owns: it sees everything and links all of
  it to Mira. One **worker** per machine, running privileged (Windows Service as LocalSystem on winhvk; a
  systemd *system* unit as root on laphvk and debhvk). It reads one config. If `body.enabled`, it runs her body.

## Why the body becomes a Capri fork, not a re-port

Capri 0.8.0 (upstream 873e931, 2026-11-03) is about 103k lines of C#. `app/` is the Windows app (Capri.cs alone is
30k lines) and `cross/` is an Avalonia port for Mac/Linux. It has 44 sprite sheets, the mouth overlay, perches,
ledges, neon, bolts, ink, clones, chaos screen, hologram, the game HUD, and dozens of effects. Our MiraPet plus
the QML body re-derived maybe a tenth of that. Re-porting the rest by hand would take months and would always
lag behind upstream. Forking it keeps every animation and effect exactly as she plays them. We then swap three
things: her **mind** (Mira's backend), her **colours** (red → Mira purple), and her **name**. PolyForm
Noncommercial permits this for HavoK's noncommercial use, as long as the license and the `Required Notice:` lines
travel with every copy.

- New repo **`mira-body`**, private, a fork of `lachydotmcg/capri-desktop` with `upstream` kept as a remote. Upstream
  fixes come in by merge or cherry-pick. It carries LICENSE.md, Capri's Required Notices, and a NOTICE saying what
  changed.
- It stays out of the MIT ARGUS repo: ARGUS only holds the worker, the config and the connector (our own code).
- The art is still Capri's (CDPR fan art) until HavoK swaps in her own. The recolour is a build step, so new
  artwork just drops in.

## Phases

### P0: Prove it runs (no changes)
1. Build stock Capri 0.8.0 on winhvk with its own `ci/build-windows.ps1` (csc 4.8 + Windows SDK winmd: both
   present). Run its `--smoke-test`.
2. laphvk: install the .NET 10 SDK, build `cross/`, run it on Hyprland (Avalonia goes through XWayland). Check
   transparency, click-through, staying on top, and the floor/window perches with Hyprland window rules.
   **Gate:** if Cross can't be made solid on Hyprland, laphvk keeps the QML body, driven by the fork's exact clip
   tables (frames, timings, offsets, transitions read straight from Pet.cs/Capri.cs). It then plays the
   same animations, but with only the features Cross also lacks.
3. **The inventory**: a generated table of every sprite sheet, clip, overlay and effect (Neon, Bolts, Ink,
   Clones, Chaos, Hologram, Smoke, Ledges, Perches, GameHud…). For each: what triggers it in Capri, and what
   triggers it for Mira (the mapping in P5). It's committed as `docs/ANIMATIONS.md` in mira-body.

### P1: Fork, rename, recolour, cut her ties to Capri's services
- Rename user-facing **Capri → Mira**: window titles, menus, tray, the data folder `%LOCALAPPDATA%\Mira` /
  `~/.local/share/mira`, and the exe `Mira.exe`. Credits and notices keep Capri's name.
- **Recolour, code side:** every Capri-red palette constant (Neon: Rose, Hot, Lit, Edge, Glow, Brim, Dash, Pressed;
  `255,0,70`, `232,66,70` and the rest, plus the ones generated in P0) is hue-mapped to Mira purple. Lightness and
  alpha are kept, so the glows and dark tints stay right. Cyan stays: it's the secondary colour, not the primary.
- **Recolour, art side:** `tools/recolour.py` runs at build time. It picks out pixels in Capri's red hue band
  (masked by hue/saturation, so skin, black and cyan stay as they are), rotates them to Mira's hue keeping
  lightness, and writes `assets/sprites/*.png`. The originals stay in `assets/capri/` for re-runs. It's
  deterministic, with a before/after contact sheet for review.
- **Cut every outbound tie to Capri's services:** the update check against Capri's GitHub releases, the Ko-fi
  lines and links, the `capri-reactions` Cloudflare worker/D1, presence art, and the VB-Cable bundle unless it's
  wanted. Her smoke test's checks for those are adjusted to match.

### P2: Her mind is Mira's (HavoK, 2 Nov)
Capri's `Brain` builds a prompt (Capri's personality, safety lines, machinery/tool rules) and calls providers
directly with keys. In the fork, all of that goes:
- **Capri's provider list is replaced** by Mira's providers as configured and authenticated on debhvk:
  claude-code (sidecar), opencode, groqcloud, googleai and the rest of her router. The body holds no keys and no
  provider choice of its own. mira-api routes as it does today: a session's lock picks the provider, otherwise
  her complexity router does.
- **Her body is in her main session.** It calls mira-api's `/v1/mira/call/stream` (SSE: `turn.started`,
  `turn.update`, `turn.final`, `turn.error`) as `X-Jarvis-Client: desktop`, with no `userId` modifier. That
  resolves to the same `agent:desktop` scope as Mira Desktop and the Voice Interface, so what HavoK says to her
  body, at her desk or by voice, is one conversation with one memory. The bearer is read on the device at
  runtime (as `backend.py` does now).
- **Her hands go through her MCP.** Tools run through the claude-code sidecar's MCP loop on debhvk, the same way
  every other Mira turn uses tools. The body's own abilities become MCP tools in `mcp-server` (a new
  `mira-body.js`, like `winhvk.js` / `laphvk-desk.js`). For example: `body_do` (animate, move, hop to a screen,
  size), `body_draw` (ink on the screen), `body_arrange` (windows), `body_clip`, `body_chaos`, `body_hologram`,
  `body_board`. Each reaches that device's ARGUS worker and returns its result. Capri features Mira already
  has tools for (reminders, files, computer input, screenshots, music) use **Mira's existing tools**, and Capri's
  duplicates are cut. Capri's local tool loop (Hands/Computer as a brain loop) is removed; the code that does
  the work stays as what those MCP tools call.
- **Mira-api/MCP changes** (the new MCP module, plus any session-linking change) are HavoK's guarded deploys.
  Every file touched on debhvk is backed up first.
- **Capri's persona is gone:** `DefaultPersonality`, the persona examples, `personality.md`, the Agent/voice
  persona lines and the Ko-fi lines. Mira's persona is mira-api's own.
- **Words in her mouth:** every line Capri says from code (greetings, fallbacks, canned quips, `hello-*.wav`,
  the scripted lines on the setup screen) is audited. Each one becomes a moment Mira answers in her own words, or
  is deleted. The audit script is part of P0's inventory.
- **Voice:** spoken replies go through Mira's own voice (mira-api `/v1/tts/stream` / the Voice Interface), never
  Capri's TTS setup or her recorded wavs. Her mouth animation follows the audio levels. Nothing is audible while
  HavoK sleeps.

### P3: The ARGUS worker as a privileged service
- New `argus worker` (it lives in ARGUS: plugin/CLI first, per the footprint ladder). It does what
  `mira-companion` does now, plus supervision: config, the link to other devices, health, starting and stopping the
  body, the Mira relay endpoint, and privileged jobs.
- **Config:** `%ProgramData%\ARGUS\argus.yaml` / `/etc/argus/argus.yaml` (behaviour). Secrets go in a root-/SYSTEM-
  only `.env` beside it, copied file to file, never echoed. Keys: `body.enabled`, `body.size`, `devices`, `links`,
  `quiet_hours`.
- **winhvk:** a small C# Windows Service `ARGUS` (LocalSystem, auto-start, restart on failure) hosts the Python
  worker. Services live in Session 0 and **can't draw on the desktop**, so the service starts Mira's body in
  HavoK's interactive session (WTSQueryUserToken + CreateProcessAsUser). It restarts the body on logon,
  unlock and session change. The body runs as HavoK, so it can see and touch her desktop; privileged work goes
  back through the worker. This replaces the current scheduled tasks.
- **laphvk:** `/etc/systemd/system/argus.service` (root). On Wayland a root process can't draw in HavoK's session,
  so the worker starts the body as a user unit in her session (`systemctl --user -M havok@ start mira-body`), and
  it lingers. It replaces `mira-companion` + `mira-pet`. **HavoK's live ARGUS TUI is never touched.**
- **debhvk:** the same system unit with `body.enabled: false` (headless). Every file touched there is backed up
  first.
- **Running privileged** means Mira's commands through the worker run as root/SYSTEM on that machine. That's
  HavoK's call (made: "must have admin/root perms"). The body and anything on the desktop still run as HavoK,
  because the OS requires it.

### P4: ARGUS sees all: the connector
- `link.py` grows from a laphvk↔winhvk pair into a mesh over every device in `argus.yaml` (laphvk, winhvk,
  debhvk, later mobilehvk). Each worker reports its device's state (online, music, quiet, focus/game, battery,
  services up) and hears the others. The current synced switches (quiet, coach, settings) and dancing on both
  bodies carry over.
- Mira's infrastructure as linked services, with health checks and how to reach each: mira-api, the MCP server,
  Mira Desktop (cockpit), the Voice Interface (mira-agent, remote-mic), Mira Mobile, the Discord bridge, and
  each body. They show on her cockpit's device board (mira-api `devices.js` already knows the hosts).
- What each body can do is offered to Mira as **device capabilities**, so her turns from anywhere (voice,
  Discord, desktop) can move her body ("dance on winhvk", "come to this screen").

### P5: Every animation mapped to Mira
From the P0 inventory: each clip/effect is bound to the Mira or ARGUS event that drives it. For example:
- glitch-in/arrive/leave → a body or device coming online or going offline
- talk/mouth → Mira speaking (her voice stream's levels drive the mouth)
- dance/perch-music → music on any linked device
- sleep/wake → quiet hours, and HavoK's own sleep/wake
- ink/drawing → Mira pointing at what she sees (`vision_look`)
- chaos/clones/hologram → Mira's own call, as tools she can use

The table goes in `docs/ANIMATIONS.md`; every row is tested or observed on screen.

### P6: Cut over and retire
For each machine: stop the old units/tasks, start the ARGUS service, and verify every row of the table. Then
`argus/pet/windows/MiraPet` and `argus/pet/mira-pet` are retired (removed in a commit, so they stay in history).
The rollback is the previous units and tasks, kept disabled, not deleted.

## Verification at each step
- the fork's own smoke test
- ARGUS tests (`tests/argus_plugins`) and `scripts/check`
- screen captures of each animation on both PCs
- the service surviving a reboot and a logoff/logon
- no outbound call to any Capri service (checked with a connection log)

## Decisions (filled in as HavoK answers)
- Mira purple: **#C77DFF** (her orchid). Cyan stays secondary.
- Brain: **Mira's debhvk providers replace Capri's**; her body joins her main Desktop/Voice session; tools go through MCP via the claude-code sidecar (see P2).
- laphvk body: **try Capri.Cross first**, fall back to QML driven by the fork's clip tables (P0 gate).
- mira-body repo: **private** `hav0kdotsys/mira-body`, with Capri as `upstream`.
- Ambient reactions (game commentary, live reactions, watch-along asides, desktop moments): a **linked side session `agent:body`**, with a short digest carried into the main session. Anything HavoK says to her body goes to the main session.

## Log

### P0 (2026-11-03): done
- Fork: `~/mira-body` on laphvk and `D:\Network\Projects\Argus\mira-body` on winhvk (winhvk has no GitHub login,
  so updates go over as a git bundle). GitHub Actions are off on the private repo.
- winhvk: stock 0.8.0 builds with `ci/build-windows.ps1` (VB-CABLE's pack made optional: it isn't in git). Its own
  smoke test over SSH (no desktop): **185 PASS, 4 FAIL**, then it timed out. All 4 fails need a real desktop:
  drag/throw physics and a 144-dpi layout. This is the baseline every later build is compared against.
- laphvk: the .NET 10 SDK is in `~/.dotnet` (user-local, no root). `cross/` builds and runs under XWayland on
  Hyprland 0.56 (Lua config). **Gate: passed, with fixes for P1:**
  - Your global window opacity and blur make a dark box behind her. Her windows need `opaque`, `no_blur`,
    `no_shadow`, `no_dim`, `no_anim`, `border_size 0` and `rounding 0`. The fork sets these itself when it tames
    each window, through the IPC socket it already uses.
  - It already has `HyprDesk`: Hyprland IPC for windows/monitors/cursor, perching on real windows, and Lua-first
    dispatch.
  - With no bottom bar, she sits on the screen's bottom edge and her legs hang off it; on Windows the taskbar
    catches them. The fork lifts the floor by her leg length when the work area reaches the screen bottom.
  - Missing in the port: the whole **lie-down family** (7 clips with facing-left sheets) and `perch_talk`. These
    get ported from the Windows app in P1/P5.
- Inventory: `docs/ANIMATIONS.md`, generated by `tools/inventory.py`. It lists 27 clips (Windows) / 20 (port),
  44 sheets, 32 windows (16 Overlay effects: Chaos, ChessBoard, ClipToast, Clone, GameHud, Ink, MiniBoard,
  MiniPlayer, ReactionFeed, TalkPill, Tear, Shatter, Takeover, HerPointer, TaskPanel, SpeechBox), the
  paint/effect routines, and **112 lines her code says by itself**, for the P2 audit.

### P1 (2026-11-03): core done
- **Recolour** (`tools/recolour.py`): Capri's primary (#FA033F, 85% of her coloured pixels) maps exactly onto #C77DFF,
  and every other red keeps its offset from it. Her greens, the cyan and the blue glitch splits stay. The art goes to
  `assets/mira/` (originals untouched; both builds embed it). 51 colour literals in code were moved, using a hard band
  so a re-run changes nothing; an orange test fixture (hue 14°) is left alone.
- **Rename** (`tools/rename.py`): string literals only (regular and verbatim), about 1,050 of them: window titles,
  menus, bubbles, the data folder `%LOCALAPPDATA%\Mira` / `~/.config/Mira`, mutexes `Local\Mira.*`, the uninstall key,
  and `Mira.exe`. Kept: resource names, credit to Capri, and every web address (a renamed domain is someone else's
  site).
- **No calls home:** the update check never asks Capri's releases. The links you'd click yourself (Help, Capri's
  Discord, Support/Ko-fi) stay as credit.
- **Linux:** her windows set their own Hyprland rules (Lua `hl.window_rule`, or the hyprlang keyword), and with no
  bottom panel the floor rises by her legs.
- winhvk smoke after P1/P2: **185 PASS / 4 FAIL**, identical to stock.
- Still open in P1: port the lie-down family and `perch_talk` to the Linux port (P5 with the rest).

### P2 (2026-11-03): the link works end to end
- Body: `app/MiraLink.cs` (both builds). Ask, call mode and asides go through ARGUS's relay to mira-api. What HavoK
  says goes to the main conversation (`agent:desktop`); the body's own moments go to `agent:body`. Cues in her reply
  still move the body. During a smoke test, or without ARGUS, the link is off.
- Her hands: `MiraHands`, 127.0.0.1:8774 with ARGUS's token. `GET /kit` returns her tools in MCP's shape; `POST /do`
  runs one through the body's own tool runner, so Security's toggles hold. Verified on laphvk: 15 tools, she danced
  and stopped on command.
- ARGUS: `relay.py`, 127.0.0.1:8773, started by the companion on both PCs. It writes `argus.json` (port, fresh token,
  0600) into her body's folder. `argus companion hands kit|do <b64>` lets her MCP reach the body.
- Verified live: relay → mira-api → **claude-code answered in 4.7 s** through `agent:body`. winhvk's relay is up, and
  the MCP's exact SSH command answers there.
- **Staged on debhvk, for HavoK's guarded deploy:** `mcp-server/mira-body.js` (`mira_body_kit`, `mira_body`) and its
  registration in `mcp-server/server.js` (backup `server.js.bak-mirabody-20261103-004209`). `node --check` is clean
  and the handlers were exercised with a fake SSH. The container still needs rebuilding (HavoK).
- Still open in P2:
  - the 112-line "words in her mouth" audit (her start-up greeting "Isn't it late, choom?" is one of them)
  - her voice through Mira's TTS
  - her settings' brain picker showing Mira's debhvk providers
  - glances (See) through Mira's vision
  - a call held by a Security toggle getting HavoK's yes through Mira
  - the digest from `agent:body` into the main session
