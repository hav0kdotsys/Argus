"""argus-cockpit - the MIRA estate from inside ARGUS.

First slice of the cockpit (see argus/ARGUS.md, phase 4): HvkDeck's view of debhvk, three ways -
  - tools the agent calls (toolset ``estate``): overview, containers, logs, health, jobs, stacks;
  - ``/estate [overview|containers [filter]|health|jobs|stacks|logs <name>]`` inside a session;
  - ``argus estate ...`` from a shell, same sub-commands.

READ-ONLY by design: every call is a GET to hvkdeckd. Changing the estate (restart a container, run a deploy) stays
with MIRA's own guarded tools (docker_restart, mira_deploy) which ARGUS reaches over the mira MCP server, so the
approvals and the audit trail live in one place.
"""

from __future__ import annotations

import json
import time
from urllib.parse import quote
from typing import Any, Callable

from . import hvkdeck

_MAX_TEXT = 16000  # characters of log text handed back to the model


# ---------------------------------------------------------------------------------------------------- shaping

def _gb(n: Any) -> float:
    try:
        return round(float(n) / 1e9, 1)
    except (TypeError, ValueError):
        return 0.0


def _tail(text: str, limit: int = _MAX_TEXT) -> tuple[str, bool]:
    text = text or ""
    if len(text) <= limit:
        return text, False
    cut = text[-limit:]
    nl = cut.find("\n")
    return (cut[nl + 1:] if 0 <= nl < 200 else cut), True


def overview() -> dict[str, Any]:
    o = hvkdeck.get("overview")
    mem = o.get("mem") or {}
    temps = o.get("temps") or []
    hot = max(temps, key=lambda t: t.get("c", 0)) if temps else None
    checks = o.get("health") or []
    return {
        "host": o.get("host"),
        "uptime_hours": round(float(o.get("uptime") or 0) / 3600, 1),
        "cpu_pct": round(float(o.get("cpu") or 0) * 100, 1),
        "load": [round(x, 2) for x in (o.get("load") or [])],
        "mem": {"used_gb": _gb(mem.get("used")), "total_gb": _gb(mem.get("total")), "available_gb": _gb(mem.get("available")),
                "swap_used_gb": _gb(mem.get("swap_used")), "swap_total_gb": _gb(mem.get("swap_total"))},
        "net_mbps": {"rx": round(float(o.get("rx") or 0) * 8 / 1e6, 2), "tx": round(float(o.get("tx") or 0) * 8 / 1e6, 2)},
        "hottest_sensor": {"chip": hot.get("chip"), "label": hot.get("label"), "c": hot.get("c")} if hot else None,
        "disks": [{"mount": d.get("mount"), "used_pct": d.get("pct"), "free_gb": _gb(d.get("avail")), "size_gb": _gb(d.get("size"))}
                  for d in (o.get("disks") or [])],
        "containers": o.get("containers") or {},
        "failed_units": o.get("failed_units") or [],
        "health_failing": [{"name": c.get("name"), "code": c.get("code"), "error": c.get("error")} for c in checks if not c.get("ok")],
        "health_ok": sum(1 for c in checks if c.get("ok")),
        "jobs_running": o.get("jobs_running", 0),
        "hvkdeckd_version": o.get("version"),
    }


def containers(filter: str = "", state: str = "all") -> dict[str, Any]:
    cs = hvkdeck.get("containers").get("containers") or []
    f = (filter or "").lower().strip()
    out = []
    for c in cs:
        hay = " ".join(str(c.get(k, "")) for k in ("name", "image", "project", "service")).lower()
        if f and f not in hay:
            continue
        running = c.get("state") == "running"
        if state == "running" and not running or state == "stopped" and running:
            continue
        if state == "unhealthy" and c.get("health") != "unhealthy":
            continue
        out.append({k: c.get(k) for k in ("name", "state", "health", "status", "image", "project", "cpu", "mem", "ports") if c.get(k)})
    return {"count": len(out), "of": len(cs), "containers": out}


