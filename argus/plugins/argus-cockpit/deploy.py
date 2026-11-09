"""Guarded ``/deploy`` — the cockpit's one WRITE path.

Every other cockpit surface is read-only (a GET to hvkdeckd). This is the deliberate exception: a
``/deploy`` runs a REAL MIRA deploy on debhvk by dispatching MIRA's own guarded ``mira_deploy`` MCP
tool, so the systemd-unit detachment, the compose replay and the audit trail all stay on MIRA's
side where they already live. ARGUS only adds a **typed confirm step** in front of it — the same
across the TUI ``/deploy``, ``argus deploy`` and any messaging surface, where an interactive y/n
prompt isn't available — so a production deploy is never one keystroke away.

Flow:
  ``/deploy``                       recent deploys + the deployable targets (read-only)
  ``/deploy <service>``             the plan + the exact line that will actually run it
  ``/deploy <service> confirm``     runs it (add ``build`` to rebuild the image first)
  ``/deploy status [id]``           the log/outcome of a deploy (default: the most recent)
"""

from __future__ import annotations

import re
from typing import Any

from . import deploys, hvkdeck  # deploys(): read-only target/recent list, shared with /estate deploys

# The MIRA MCP tools this command drives (server "mira"); resolved to their registry names at call
# time so a rename on MIRA's side or a scoped registration still lands.
_DEPLOY_TOOL = "mira_deploy"
_STATUS_TOOL = "mira_deploy_status"
# mira_deploy is guarded server-side by HavoK's hardware key: a deploy only runs after she touches
# the key on laphvk. request_key_approval raises that prompt for this exact call and waits for her
# touch; the typed `confirm` is ARGUS's gate, her key is MIRA's — both must pass.
_APPROVE_TOOL = "request_key_approval"

# Typed confirmation tokens — one of these as a trailing word turns a plan into a real deploy.
_CONFIRM = {"confirm", "--confirm", "yes", "-y", "go"}
_BUILD = {"build", "--build", "-b"}

# Deployable services, if hvkdeckd's live target list is unreachable. mira-api / mira-mcp redeploys
# drop ARGUS's own MCP tools for ~40s; mira-web (the first test target) does not.
_KNOWN_TARGETS = ("mira-api", "mira-mcp", "mira-web", "mira-supervisor", "vortex-discord-bot")
_TOOL_DROPPING = {"mira-api", "mira-mcp"}


def _targets() -> list[str]:
    try:
        t = deploys().get("targets") or []
    except Exception:
        t = []
    return list(t) or list(_KNOWN_TARGETS)


def _recent_lines() -> list[str]:
    try:
        rec = deploys().get("recent") or []
    except hvkdeck.DeckError as e:
        return [f"  (deploy history unavailable: {e})"]
    if not rec:
        return ["  (no recent deploys)"]
    return [f"  {d.get('id', '?')}  {d.get('result', '?')}  {d.get('detail', '')}".rstrip() for d in rec[-8:]]


def _resolve_tool(dispatch_ctx, bare: str) -> str | None:
    """The registry name for a MIRA MCP tool (``mcp__mira__<bare>``), by live lookup so a scoped or
    renamed registration still resolves; falls back to the deterministic prefixed name."""
    from tools.registry import registry

    want = f"__{bare}"
    for entry in registry.get_all_entries():
        if entry.name == bare or entry.name.endswith(want):
            return entry.name
    try:
        from tools.mcp_tool_schema import mcp_prefixed_tool_name

        name = mcp_prefixed_tool_name("mira", bare)
        if registry.get_entry(name) is not None:
            return name
    except Exception:
        pass
    return None


def _plan(service: str, build: bool, targets: list[str]) -> str:
    warn = ""
    if service in _TOOL_DROPPING:
        warn = ("\n  ⚠ redeploying this drops ARGUS's own MIRA tools for ~40s — the deploy still "
                "completes;\n    check it afterwards with  /deploy status")
    confirm_line = f"/deploy {service} confirm" + (" build" if build else "")
    return (
        f"▶ deploy plan — {service}\n"
        f"  target     {service}" + ("  (not in the live target list — " + ", ".join(targets) + ")"
                                      if service not in targets else "") + "\n"
        f"  rebuild    {'yes — image is rebuilt first' if build else 'no — restart with the current image'}\n"
        f"  runs       MIRA's guarded mira_deploy on debhvk (detached systemd unit, compose replay)"
        f"{warn}\n\n"
        f"This is a REAL production deploy. To run it, repeat with the confirm word:\n"
        f"  {confirm_line}"
    )


def _as_text(out: Any) -> str:
    return out if isinstance(out, str) else str(out)


def _norm(text: str) -> str:
    """MCP tool output nests JSON as an escaped string (``\\"blocked\\":true``); drop the escaping
    so the field probes below match the same whether the envelope is one or two layers deep."""
    return text.replace("\\", "")


