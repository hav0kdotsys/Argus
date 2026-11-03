# ARGUS worker

ARGUS on each machine, running privileged: it reads one config and houses MIRA there. If her body is enabled, it runs
her body (the `mira-body` fork) in HavoK's desktop session, and her companion: the relay her body thinks, speaks and
sees through, and her check-ins. Plan: `argus/PLAN-mira-body.md`, P3.

| machine | runs as | config | what it keeps running |
|---|---|---|---|
| laphvk | root, `/etc/systemd/system/argus.service` | `/etc/argus/argus.yaml` | HavoK's user units `mira-body`, `mira-companion` (and `mira-pet`, the QML body, only while her body is off) |
| winhvk | LocalSystem, service `ARGUS` | `%ProgramData%\ARGUS\argus.yaml` | `Mira.exe` and her companion in HavoK's session, as HavoK (and the `MIRA-Pet` task only while her body is off) |
| debhvk | root, `/etc/systemd/system/argus.service` | `/etc/argus/argus.yaml` | nothing yet: headless, body and companion off |

Her body and companion always run as HavoK, never as root or SYSTEM: a desktop app has to run in its user's session, and
nothing they do gets the worker's rights. The worker's own copy is root-owned (`/usr/local/lib/argus`,
`%ProgramFiles%\ARGUS`), and only admins can change `argus.yaml`, so nothing HavoK's user can write runs privileged.

## Config

```yaml
host: laphvk
user: havok
body:
  enabled: true      # false: her body stops and the old one comes back (that's the whole rollback)
companion:
  enabled: true
```

Windows adds `body.path` and `companion.command`. The worker rereads it every 30 s. It's plain YAML: nested maps of
scalars, `- item` lists; anything else is an error, and while it's wrong the worker changes nothing.
`argus_worker.py check --config FILE` (or `ArgusService.exe --check FILE`) reads one the way the worker will.

## Install (HavoK, once per machine)

- **laphvk:** `argus/worker/linux/deploy-body.sh` (as HavoK: her body's build into `~/.local/share/mira-body` and its
  user unit), then `sudo argus/worker/linux/install.sh laphvk`.
- **debhvk:** `sudo argus/worker/linux/install.sh debhvk`.
- **winhvk:** from an admin PowerShell, `argus\worker\windows\install.ps1`.

Rollback: `body.enabled: false`, or `sudo systemctl disable --now argus` / `windows\uninstall.ps1`, which puts MiraPet
and the MIRA Companion startup shortcut back as they were.

## Updating her body

- laphvk: `argus/worker/linux/deploy-body.sh`
- winhvk: `argus\worker\windows\deploy-body.ps1` (no admin; the service starts it again)