def logs(name: str, source: str = "container", lines: int = 200, since: str = "", grep: str = "", user: bool = False) -> dict[str, Any]:
    lines = max(1, min(int(lines or 200), 2000))
    source = (source or "container").lower()
    if source == "container":
        if not name:
            raise hvkdeck.DeckError("name the container")
        r = hvkdeck.get(f"containers/{quote(name, safe='')}/logs", {"tail": lines, "since": since})
    elif source == "unit":
        if not name:
            raise hvkdeck.DeckError("name the systemd unit")
        r = hvkdeck.get(f"units/{'user' if user else 'system'}/{quote(name, safe='')}/logs", {"lines": lines})
    elif source == "journal":
        r = hvkdeck.get("journal", {"lines": lines, "unit": name, "grep": grep, "user": "1" if user else ""})
    else:
        raise hvkdeck.DeckError("source must be container, unit or journal")
    if r.get("error") and not r.get("text"):
        raise hvkdeck.DeckError(r["error"])
    text, cut = _tail(r.get("text", ""))
    return {"source": source, "name": name, "lines": text.count("\n"), "truncated": cut, "text": text}


def health() -> dict[str, Any]:
    checks = hvkdeck.get("health").get("checks") or []
    o = hvkdeck.get("overview")
    try:
        up = hvkdeck.get("updates")
    except hvkdeck.DeckError:
        up = {}
    return {
        "checks": [{"name": c.get("name"), "ok": c.get("ok"), "code": c.get("code"), "ms": c.get("ms"), "error": c.get("error") or None}
                   for c in checks],
        "failed_units": o.get("failed_units") or [],
        "unhealthy_containers": (o.get("containers") or {}).get("unhealthy") or [],
        "stopped_containers": (o.get("containers") or {}).get("stopped") or [],
        "apt_upgradable": up.get("count"),
    }


def jobs(job_id: str = "") -> dict[str, Any]:
    if job_id:
        r = hvkdeck.get(f"jobs/{quote(job_id, safe='')}")
        text, cut = _tail(r.get("text", ""))
        return {"job": r.get("job"), "truncated": cut, "text": text}
    js = hvkdeck.get("jobs").get("jobs") or []
    now = time.time()
    return {"jobs": [{"id": j.get("id"), "title": j.get("title"), "kind": j.get("kind"), "running": j.get("running"), "rc": j.get("rc"),
                      "started_ago_min": round((now - float(j.get("started") or now)) / 60)} for j in js[:30]]}


def stacks() -> dict[str, Any]:
    s = hvkdeck.get("stacks")
    try:
        d = hvkdeck.get("deploys")
    except hvkdeck.DeckError:
        d = {}
    return {"scopes": s.get("scopes") or [], "services": s.get("services") or [],
            "recent_deploys": (d.get("deploys") or [])[-10:], "deploy_targets": d.get("targets") or []}


# ---------------------------------------------------------------------------------------------------- tools

def _tool(fn: Callable[..., dict[str, Any]], *keys: str) -> Callable[..., str]:
    """Wrap a reader as a Hermes tool handler: JSON out, never raises."""
    def handler(args: dict, **_: Any) -> str:
        try:
            kw = {k: args[k] for k in keys if k in args and args[k] is not None}
            return json.dumps(fn(**kw), ensure_ascii=False)
        except hvkdeck.DeckError as e:
            return json.dumps({"error": str(e)})
        except Exception as e:  # a tool must never take the turn down
            return json.dumps({"error": f"{type(e).__name__}: {e}"})
    return handler


def _schema(name: str, description: str, props: dict | None = None, required: list | None = None) -> dict:
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}


