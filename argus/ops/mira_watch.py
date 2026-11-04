#!/usr/bin/env python3
"""MIRA's watcher on debhvk: tells Hannah once when something of MIRA's breaks, and once when it's back.

Written 4 Nov 2026, after ElevenLabs refused every request for 15 hours (a failed payment) and nobody knew: her voice
had quietly become Edge's. Runs every 2 minutes (``mira-watch.timer``, a systemd --user unit). A check has to fail on
two runs in a row before it alerts, so a restart or a blip stays quiet; the all-clear goes out once it passes again.

What it watches: her ElevenLabs voice (main account, and the backup that speaks as Lily), Claude's login and usage
limit, her providers' health, the Claude sidecar, and her containers. Her bodies and companions are watched on their
own machines by her companion (``argus-companion``), since this box can't reach the PCs.

Alerts are a Discord DM through mira-api's /notify, with the token the Claude sidecar already holds (read from its
.env at runtime, never copied or logged). State: ``~/.local/state/mira-watch.json``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SIDECAR_ENV = Path("/srv/authentik-prod/production/mira/mira-claude/.env")
SIDECAR_HEALTH = "http://172.17.0.1:8095/health"
CONTAINERS = ("mira-api", "mira-mcp", "mira-supervisor", "mira-db", "mira-web", "bark-tts")
OPERATOR = "1162645612907483226"
FAILS_TO_ALERT = 2


def state_path() -> Path:
    return Path.home() / ".local" / "state" / "mira-watch.json"


def env() -> dict:
    values = {}
    try:
        for row in SIDECAR_ENV.read_text(encoding="utf-8").splitlines():
            key, sep, value = row.strip().partition("=")
            if sep and key in ("MIRA_WEB_INTERNAL_TOKEN", "MIRA_API_URL", "MIRA_OPERATOR_DISCORD_ID"):
                values[key] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def _get(url: str, token: str = "", timeout: float = 30) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as reply:
        return json.loads(reply.read().decode("utf-8"))


def _run(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30,
                              check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


# Each check: (name, ok or None for "nothing to judge this run", what's wrong)

def voice(since: str) -> list[tuple[str, bool | None, str]]:
    """Her ElevenLabs accounts, from what bark-tts did since the last run."""
    log = _run(["docker", "logs", "--since", since, "bark-tts"])
    lines = [l for l in log.splitlines() if l.startswith(("tts ", "ElevenLabs"))]
    out = []
    for engine, name, words in (("el", "voice-main", "Her ElevenLabs voice (main account)"),
                                ("el-backup", "voice-backup", "Her backup ElevenLabs voice (Lily)")):
        good = any(l.startswith(f"tts {engine}:") for l in lines)
        bad = [l for l in lines if l.startswith(f"ElevenLabs ({engine})")]
        if good:
            out.append((name, True, ""))
        elif bad:
            why = bad[-1].split(":", 1)[-1].strip()
            for marker in ("payment_issue", "quota_exceeded", "concurrent_limit_exceeded", "unauthorized", "detected_unusual_activity"):
                if marker in why:
                    why = marker.replace("_", " ")
                    break
            out.append((name, False, f"{words} is refusing requests ({why[:120]})."))
        else:
            out.append((name, None, ""))
    return out


def claude(token: str, base: str) -> list[tuple[str, bool | None, str]]:
    out = []
    try:
        side = _get(SIDECAR_HEALTH, timeout=10)
        out.append(("claude-login", bool(side.get("auth_ok", True)),
                    f"Claude's login on debhvk is failing: {str(side.get('auth_error') or '')[:150]}"))
    except (OSError, ValueError):
        out.append(("claude-sidecar", False, "The Claude sidecar on debhvk isn't answering."))
        return out
    out.append(("claude-sidecar", True, ""))
    try:
        health = _get(f"{base}/v1/mira/providers/health", token)
    except (OSError, ValueError):
        return out
    limit = health.get("claudeLimit")
    out.append(("claude-limit", not limit, f"Claude has hit its usage limit; her turns go to "
                                            f"{health.get('claudeFallbackNow') or 'a fallback'} until it resets ({limit})."))
    for name, info in (health.get("providers") or {}).items():
        if name == "groqcloud-router":
            continue
        down = bool(info.get("down")) or info.get("ok") is False
        out.append((f"provider-{name}", not down, f"Her provider {name} is down: {str(info.get('error') or '')[:150]}"))
    return out


def containers() -> list[tuple[str, bool | None, str]]:
    out = []
    for name in CONTAINERS:
        state = _run(["docker", "inspect", name, "--format",
                      "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}"]).split()
        ok = bool(state) and state[0] == "running" and (len(state) < 2 or state[1] != "unhealthy")
        out.append((f"container-{name}", ok, f"Her container {name} is {' '.join(state) or 'missing'}."))
    return out


def notify(token: str, base: str, target: str, message: str, high: bool) -> bool:
    body = {"target": target, "messages": [message], "priority": "high" if high else "normal", "channels": ["discord"],
            "source": "mira-watch", "origin": "autonomous"}
    request = urllib.request.Request(f"{base}/v1/mira/notify", data=json.dumps(body).encode("utf-8"),
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as reply:
            return reply.status == 200
    except OSError:
        return False


def judge(state: dict, results: list[tuple[str, bool | None, str]], now: float) -> list[tuple[str, str, bool]]:
    """Update the per-check state; the messages to send: (check, text, is_an_alert)."""
    messages = []
    for name, ok, why in results:
        if ok is None:
            continue
        entry = state.setdefault(name, {"fails": 0, "alerted": False})
        if ok:
            if entry.get("alerted"):
                since = time.strftime("%H:%M", time.localtime(entry.get("since") or now))
                messages.append((name, f"✅ MIRA: fixed - {entry.get('why', name)} (broken since {since}).", False))
            state[name] = {"fails": 0, "alerted": False}
            continue
        entry["fails"] = entry.get("fails", 0) + 1
        entry.setdefault("since", now)
        entry["why"] = why
        if entry["fails"] >= FAILS_TO_ALERT and not entry.get("alerted"):
            entry["alerted"] = True
            messages.append((name, f"⚠️ MIRA: {why}", True))
    return messages


def main(argv: list[str] | None = None) -> int:
    """``--dry-run``: check and print, send nothing, keep no state."""
    dry = "--dry-run" in (argv if argv is not None else sys.argv[1:])
    now = time.time()
    try:
        state = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    last = float(state.get("_ran") or (now - 600))
    since = f"{max(60, int(now - last) + 30)}s"
    values = env()
    token, base = values.get("MIRA_WEB_INTERNAL_TOKEN", ""), values.get("MIRA_API_URL", "http://127.0.0.1:5000").rstrip("/")
    target = values.get("MIRA_OPERATOR_DISCORD_ID") or OPERATOR
    results = voice(since) + claude(token, base) + containers()
    checks = {k: v for k, v in state.items() if not k.startswith("_")}
    messages = judge(checks, results, now)
    if dry:
        for name, ok, why in results:
            print(f"{name}: {'ok' if ok else 'n/a' if ok is None else 'FAILING - ' + why}")
        return 0
    for name, text, alert in messages:
        print(text, flush=True)
        if not (token and notify(token, base, target, text, alert)) and alert:
            checks[name]["alerted"] = False          # mira-api itself down, say: the alert goes out on a later run
    state_path().parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path().with_suffix(".tmp")
    tmp.write_text(json.dumps({**checks, "_ran": now}), encoding="utf-8")
    tmp.replace(state_path())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
