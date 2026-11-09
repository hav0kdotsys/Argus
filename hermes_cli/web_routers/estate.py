"""Estate routes: the MIRA estate (HvkDeck) for ARGUS clients — the Desktop pane and the dashboard.

Read-only. The HvkDeck credentials (``~/.config/hvkdeck/credentials.json``) are read server-side and
hvkdeckd is proxied here, so the deck token and the Cloudflare Access service token never reach a
browser or the Electron renderer. Routing mirrors the argus-cockpit plugin's client — the LAN URL
first (fast at home), the Cloudflare Access hostname as the fallback when away — and whichever
answered last is tried first for a minute. Only GET is exposed; nothing here can change the estate.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

router = APIRouter()

_LAN_TIMEOUT = 2.5
_REMOTE_TIMEOUT = 20.0
_preferred: dict[str, float] = {}  # route name -> when it last worked


def _credentials_path() -> Path:
    env = os.environ.get("HVKDECK_CREDENTIALS")
    if env:
        return Path(env).expanduser()
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "hvkdeck" / "credentials.json"
    return Path.home() / ".config" / "hvkdeck" / "credentials.json"


def _load_credentials() -> dict[str, str]:
    path = _credentials_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail=f"no HvkDeck credentials at {path}")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"cannot read HvkDeck credentials: {exc}")
    if not isinstance(data, dict) or not data.get("token"):
        raise HTTPException(status_code=503, detail="HvkDeck credentials have no token")
    return {k: str(v) for k, v in data.items() if isinstance(v, (str, int, float))}


def _routes(creds: dict[str, str]) -> list[tuple[str, str, dict[str, str], float]]:
    auth = {"Authorization": f"Bearer {creds['token']}", "Accept": "application/json", "User-Agent": "argus-estate/0.1"}
    out: list[tuple[str, str, dict[str, str], float]] = []
    if creds.get("lan_url"):
        out.append(("lan", creds["lan_url"].rstrip("/"), auth, _LAN_TIMEOUT))
    if creds.get("remote_url"):
        headers = dict(auth)
        if creds.get("cf_client_id") and creds.get("cf_client_secret"):
            headers["CF-Access-Client-Id"] = creds["cf_client_id"]
            headers["CF-Access-Client-Secret"] = creds["cf_client_secret"]
        out.append(("remote", creds["remote_url"].rstrip("/"), headers, _REMOTE_TIMEOUT))
    if not out:
        raise HTTPException(status_code=503, detail="HvkDeck credentials have neither lan_url nor remote_url")
    now = time.time()
    out.sort(key=lambda r: 0 if now - _preferred.get(r[0], 0) < 60 else 1)
    return out


# The hvkdeckd GET paths ARGUS clients may read. Keeps this a fixed read-only surface, never an open proxy.
_ALLOWED = {"devices", "phones", "overview", "health", "containers", "network", "processes", "jobs", "stacks", "deploys"}


def fetch_estate(path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """GET hvkdeckd ``/api/<path>`` and return the decoded JSON. Blocking — call via a threadpool."""
    head = path.strip("/").split("/", 1)[0]
    if head not in _ALLOWED:
        raise HTTPException(status_code=404, detail=f"unknown estate path: {head}")
    creds = _load_credentials()
    qs = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v not in (None, "")})
    rel = "/api/" + path.strip("/") + (f"?{qs}" if qs else "")
    tried: list[str] = []
    for name, base, headers, timeout in _routes(creds):
        req = urllib.request.Request(base + rel, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
            _preferred[name] = time.time()
            out = json.loads(body.decode("utf-8") or "{}")
            return out if isinstance(out, dict) else {"data": out}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", "")
            except Exception:
                pass
            if exc.code in (401, 403) and name == "remote" and not detail:
                tried.append(f"{name}: HTTP {exc.code}")
                continue
            raise HTTPException(status_code=502, detail=f"hvkdeckd {rel}: HTTP {exc.code}{': ' + detail if detail else ''}")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            tried.append(f"{name}: {getattr(exc, 'reason', exc)}")
    raise HTTPException(status_code=504, detail="HvkDeck is unreachable (" + "; ".join(tried) + ")")


@router.get("/api/estate/devices")
async def estate_devices() -> JSONResponse:
    """The whole estate's liveness: HavoK's machines, the friend PCs, and the phones on MIRA's channel."""
    return JSONResponse(await run_in_threadpool(fetch_estate, "devices"))


@router.get("/api/estate/phones")
async def estate_phones() -> JSONResponse:
    """The phones on MIRA's device channel: liveness plus battery/network when a phone's channel is live."""
    return JSONResponse(await run_in_threadpool(fetch_estate, "phones"))


@router.get("/api/estate/overview")
async def estate_overview() -> JSONResponse:
    """debhvk at a glance: CPU, load, memory, disks, temps, containers, failing checks."""
    return JSONResponse(await run_in_threadpool(fetch_estate, "overview"))


@router.get("/api/estate/health")
async def estate_health() -> JSONResponse:
    """HvkDeck's service health checks plus failed units and unhealthy/stopped containers."""
    return JSONResponse(await run_in_threadpool(fetch_estate, "health"))