TOOLS = [
    ("estate_overview", overview, (), _schema(
        "estate_overview",
        "debhvk at a glance from HvkDeck: CPU, load, memory, disks, temperatures, container counts (with any unhealthy or "
        "stopped by name), failed systemd units, failing health checks, running jobs. Start here for 'how is the server'.")),
    ("estate_containers", containers, ("filter", "state"), _schema(
        "estate_containers",
        "List debhvk's Docker containers with state, health, image, compose project, CPU and memory. Filter by a substring "
        "of name/image/project and by state.",
        {"filter": {"type": "string", "description": "Substring of name, image or compose project, e.g. 'mira'."},
         "state": {"type": "string", "enum": ["all", "running", "stopped", "unhealthy"], "default": "all"}})),
    ("estate_logs", logs, ("name", "source", "lines", "since", "grep", "user"), _schema(
        "estate_logs",
        "Read recent logs on debhvk: a container's (source=container), a systemd unit's (source=unit) or the journal "
        "(source=journal, optionally one unit and a grep). Newest last; long output keeps the tail.",
        {"name": {"type": "string", "description": "Container or unit name (optional for journal)."},
         "source": {"type": "string", "enum": ["container", "unit", "journal"], "default": "container"},
         "lines": {"type": "integer", "minimum": 1, "maximum": 2000, "default": 200},
         "since": {"type": "string", "description": "Containers only: e.g. '15m', '2h' or an RFC3339 time."},
         "grep": {"type": "string", "description": "Journal only: a pattern to match."},
         "user": {"type": "boolean", "description": "Units/journal: the user manager instead of the system one.", "default": False}})),
    ("estate_health", health, (), _schema(
        "estate_health",
        "HvkDeck's health checks for MIRA's services (up/down, HTTP code, latency) plus failed units, unhealthy or stopped "
        "containers and pending apt upgrades on debhvk.")),
    ("estate_jobs", jobs, ("job_id",), _schema(
        "estate_jobs",
        "HvkDeck jobs on debhvk (deploys, docker actions, manage.sh runs): the recent list, or one job's output by id.",
        {"job_id": {"type": "string", "description": "A job id from the list, e.g. 20261031-142233-a1b2c3."}})),
    ("estate_stacks", stacks, (), _schema(
        "estate_stacks",
        "The compose stacks manage.sh knows on debhvk (scopes, services, aliases) and the recent MIRA deploys.")),
]


# ---------------------------------------------------------------------------------------------------- text views

def _bar(pct: float, width: int = 12) -> str:
    n = max(0, min(width, round(pct / 100 * width)))
    return "█" * n + "░" * (width - n)


def render_overview(o: dict[str, Any]) -> str:
    m, c = o["mem"], o["containers"]
    mem_pct = 100 * m["used_gb"] / m["total_gb"] if m["total_gb"] else 0
    lines = [
        f"◉ {o['host']}  up {o['uptime_hours']}h  hvkdeckd {o.get('hvkdeckd_version') or '?'}",
        f"  cpu  {_bar(o['cpu_pct'])} {o['cpu_pct']:5.1f}%   load {' '.join(str(x) for x in o['load'])}",
        f"  mem  {_bar(mem_pct)} {m['used_gb']}/{m['total_gb']} GB   swap {m['swap_used_gb']}/{m['swap_total_gb']} GB",
    ]
    if o.get("hottest_sensor"):
        h = o["hottest_sensor"]
        lines.append(f"  temp {h['c']}°C ({h['chip']} {h['label']})   net ↓{o['net_mbps']['rx']} ↑{o['net_mbps']['tx']} Mb/s")
    for d in o["disks"]:
        lines.append(f"  disk {_bar(d['used_pct'] or 0)} {d['used_pct']:3}%  {d['mount']}  ({d['free_gb']} GB free)")
    lines.append(f"  containers {c.get('running', 0)}/{c.get('total', 0)} running"
                 + (f"   unhealthy: {', '.join(c['unhealthy'])}" if c.get("unhealthy") else "")
                 + (f"   stopped: {', '.join(c['stopped'])}" if c.get("stopped") else ""))
    lines.append(f"  health {o['health_ok']} ok" + (f", failing: {', '.join(h['name'] for h in o['health_failing'])}" if o["health_failing"] else ""))
    if o["failed_units"]:
        lines.append(f"  failed units: {', '.join(o['failed_units'])}")
    if o.get("jobs_running"):
        lines.append(f"  jobs running: {o['jobs_running']}")
    return "\n".join(lines)


def render_containers(r: dict[str, Any]) -> str:
    rows = r["containers"]
    if not rows:
        return f"no containers match ({r['of']} total)"
    w = max(len(x["name"]) for x in rows)
    out = [f"{r['count']} of {r['of']} containers"]
    for x in rows:
        mark = "●" if x.get("state") == "running" else "○"
        if x.get("health") == "unhealthy":
            mark = "✖"
        out.append(f"  {mark} {x['name']:<{w}}  {x.get('status', ''):<28} {x.get('cpu', ''):>7} {x.get('mem', '')}")
    return "\n".join(out)


