"""argus-cockpit - the MIRA estate from inside ARGUS.

The cockpit (see argus/ARGUS.md, phase 4): HvkDeck's view of the estate, three ways -
  - tools the agent calls (toolset ``estate``): overview, devices, containers, processes, services, logs, health,
    network, jobs, stacks, deploys;
  - ``/estate [overview|devices|containers [filter]|processes|services|logs <name>|health|network|jobs|stacks|
    deploys]`` inside a session;
  - ``argus estate ...`` from a shell, same sub-commands.

``estate_devices`` covers the whole estate - HavoK's machines and the friend-PC MiraAgent receivers - through
hvkdeckd's device board; the rest are debhvk itself. READ-ONLY by design: every call is a GET to hvkdeckd. Changing
the estate (restart a container, run a deploy) stays with MIRA's own guarded tools (docker_restart, mira_deploy)
which ARGUS reaches over the mira MCP server, so the approvals and the audit trail live in one place.
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


def devices() -> dict[str, Any]:
    """The whole estate's liveness: HavoK's machines and the friend-PC MiraAgent receivers."""
    d = hvkdeck.get("devices")
    out = []
    for x in d.get("devices") or []:
        online, agent_up = bool(x.get("online")), bool(x.get("agentUp"))
        out.append({
            "host": x.get("host"), "label": x.get("label") or x.get("host"),
            "owner": x.get("owner") or "", "role": x.get("role") or "", "kind": x.get("kind"),
            "status": "offline" if not online else ("online" if agent_up else "agent-down"),
            "online": online, "agent_up": agent_up, "latency_ms": x.get("latencyMs"),
            "uptime_hours": round((x.get("uptimeSec") or 0) / 3600, 1) if x.get("uptimeSec") else None,
            "load": x.get("load"),
            "services": [{"name": s.get("name"), "up": bool(s.get("up"))} for s in (x.get("services") or [])],
            "since": x.get("since"), "error": x.get("error") or None,
        })
    return {"devices": out,
            "online": sum(1 for x in out if x["online"]),
            "agent_down": sum(1 for x in out if x["status"] == "agent-down"),
            "offline": sum(1 for x in out if not x["online"]),
            "checked_at": d.get("at")}


def phones() -> dict[str, Any]:
    """The estate's phones on MIRA's device channel - liveness from the board, vitals (battery/network) when the
    phone's channel is actively connected (deviceVitals is empty otherwise)."""
    d = hvkdeck.get("phones")
    ps = d.get("phones") or []
    return {"phones": ps,
            "online": sum(1 for p in ps if p.get("online")),
            "connected": sum(1 for p in ps if p.get("connected"))}


def processes(sort: str = "cpu", limit: int = 20, filter: str = "") -> dict[str, Any]:
    ps = hvkdeck.get("processes", {"sort": sort}).get("processes") or []
    f = filter.lower()
    if f:
        ps = [p for p in ps if f in (str(p.get("comm", "")) + " " + str(p.get("args", ""))).lower() or f == str(p.get("pid"))]
    n = max(1, min(100, int(limit)))
    return {"sort": sort, "count": min(n, len(ps)), "of": len(ps),
            "processes": [{"pid": p.get("pid"), "user": p.get("user"), "cpu": p.get("cpu"), "mem_pct": p.get("mem"),
                           "rss_gb": _gb(p.get("rss")), "age_s": p.get("age"), "cmd": p.get("comm"), "args": p.get("args")}
                          for p in ps[:n]]}


def services(filter: str = "", scope: str = "system", state: str = "active") -> dict[str, Any]:
    us = hvkdeck.get(f"units/{quote(scope, safe='')}").get("units") or []
    f = filter.lower()
    out = []
    for u in us:
        name, desc, active, sub = u.get("unit", ""), u.get("description", ""), u.get("active", ""), u.get("sub", "")
        if f and f not in name.lower() and f not in desc.lower():
            continue
        if state == "active" and active not in ("active", "activating", "failed"):
            continue
        if state == "running" and sub != "running":
            continue
        if state == "failed" and active != "failed":
            continue
        out.append({"unit": name, "active": active, "sub": sub, "enabled": u.get("enabled", ""), "description": desc})
    return {"scope": scope, "state": state, "count": len(out), "of": len(us),
            "failed": [u["unit"] for u in out if u["active"] == "failed"], "services": out[:120]}


