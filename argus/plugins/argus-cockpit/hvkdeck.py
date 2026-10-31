"""A small client for hvkdeckd, HvkDeck's API on debhvk.

Credentials are the ones the HvkDeck apps already use, read on every call so a rotated token needs no restart:
``$HVKDECK_CREDENTIALS`` or ``~/.config/hvkdeck/credentials.json`` (Linux/macOS) / ``%APPDATA%\\hvkdeck\\credentials.json``
(Windows), with keys ``lan_url``, ``remote_url``, ``token``, ``cf_client_id``, ``cf_client_secret``.

Route: the LAN URL first (fast, home network), then the remote URL behind Cloudflare Access (service-token
headers). Whichever answered last is tried first for a minute, so off the LAN the dead LAN hop isn't paid twice.
Only GET is exposed: this client cannot change anything on debhvk.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

_LAN_TIMEOUT = 2.5
_REMOTE_TIMEOUT = 20.0
_preferred: dict[str, float] = {}  # route name -> time it last worked


class DeckError(Exception):
    """A readable failure: no credentials, unreachable, or the API said no."""


def credentials_path() -> Path:
    env = os.environ.get("HVKDECK_CREDENTIALS")
    if env:
        return Path(env).expanduser()
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "hvkdeck" / "credentials.json"
    return Path.home() / ".config" / "hvkdeck" / "credentials.json"


def load_credentials() -> dict[str, str]:
    p = credentials_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise DeckError(f"no HvkDeck credentials at {p} (sign the HvkDeck app in on this machine, or set HVKDECK_CREDENTIALS)")
    except (OSError, ValueError) as e:
        raise DeckError(f"cannot read HvkDeck credentials at {p}: {e}")
    if not isinstance(data, dict) or not data.get("token"):
        raise DeckError(f"HvkDeck credentials at {p} have no token")
    return {k: str(v) for k, v in data.items() if isinstance(v, (str, int, float))}


def available() -> bool:
    try:
        load_credentials()
        return True
    except DeckError:
        return False


def _routes(creds: dict[str, str]) -> list[tuple[str, str, dict[str, str], float]]:
    auth = {"Authorization": f"Bearer {creds['token']}", "Accept": "application/json", "User-Agent": "argus-cockpit/0.1"}
    routes = []
    if creds.get("lan_url"):
        routes.append(("lan", creds["lan_url"].rstrip("/"), auth, _LAN_TIMEOUT))
    if creds.get("remote_url"):
        h = dict(auth)
        if creds.get("cf_client_id") and creds.get("cf_client_secret"):
            h["CF-Access-Client-Id"] = creds["cf_client_id"]
            h["CF-Access-Client-Secret"] = creds["cf_client_secret"]
        routes.append(("remote", creds["remote_url"].rstrip("/"), h, _REMOTE_TIMEOUT))
    if not routes:
        raise DeckError("HvkDeck credentials have neither lan_url nor remote_url")
    # Prefer the route that worked in the last minute.
    now = time.time()
    routes.sort(key=lambda r: 0 if now - _preferred.get(r[0], 0) < 60 else 1)
    return routes


def get(path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """GET /api/<path> and return the decoded JSON object. Raises DeckError with a sentence a person can act on."""
    creds = load_credentials()
    qs = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v not in (None, "")})
    rel = "/api/" + path.lstrip("/") + (f"?{qs}" if qs else "")
    tried = []
    for name, base, headers, timeout in _routes(creds):
        req = urllib.request.Request(base + rel, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
            _preferred[name] = time.time()
            out = json.loads(body.decode("utf-8") or "{}")
            return out if isinstance(out, dict) else {"data": out}
        except urllib.error.HTTPError as e:
            # The API answered: don't fall through to the other route, its answer would be the same.
            try:
                detail = json.loads(e.read().decode("utf-8")).get("error", "")
            except Exception:
                detail = ""
            if e.code in (401, 403) and name == "remote" and "cloudflare" not in detail.lower() and not detail:
                tried.append(f"{name}: HTTP {e.code} (Cloudflare Access refused the service token?)")
                continue
            raise DeckError(f"hvkdeckd {rel}: HTTP {e.code}{': ' + detail if detail else ''}")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            reason = getattr(e, "reason", e)
            tried.append(f"{name}: {reason}")
    raise DeckError("HvkDeck is unreachable (" + "; ".join(tried) + ")")