def render_health(r: dict[str, Any]) -> str:
    out = []
    for c in r["checks"]:
        out.append(f"  {'✔' if c['ok'] else '✖'} {c['name']:<24} {c['code'] or '-':>4} {c['ms'] or 0:>5} ms" + (f"  {c['error']}" if c["error"] else ""))
    tail = []
    if r["failed_units"]:
        tail.append("failed units: " + ", ".join(r["failed_units"]))
    if r["unhealthy_containers"]:
        tail.append("unhealthy: " + ", ".join(r["unhealthy_containers"]))
    if r["stopped_containers"]:
        tail.append("stopped: " + ", ".join(r["stopped_containers"]))
    if r.get("apt_upgradable"):
        tail.append(f"apt: {r['apt_upgradable']} upgradable")
    return "\n".join(["health checks"] + out + (["  " + t for t in tail] or ["  nothing failed"]))


def render_jobs(r: dict[str, Any]) -> str:
    if "jobs" not in r:
        return r.get("text") or "(no output)"
    if not r["jobs"]:
        return "no jobs"
    return "\n".join(["jobs (newest first)"] + [
        f"  {'▶' if j['running'] else ('✔' if j['rc'] == 0 else '✖')} {j['id']}  {j['title']}  ({j['started_ago_min']} min ago)" for j in r["jobs"]])


def render_stacks(r: dict[str, Any]) -> str:
    out = [f"scopes: {', '.join(r['scopes']) or '-'}", f"services ({len(r['services'])}):"]
    out += [f"  {s['name']:<28} {s['scope']}" for s in r["services"]]
    if r["recent_deploys"]:
        out.append("recent deploys:")
        out += [f"  {d['id']}  {d['result']}  {d['detail']}" for d in r["recent_deploys"]]
    return "\n".join(out)


USAGE = ("estate                      overview of debhvk\n"
         "estate containers [filter]  containers (filter by name/image/project)\n"
         "estate logs <container> [n] last n log lines of a container\n"
         "estate health               health checks, failed units, stopped containers\n"
         "estate jobs [id]            HvkDeck jobs, or one job's output\n"
         "estate stacks               compose scopes, services, recent deploys")


def run_view(argv: list[str]) -> str:
    """The shared text front-end for /estate and `argus estate`."""
    cmd, rest = (argv[0].lower(), argv[1:]) if argv else ("overview", [])
    try:
        if cmd in ("overview", "status", "o"):
            return render_overview(overview())
        if cmd in ("containers", "c", "ps"):
            return render_containers(containers(filter=" ".join(rest)))
        if cmd in ("logs", "l"):
            if not rest:
                return "usage: estate logs <container> [lines]"
            n = int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else 80
            return logs(rest[0], lines=n)["text"] or "(no log lines)"
        if cmd in ("health", "h"):
            return render_health(health())
        if cmd in ("jobs", "j"):
            return render_jobs(jobs(rest[0] if rest else ""))
        if cmd in ("stacks", "s"):
            return render_stacks(stacks())
        if cmd in ("help", "-h", "--help", "?"):
            return USAGE
        return f"unknown: {cmd}\n{USAGE}"
    except hvkdeck.DeckError as e:
        return f"estate: {e}"
    except Exception as e:
        return f"estate: {type(e).__name__}: {e}"


def _slash(raw_args: str = "", **_: Any) -> str:
    return run_view((raw_args or "").split())


def _cli_setup(parser) -> None:
    parser.add_argument("view", nargs="*", help="overview | containers [filter] | logs <name> [n] | health | jobs [id] | stacks")


def _cli_run(args) -> int:
    out = run_view(list(getattr(args, "view", []) or []))
    print(out)
    return 1 if out.startswith("estate: ") else 0


# ---------------------------------------------------------------------------------------------------- register

def register(ctx) -> None:
    for name, fn, keys, schema in TOOLS:
        ctx.register_tool(name=name, toolset="estate", schema=schema, handler=_tool(fn, *keys),
                          check_fn=hvkdeck.available, emoji="◉")
    ctx.register_command("estate", handler=_slash, description="The MIRA estate from HvkDeck: overview, containers, logs, health, jobs, stacks.",
                         args_hint="[overview|containers|logs|health|jobs|stacks]")
    ctx.register_cli_command(name="estate", help="The MIRA estate from HvkDeck (debhvk)", setup_fn=_cli_setup, handler_fn=_cli_run,
                             description=USAGE)