def _is_blocked(text: str) -> bool:
    """mira_deploy's own guard verdict — true when the key approval hasn't been granted."""
    t = _norm(text)
    return bool(re.search(r'"(?:blocked|guarded)"\s*:\s*true', t)) and not re.search(r'"ok"\s*:\s*true', t)


def _guard_message(text: str) -> str:
    m = re.search(r'"message"\s*:\s*"([^"]*)"', _norm(text))
    return m.group(1) if m else _norm(text).strip()[:300]


def _deploy_id(text: str) -> str | None:
    m = re.search(r"\b(\d{8}-\d{6}-[0-9A-Za-z-]+)\b", text)
    return m.group(1) if m else None


def _run_deploy(dispatch, service: str, build: bool) -> str:
    name = _resolve_tool(dispatch, _DEPLOY_TOOL)
    if not name:
        return ("deploy: MIRA's mira_deploy tool isn't loaded — is the `mira` MCP server connected? "
                "(try again once ARGUS has finished connecting to it)")

    # The real gate: ask HavoK to approve THIS exact deploy with her hardware key. The prompt and
    # reason appear on laphvk; the call blocks until she touches the key (or it times out). We pass
    # the bare tool name and the exact args MIRA's guard will match the subsequent deploy against.
    approve = _resolve_tool(dispatch, _APPROVE_TOOL)
    appr = ""
    if approve:
        appr = _as_text(dispatch(approve, {
            "kind": "action",
            "tool": _DEPLOY_TOOL,
            "arguments": {"service": service, "build": bool(build)},
            "summary": f"deploy {service} on debhvk" + (" (rebuild)" if build else ""),
            "reason": f"HavoK ran /deploy {service} from ARGUS and typed confirm.",
            "wait_seconds": 120,
        }))

    out = _as_text(dispatch(name, {"service": service, "build": bool(build)}))

    if _is_blocked(out):
        why = _guard_message(appr) if appr else ""
        return (f"✋ deploy NOT run — {service} needs HavoK's hardware-key touch on laphvk.\n"
                f"  {_guard_message(out)}\n"
                + (f"  approval: {why}\n" if why else "")
                + f"  Plug the key into laphvk and touch it when the prompt appears, then re-run:\n"
                f"  /deploy {service} confirm" + (" build" if build else ""))

    did = _deploy_id(out)
    head = f"✓ deploy started — {service}" + (" (with rebuild)" if build else "")
    tail = (f"\n  deploy id: {did}\n  check it with:  /deploy status {did}"
            if did else "\n  check it with:  /deploy status")
    return f"{head}\n  {out.strip()}{tail}"


def _run_status(dispatch, deploy_id: str) -> str:
    name = _resolve_tool(dispatch, _STATUS_TOOL)
    if not name:
        # fall back to hvkdeckd's own recent-deploy list — read-only and always available
        return "\n".join(["recent deploys (debhvk):"] + _recent_lines())
    args: dict[str, Any] = {"list": True} if not deploy_id else {"id": deploy_id}
    out = dispatch(name, args)
    return (out if isinstance(out, str) else str(out)).strip() or "(no status)"


def run_deploy(dispatch, argv: list[str]) -> str:
    """Shared front-end for ``/deploy`` and ``argus deploy``. *dispatch* is a ``(name, args) -> str``
    tool dispatcher (``ctx.dispatch_tool``), injected so this module never imports the plugin host."""
    words = [w.strip() for w in argv if w.strip()]
    lowered = [w.lower() for w in words]

    # bare /deploy, or /deploy status|list [id] — read-only
    if not words or lowered[0] in ("status", "list", "recent", "-s"):
        if words and lowered[0] in ("status", "list", "recent", "-s"):
            rest = [w for w in words[1:] if w.lower() not in ("list",)]
            return _run_status(dispatch, rest[0] if rest else "")
        targets = _targets()
        return "\n".join(
            ["deployable services: " + ", ".join(targets),
             "", "recent deploys:"] + _recent_lines()
            + ["", "run one with:  /deploy <service>   (then confirm)"])

    if lowered[0] in ("help", "-h", "--help", "?"):
        return __doc__ or "usage: /deploy <service> [confirm] [build] | /deploy status [id]"

    service = words[0]
    flags = set(lowered[1:])
    build = bool(flags & _BUILD)
    confirmed = bool(flags & _CONFIRM)
    targets = _targets()

    if service not in targets and service not in _KNOWN_TARGETS:
        return (f"deploy: unknown service '{service}'.\n"
                f"deployable services: {', '.join(targets)}")

    if not confirmed:
        return _plan(service, build, targets)
    return _run_deploy(dispatch, service, build)