def network() -> dict[str, Any]:
    n = hvkdeck.get("network")
    return {"interfaces": [{"name": i.get("name"), "state": i.get("state"), "addrs": i.get("addrs") or []}
                           for i in (n.get("interfaces") or []) if i.get("addrs")],
            "listening": [{"local": l.get("local"), "process": l.get("process")} for l in (n.get("listening") or [])],
            "tunnels": n.get("tunnels") or {}}


def deploys() -> dict[str, Any]:
    d = hvkdeck.get("deploys")
    return {"recent": (d.get("deploys") or [])[-12:], "targets": d.get("targets") or []}


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
    ("estate_devices", devices, (), _schema(
        "estate_devices",
        "Every estate device at a glance: HavoK's machines (winhvk, laphvk, debhvk) and the friend-PC MiraAgent receivers "
        "(winbatata = Sarah's, winghost = Ghost's, winfranci = Franci's). Each shows online/offline, whether its MIRA "
        "agent is answering (agent-down = PC up but agent not running), latency, uptime and load. Use for 'is winbatata "
        "up', 'are the friend PCs online', 'which agents are down'.")),
    ("estate_phones", phones, (), _schema(
        "estate_phones",
        "The estate's phones on MIRA's device channel (mobilehvk = HavoK's, mobileghost = Ghost's): online/offline, and "
        "battery, charging, network and uptime when the phone's channel is actively connected.")),
    ("estate_processes", processes, ("sort", "limit", "filter"), _schema(
        "estate_processes",
        "Top processes on debhvk by CPU or memory (pid, user, %cpu, %mem, RSS, age, command). Optionally filter by a "
        "substring of the command or a pid.",
        {"sort": {"type": "string", "enum": ["cpu", "mem"], "default": "cpu"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
         "filter": {"type": "string", "description": "Substring of the command/args, or a pid."}})),
    ("estate_services", services, ("filter", "scope", "state"), _schema(
        "estate_services",
        "systemd units on debhvk (active/sub state, enabled, description). Defaults to the system manager and the units "
        "that are active, activating or failed; set state=all for every unit, or scope=user for the user manager.",
        {"filter": {"type": "string", "description": "Substring of the unit name or description, e.g. 'mira' or 'cloudflared'."},
         "scope": {"type": "string", "enum": ["system", "user"], "default": "system"},
         "state": {"type": "string", "enum": ["active", "running", "failed", "all"], "default": "active"}})),
    ("estate_network", network, (), _schema(
        "estate_network",
        "debhvk's network: interfaces and their addresses, the Cloudflare tunnels' state (cloudflared, "
        "cloudflared-ssh-debhvk), and what is listening on which TCP port and the process behind it.")),
    ("estate_deploys", deploys, (), _schema(
        "estate_deploys",
        "Recent mira-deploy results on debhvk (id, result, detail) and the deployable targets (mira-api, mira-mcp, "
        "mira-web, mira-supervisor, vortex-discord-bot). Read-only: running a deploy stays with MIRA's guarded tools.")),
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


_DEV_DOT = {"online": "●", "agent-down": "◐", "offline": "○"}


def render_devices(r: dict[str, Any]) -> str:
    rows = r["devices"]
    out = [f"estate devices — {r['online']} online, {r['agent_down']} agent-down, {r['offline']} offline"]
    w = max((len(x["label"]) for x in rows), default=4)
    for x in rows:
        line = f"  {_DEV_DOT.get(x['status'], '?')} {x['label']:<{w}}  {x['status']:<10}"
        if x["online"] and x.get("latency_ms") is not None:
            line += f" {x['latency_ms']:>4} ms"
        extra = []
        if x.get("owner"):
            extra.append(x["owner"])
        if x.get("uptime_hours"):
            extra.append(f"up {x['uptime_hours']}h")
        down = [s["name"] for s in x["services"] if not s["up"]]
        if down:
            extra.append("down: " + ", ".join(down))
        if x.get("error"):
            extra.append(x["error"])
        if extra:
            line += "  " + " · ".join(extra)
        out.append(line)
    return "\n".join(out)


def render_phones(r: dict[str, Any]) -> str:
    rows = r["phones"]
    out = [f"estate phones — {r['online']} online, {r['connected']} reporting vitals"]
    w = max((len(x.get("label", "")) for x in rows), default=4)
    for p in rows:
        mark = "●" if p.get("online") else "○"
        line = f"  {mark} {p.get('label', ''):<{w}}  {'online' if p.get('online') else 'offline'}"
        bits = []
        if p.get("owner"):
            bits.append(p["owner"])
        if p.get("battery") is not None:
            bits.append(f"{p['battery']}%{'⚡' if p.get('charging') else ''}")
        if p.get("network"):
            bits.append(str(p["network"]))
        if p.get("uptimeDays") is not None:
            bits.append(f"up {p['uptimeDays']}d")
        if p.get("online") and not p.get("connected"):
            bits.append("no live channel")
        if bits:
            line += "  " + " · ".join(bits)
        out.append(line)
    return "\n".join(out)


def render_processes(r: dict[str, Any]) -> str:
    out = [f"top {r['count']} of {r['of']} processes by {r['sort']}"]
    for p in r["processes"]:
        out.append(f"  {p['pid']:>7}  {p['user']:<10} {p['cpu']:>5}%cpu {p['mem_pct']:>5}%mem {p['rss_gb']:>5}G  {p['cmd']}")
    return "\n".join(out)


def render_services(r: dict[str, Any]) -> str:
    out = [f"{r['count']} of {r['of']} units ({r['scope']}, state={r['state']})"]
    if r["failed"]:
        out.append("  failed: " + ", ".join(r["failed"]))
    for u in r["services"]:
        mark = "✖" if u["active"] == "failed" else ("●" if u["sub"] == "running" else "○")
        out.append(f"  {mark} {u['unit']:<34} {u['active']:<9} {u['sub']:<9} {u['enabled']}")
    return "\n".join(out)


def render_network(r: dict[str, Any]) -> str:
    out = ["interfaces:"]
    for i in r["interfaces"]:
        out.append(f"  {i['name']:<10} {i['state']:<7} {', '.join(i['addrs'])}")
    out.append("tunnels: " + (", ".join(f"{k}={v}" for k, v in r["tunnels"].items()) or "-"))
    out.append(f"listening ({len(r['listening'])}):")
    out += [f"  {l['local']:<24} {l['process']}" for l in r["listening"][:40]]
    return "\n".join(out)


def render_deploys(r: dict[str, Any]) -> str:
    out = ["deploy targets: " + (", ".join(r["targets"]) or "-")]
    if r["recent"]:
        out.append("recent:")
        out += [f"  {d['id']}  {d['result']}  {d.get('detail', '')}" for d in r["recent"]]
    return "\n".join(out)


USAGE = ("estate                      overview of debhvk\n"
         "estate devices              every estate device: HavoK's machines + the friend PCs\n"
         "estate phones               the phones on MIRA's device channel (battery/network when live)\n"
         "estate containers [filter]  containers (filter by name/image/project)\n"
         "estate processes [filter]   top processes by CPU (add 'mem' to sort by memory)\n"
         "estate services [filter]    systemd units (active/failed; 'all' for every unit)\n"
         "estate logs <container> [n] last n log lines of a container\n"
         "estate health               health checks, failed units, stopped containers\n"
         "estate network              interfaces, tunnels, listening ports\n"
         "estate jobs [id]            HvkDeck jobs, or one job's output\n"
         "estate stacks               compose scopes, services, recent deploys\n"
         "estate deploys              recent mira-deploy results and targets")


def run_view(argv: list[str]) -> str:
    """The shared text front-end for /estate and `argus estate`."""
    cmd, rest = (argv[0].lower(), argv[1:]) if argv else ("overview", [])
    try:
        if cmd in ("overview", "status", "o"):
            return render_overview(overview())
        if cmd in ("devices", "device", "d", "dev"):
            return render_devices(devices())
        if cmd in ("phones", "phone", "mobile"):
            return render_phones(phones())
        if cmd in ("containers", "c", "ps"):
            return render_containers(containers(filter=" ".join(rest)))
        if cmd in ("processes", "proc", "p", "top"):
            lowered = [w.lower() for w in rest]
            srt = "mem" if ("mem" in lowered or "memory" in lowered) else "cpu"
            flt = " ".join(w for w in rest if w.lower() not in ("mem", "memory", "cpu"))
            return render_processes(processes(sort=srt, filter=flt))
        if cmd in ("services", "units", "svc"):
            st = "all" if "all" in [w.lower() for w in rest] else "active"
            scope = "user" if "user" in [w.lower() for w in rest] else "system"
            flt = " ".join(w for w in rest if w.lower() not in ("all", "user", "system"))
            return render_services(services(filter=flt, scope=scope, state=st))
        if cmd in ("logs", "l"):
            if not rest:
                return "usage: estate logs <container> [lines]"
            n = int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else 80
            return logs(rest[0], lines=n)["text"] or "(no log lines)"
        if cmd in ("health", "h"):
            return render_health(health())
        if cmd in ("network", "net", "n"):
            return render_network(network())
        if cmd in ("jobs", "j"):
            return render_jobs(jobs(rest[0] if rest else ""))
        if cmd in ("stacks", "s"):
            return render_stacks(stacks())
        if cmd in ("deploys", "deploy", "deployments"):
            return render_deploys(deploys())
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
    parser.add_argument("view", nargs="*", help="overview | devices | containers [filter] | processes [filter] | "
                        "services [filter] | logs <name> [n] | health | network | jobs [id] | stacks | deploys")


def _cli_run(args) -> int:
    out = run_view(list(getattr(args, "view", []) or []))
    print(out)
    return 1 if out.startswith("estate: ") else 0


# ---------------------------------------------------------------------------------------------------- register

def _deploy_slash_factory(ctx) -> Callable[..., str]:
    from . import deploy as _deploy

    def _deploy_slash(raw_args: str = "", **_: Any) -> str:
        return _deploy.run_deploy(ctx.dispatch_tool, (raw_args or "").split())

    return _deploy_slash


def _deploy_cli_setup(parser) -> None:
    parser.add_argument("args", nargs="*",
                        help="<service> [confirm] [build]  |  status [id]  |  (empty: list targets + recent)")


def _deploy_cli_run_factory(ctx) -> Callable[..., int]:
    from . import deploy as _deploy

    def _run(args) -> int:
        out = _deploy.run_deploy(ctx.dispatch_tool, list(getattr(args, "args", []) or []))
        print(out)
        return 1 if out.startswith("deploy: ") else 0

    return _run


def register(ctx) -> None:
    for name, fn, keys, schema in TOOLS:
        ctx.register_tool(name=name, toolset="estate", schema=schema, handler=_tool(fn, *keys),
                          check_fn=hvkdeck.available, emoji="◉")
    ctx.register_command("estate", handler=_slash,
                         description="The MIRA estate from HvkDeck: overview, devices, containers, processes, services, logs, health, network, jobs, stacks, deploys.",
                         args_hint="[overview|devices|containers|processes|services|logs|health|network|jobs|stacks|deploys]")
    ctx.register_cli_command(name="estate", help="The MIRA estate from HvkDeck (debhvk)", setup_fn=_cli_setup, handler_fn=_cli_run,
                             description=USAGE)

    # The one WRITE path: a guarded, confirm-gated deploy that drives MIRA's own mira_deploy tool.
    ctx.register_command("deploy", handler=_deploy_slash_factory(ctx),
                         description="Guarded MIRA deploy from ARGUS. /deploy lists targets; /deploy <service> shows the "
                                     "plan; /deploy <service> confirm runs a REAL deploy; /deploy status [id] checks one.",
                         args_hint="[<service> [confirm] [build] | status [id]]")
    ctx.register_cli_command(name="deploy", help="Guarded MIRA deploy (debhvk) from ARGUS — confirm-gated",
                             setup_fn=_deploy_cli_setup, handler_fn=_deploy_cli_run_factory(ctx),
                             description="Guarded MIRA deploy. `argus deploy` lists targets + recent; `argus deploy "
                                         "<service>` shows the plan; `argus deploy <service> confirm [build]` runs a REAL "
                                         "deploy; `argus deploy status [id]` checks one.")
