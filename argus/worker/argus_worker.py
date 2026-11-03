#!/usr/bin/env python3
"""ARGUS's worker: one per machine, privileged, reading one config.

ARGUS isn't an entity; it's the connector on every device HavoK owns, and this is its process. As root (a systemd system
unit on laphvk and debhvk) it keeps what runs on this machine matching ``argus.yaml``: if Mira's body is enabled it runs
her body in HavoK's desktop session, and her companion (the relay her body thinks and speaks through, her check-ins);
if not, her body stays down. On Windows the ARGUS service (``windows/ArgusService.cs``, LocalSystem) does the same with
the same file; this script only reads it there (``status``/``check``).

Standard library only, on purpose: it runs as root from a root-owned copy (``install.sh`` puts it in
/usr/local/lib/argus), never from HavoK's own checkout, so nothing HavoK's user can write runs as root; and debhvk's
system Python has no YAML library. ``argus.yaml`` is plain YAML: nested maps of scalars and lists of scalars.

    argus_worker.py run [--config PATH]      supervise (foreground; systemd runs it)
    argus_worker.py status [--config PATH]   what the config asks for, and what's running
    argus_worker.py check [--config PATH]    read the config and say what's wrong with it (exit 1 if anything)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TICK = 30

# Her units in HavoK's own systemd (user) manager. mira-pet is the QML body from before the fork: while her body is off it
# stands in, so turning her body off in argus.yaml is the whole rollback.
BODY, OLD_BODY, COMPANION = "mira-body.service", "mira-pet.service", "mira-companion.service"

DEFAULTS = {"host": "", "user": "", "body": {"enabled": False}, "companion": {"enabled": True}}
KNOWN = {"host": str, "user": str, "body": dict, "companion": dict, "devices": list, "links": dict, "quiet_hours": str}


def config_path() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "ARGUS" / "argus.yaml"
    return Path("/etc/argus/argus.yaml")


class ConfigError(ValueError):
    pass


def _scalar(text: str):
    text = text.strip()
    if text[:1] in "\"'" and text[-1:] == text[:1] and len(text) >= 2:
        return text[1:-1]
    low = text.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~", ""):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def parse(text: str) -> dict:
    """The plain-YAML subset argus.yaml uses: ``key: value``, nested maps by indentation, ``- item`` lists of scalars,
    ``#`` comments. Anything else is an error, never a guess."""
    rows: list[tuple[int, int, str]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = "" if raw.lstrip().startswith("#") else re.sub(r"\s+#.*$", "", raw).rstrip()
        if not line.strip():
            continue
        lead = line[: len(line) - len(line.lstrip())]
        if "\t" in lead:
            raise ConfigError(f"line {number}: indent with spaces, not tabs")
        rows.append((number, len(lead), line.strip()))
    at = 0

    def block(indent: int) -> dict | list:
        nonlocal at
        listed = rows[at][2].startswith("-")
        out: dict | list = [] if listed else {}
        while at < len(rows) and rows[at][1] == indent:
            number, _, body = rows[at]
            if listed != body.startswith("-"):
                raise ConfigError(f"line {number}: a list and keys mixed at one level")
            at += 1
            if listed:
                out.append(_scalar(body[1:]))
                continue
            match = re.fullmatch(r"([A-Za-z_][\w.-]*)\s*:(?:\s+(.*))?", body)
            if not match:
                raise ConfigError(f"line {number}: expected 'key: value', got {body!r}")
            key, value = match.group(1), match.group(2)
            if key in out:
                raise ConfigError(f"line {number}: {key} is set twice")
            if value is not None and value.strip():
                out[key] = _scalar(value)
            elif at < len(rows) and rows[at][1] > indent:
                out[key] = block(rows[at][1])
            else:
                out[key] = None
        if at < len(rows) and rows[at][1] > indent:
            raise ConfigError(f"line {rows[at][0]}: indentation doesn't line up")
        return out

    if not rows:
        return {}
    if rows[0][1] != 0:
        raise ConfigError(f"line {rows[0][0]}: the first setting shouldn't be indented")
    root = block(0)
    if at < len(rows) or not isinstance(root, dict):
        raise ConfigError(f"line {rows[min(at, len(rows) - 1)][0]}: indentation doesn't line up")
    return root


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"no config at {path}") from None
    found = parse(text)
    problems = [f"{key}: unknown setting" for key in found if key not in KNOWN]
    problems += [f"{key}: should be a {kind.__name__}" for key, kind in KNOWN.items()
                 if found.get(key) is not None and not isinstance(found[key], kind)]
    for part in ("body", "companion"):
        section = found.get(part)
        enabled = section.get("enabled") if isinstance(section, dict) else None
        if enabled is not None and not isinstance(enabled, bool):
            problems.append(f"{part}.enabled: should be true or false")
    if problems:
        raise ConfigError("; ".join(problems))
    merged = {**DEFAULTS, **{k: v for k, v in found.items() if v is not None}}
    for part in ("body", "companion"):
        merged[part] = {**DEFAULTS[part], **(found.get(part) or {})}
    return merged


