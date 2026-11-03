"""MIRA's body asks her own backend through ARGUS: the relay on 127.0.0.1:8773.

Her body (the Capri fork, ``mira-body``) holds no keys and picks no provider. Each thing said to it, and each moment it
notices, is one POST here; ARGUS adds MIRA's bearer and hands it to mira-api's ``/v1/mira/call/stream``, then streams her
events (``turn.started``, ``turn.update``, ``turn.final``, ``turn.error``) straight back. Her router decides who answers.

Two sessions (HavoK, 3 Nov):
- ``main``: what HavoK says to her body joins MIRA's main conversation, the same ``agent:desktop`` scope Mira Desktop and
  the Voice Interface use, so it is one conversation with one memory wherever she's spoken to.
- ``body``: the body's ambient moments (game commentary, live reactions, watch-along asides) go to a linked side
  session, ``agent:body``, so they never crowd her main history.

The body finds the relay through ``argus.json`` in its own data folder (port and a token made fresh each start, readable
by HavoK only). Loopback only; a request without the token is refused.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
import urllib.error
import urllib.request
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import backend

logger = logging.getLogger(__name__)

PORT = 8773
HEADER = "X-Argus-Token"
SESSIONS = {"main": None, "body": "body"}      # session -> mira-api userId (the scope modifier)
TURN_TIMEOUT = 600


def body_folder() -> Path:
    """Where Mira's body keeps its things: %LOCALAPPDATA%\\Mira, or ~/.config/Mira."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Mira"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "Mira"


def where_said(host: str, session: str) -> str:
    if session == "main":
        return f"\n\n(HavoK said this to your body on {host}.)"
    return f"\n\n(From your body on {host}.)"


def request_for(text: str, session: str, host: str, max_tokens: int, base: str, token: str) -> urllib.request.Request:
    body = {"messages": [{"role": "user", "content": text + where_said(host, session)}], "mode": "agent",
            "maxTokens": max_tokens, "temperature": 0.9}
    if SESSIONS[session]:
        body["userId"] = SESSIONS[session]
    return urllib.request.Request(
        f"{base.rstrip('/')}/v1/mira/call/stream", data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Accept": "text/event-stream", "X-Jarvis-Client": "desktop"})


def _event(kind: str, payload: dict) -> bytes:
    return f"event: {kind}\ndata: {json.dumps({'type': kind, **payload})}\n\n".encode()


class Relay:
    def __init__(self, host: str, folder: Path | None = None, port: int = PORT):
        self.host, self.folder, self.port = host, folder or body_folder(), port
        self.token = secrets.token_urlsafe(24)
        self.server: ThreadingHTTPServer | None = None

    def announce(self) -> None:
        """argus.json in her body's folder: how it reaches this relay. HavoK-only on Linux."""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / "argus.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({"port": self.port, "token": self.token, "host": self.host}), encoding="utf-8")
        if sys.platform != "win32":
            temp.chmod(0o600)
        temp.replace(path)

    def stream(self, text: str, session: str, max_tokens: int, write) -> None:
        base, token = backend._config()
        if not token:
            write(_event("turn.error", {"error": "ARGUS has no MIRA_AUTH_TOKEN on this machine", "status": "unconfigured"}))
            return
        request = request_for(text, session, self.host, max_tokens, base, token)
        try:
            with urllib.request.urlopen(request, timeout=TURN_TIMEOUT) as response:
                for line in response:
                    write(line)
        except urllib.error.HTTPError as exc:
            write(_event("turn.error", {"error": f"mira-api answered {exc.code}", "status": "http"}))
        except (OSError, ValueError) as exc:
            logger.warning("relay: Mira's backend didn't answer (%s)", exc)
            write(_event("turn.error", {"error": "Mira's backend didn't answer", "status": "unreachable"}))

    def serve(self) -> ThreadingHTTPServer:
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_POST(self):
                if self.path != "/turn" or not compare_digest(self.headers.get(HEADER, ""), relay.token):
                    self.send_error(404 if self.path != "/turn" else 403)
                    return
                try:
                    ask = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    text, session = str(ask["text"]).strip(), str(ask.get("session", "main"))
                    max_tokens = int(ask.get("max_tokens", 1500))
                except (KeyError, TypeError, ValueError):
                    self.send_error(400)
                    return
                if not text or session not in SESSIONS:
                    self.send_error(400)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()

                def write(chunk: bytes) -> None:
                    self.wfile.write(chunk)
                    self.wfile.flush()

                try:
                    relay.stream(text, session, max_tokens, write)
                except (BrokenPipeError, ConnectionResetError):
                    logger.info("relay: her body stopped listening mid-turn")

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_port
        from agent.memory_provider import spawn_context_thread

        spawn_context_thread(self.server.serve_forever, name="mira-relay").start()
        self.announce()
        return self.server


HANDS_PORT = 8774


def hands(what: str, call: dict | None = None, folder: Path | None = None, timeout: float = 120) -> dict | list:
    """MIRA's MCP using her body's hands here: ``kit`` (her tools, in MCP's shape) or ``do`` (one tool call). Reached over
    SSH as ``argus companion hands kit|do <base64 json>``; the answer is JSON for her MCP to read."""
    try:
        door = json.loads(((folder or body_folder()) / "argus.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"error": "ARGUS isn't housing her body on this machine right now"}
    path, data = ("/kit", None) if what == "kit" else ("/do", json.dumps(call or {}).encode("utf-8"))
    request = urllib.request.Request(f"http://127.0.0.1:{HANDS_PORT}{path}", data=data,
                                     headers={HEADER: str(door.get("token", "")), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"error": f"her body answered {exc.code}"}
    except (OSError, ValueError):
        return {"error": "her body isn't up on this machine"}


def start(host: str) -> Relay | None:
    relay = Relay(host)
    try:
        relay.serve()
    except OSError:
        logger.warning("relay: port %s taken; her body can't reach MIRA through ARGUS this run", PORT)
        return None
    return relay