def desired(config: dict) -> dict[str, bool]:
    """Which of her user units should be running for this config."""
    body = bool(config["body"]["enabled"])
    return {COMPANION: bool(config["companion"]["enabled"]), BODY: body, OLD_BODY: not body}


def systemctl(user: str, *args: str, run=subprocess.run) -> subprocess.CompletedProcess:
    """HavoK's own (user) systemd manager: as root through ``-M user@`` (it lingers, so it's there), else directly."""
    head = ["systemctl", "--user"] + (["-M", f"{user}@"] if os.geteuid() == 0 else [])
    return run(head + list(args), capture_output=True, text=True, timeout=60, check=False)


def state(user: str, unit: str, run=subprocess.run) -> str:
    """active, inactive, failed, ...; "missing" for a unit this machine doesn't have (debhvk has no bodies)."""
    loaded = (systemctl(user, "show", "-p", "LoadState", "--value", unit, run=run).stdout or "").strip()
    if loaded == "not-found":
        return "missing"
    return (systemctl(user, "is-active", unit, run=run).stdout or "").strip() or "unknown"


def apply(config: dict, run=subprocess.run, say=print) -> list[str]:
    """One pass: start what should run and stop what shouldn't. Returns what it changed."""
    user = config["user"]
    changed = []
    for unit, want in desired(config).items():
        now = state(user, unit, run)
        if now in ("unknown", "missing") or (now == "inactive" and not want) or (now == "active" and want):
            continue
        if want and now != "activating":
            done = systemctl(user, "start", unit, run=run)
            changed.append(f"started {unit}" if done.returncode == 0 else f"couldn't start {unit}: {done.stderr.strip()[:200]}")
        elif not want and now in ("active", "activating", "failed"):
            done = systemctl(user, "stop", unit, run=run)
            changed.append(f"stopped {unit}" if done.returncode == 0 else f"couldn't stop {unit}: {done.stderr.strip()[:200]}")
    for line in changed:
        say(f"argus worker: {line}")
    return changed


def run(path: Path | None, tick: float = TICK) -> int:
    if sys.platform == "win32":
        print("argus worker: on Windows the ARGUS service supervises (windows/ArgusService.cs); use status or check here")
        return 2
    seen, told = None, set()
    while True:
        try:
            config = load(path)
            if config != seen:
                print(f"argus worker: {config['host'] or 'this machine'}: body {'on' if config['body']['enabled'] else 'off'}, "
                      f"companion {'on' if config['companion']['enabled'] else 'off'} (for {config['user']})", flush=True)
                seen = config
            if config["user"]:
                # A unit that won't start is said once, not every tick, until something changes.
                changed = set(apply(config, say=lambda line: None))
                for line in sorted(changed - told):
                    print(f"argus worker: {line}", flush=True)
                told = changed
        except ConfigError as exc:
            print(f"argus worker: config: {exc}; changing nothing until it's fixed", flush=True)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"argus worker: {exc}", flush=True)
        time.sleep(tick)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="argus_worker.py", description="ARGUS's worker on this machine")
    parser.add_argument("action", choices=("run", "status", "check"))
    parser.add_argument("--config", type=Path, default=None, help=f"default {config_path()}")
    args = parser.parse_args(argv)
    if args.action == "run":
        return run(args.config)
    try:
        config = load(args.config)
    except ConfigError as exc:
        print(f"config: {exc}")
        return 1
    if args.action == "check":
        print(f"config ok: {args.config or config_path()}")
        if not config["user"]:
            print("user: not set, so the worker changes nothing")
            return 1
        return 0
    report = {"config": str(args.config or config_path()), "asks": desired(config)}
    if sys.platform != "win32" and config["user"]:
        report["running"] = {unit: state(config["user"], unit) for unit in desired(config)}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
