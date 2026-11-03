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
import shutil
import subprocess
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
SEE_PROMPT = ("This is a frame of HavoK's own computer screen. Say plainly what's on it: the app or game, what's happening, "
              "any text that matters. Be concise and leave out private details like passwords or message contents.")


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
    def __init__(self, host: str, folder: Path | None = None, port: int = PORT, companion: Path | None = None):
        self.host, self.folder, self.port = host, folder or body_folder(), port
        self.companion = companion            # where the shared quiet switch lives; quiet means her body makes no sound
        self.token = secrets.token_urlsafe(24)
        self.server: ThreadingHTTPServer | None = None
        self.seen: dict[str, dict] = {}         # session -> what her last turn there said about it (id, lock, who answered)

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
                    self.note(session, line)
                    write(line)
        except urllib.error.HTTPError as exc:
            write(_event("turn.error", {"error": f"mira-api answered {exc.code}", "status": "http"}))
        except (OSError, ValueError) as exc:
            logger.warning("relay: Mira's backend didn't answer (%s)", exc)
            write(_event("turn.error", {"error": "Mira's backend didn't answer", "status": "unreachable"}))

    def note(self, session: str, line: bytes) -> None:
        """Her session's id and lock, from each turn.final passing through, so her body's brain picker can pin it."""
        if not line.startswith(b"data:") or b"turn.final" not in line:
            return
        try:
            final = json.loads(line[5:])
        except ValueError:
            return
        if final.get("type") != "turn.final":
            return
        about = final.get("session") or {}
        self.seen[session] = {"id": about.get("sessionId"), "locked": about.get("lockedProvider"),
                              "answeredBy": final.get("answeredBy") or final.get("provider")}

    def brains(self) -> dict:
        """Mira's providers as her router has them on debhvk, and what each of her body's sessions is locked to."""
        base, token = backend._config()
        if not token:
            return {"error": "ARGUS has no MIRA_AUTH_TOKEN on this machine"}
        request = urllib.request.Request(f"{base.rstrip('/')}/v1/mira/providers/health",
                                         headers={"Authorization": f"Bearer {token}", "X-Jarvis-Client": "desktop"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                health = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("relay: Mira's providers didn't answer (%s)", exc)
            return {"error": "Mira's backend didn't answer"}
        providers = {name: {"ok": info.get("ok"), "down": bool(info.get("down"))}
                     for name, info in (health.get("providers") or {}).items()}
        return {"providers": providers, "sessions": self.seen}

    def pin(self, session: str, provider: str) -> dict:
        """Lock one of her sessions to a provider (mira-api's own escape hatch). The main session is the one Mira Desktop
        and her Voice Interface share, so a pin there is a pin for her everywhere."""
        known = self.seen.get(session) or {}
        if not known.get("id"):
            return {"error": "talk to her once first: ARGUS learns which session is hers from her first answer"}
        base, token = backend._config()
        if not token:
            return {"error": "ARGUS has no MIRA_AUTH_TOKEN on this machine"}
        request = urllib.request.Request(
            f"{base.rstrip('/')}/v1/mira/session/{known['id']}/provider",
            data=json.dumps({"provider": provider}).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Jarvis-Client": "desktop"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return {"error": f"mira-api answered {exc.code}"}
        except (OSError, ValueError):
            return {"error": "Mira's backend didn't answer"}
        known["locked"] = provider
        return {"locked": provider}

    def describe(self, image: str) -> str | None:
        """What a frame of HavoK's screen shows, from MIRA's vision (Claude, through mira-api). Her body's glance becomes
        words she then answers herself."""
        base, token = backend._config()
        if not token:
            return None
        request = urllib.request.Request(
            f"{base.rstrip('/')}/v1/mira/camera/analyze",
            data=json.dumps({"imageBase64": image, "mimeType": "image/jpeg", "prompt": SEE_PROMPT}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Jarvis-Client": "desktop"})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                seen = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("relay: Mira's vision didn't answer (%s)", exc)
            return None
        return (seen.get("content") or "").strip() or None

    def glance(self, text: str, image: str, max_tokens: int, write) -> None:
        seen = self.describe(image)
        if not seen:
            write(_event("turn.error", {"error": "Mira's vision didn't answer", "status": "unseen"}))
            return
        self.stream(f"(Your body on {self.host} just glanced at HavoK's screen. What it shows: {seen})\n\n{text}",
                    "body", max_tokens, write)

    def speak(self, text: str) -> tuple[int, bytes, str]:
        """Her voice for her body: mira-api's TTS in the voice "mira" (ElevenLabs, Edge behind it). Asked as a
        notification, so her body never spends the credits kept for conversation. Never while ARGUS is quiet."""
        if self.companion is not None and (self.companion / "quiet").exists():
            return 423, b'{"error":"quiet: her body makes no sound right now"}', "application/json"
        base, token = backend._config()
        if not token:
            return 503, b'{"error":"ARGUS has no MIRA_AUTH_TOKEN on this machine"}', "application/json"
        request = urllib.request.Request(
            f"{base.rstrip('/')}/v1/tts", data=json.dumps({"text": text, "voice": "mira", "purpose": "notification"}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                sound = response.read()
        except urllib.error.HTTPError as exc:
            return 502, json.dumps({"error": f"mira-api's voice answered {exc.code}"}).encode(), "application/json"
        except OSError:
            return 502, b'{"error":"Mira\'s voice didn\'t answer"}', "application/json"
        return 200, *as_wav(sound)

    def serve(self) -> ThreadingHTTPServer:
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def answer(self, body: dict) -> None:
                data = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def allowed(self) -> bool:
                if compare_digest(self.headers.get(HEADER, ""), relay.token):
                    return True
                self.send_error(403)
                return False

            def sound(self, status: int, data: bytes, kind: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path != "/brains":
                    self.send_error(404)
                elif self.allowed():
                    self.answer(relay.brains())

            def do_POST(self):
                if self.path not in ("/turn", "/brain", "/speak", "/see"):
                    self.send_error(404)
                    return
                if not self.allowed():
                    return
                if self.path == "/speak":
                    try:
                        text = str(json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))["text"]).strip()
                    except (KeyError, TypeError, ValueError):
                        self.send_error(400)
                        return
                    if not text:
                        self.send_error(400)
                        return
                    self.sound(*relay.speak(text[:2000]))
                    return
                if self.path == "/brain":
                    try:
                        ask = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                        session, provider = str(ask.get("session", "main")), str(ask["provider"]).strip()
                    except (KeyError, TypeError, ValueError):
                        self.send_error(400)
                        return
                    if session not in SESSIONS or not provider:
                        self.send_error(400)
                        return
                    self.answer(relay.pin(session, provider))
                    return
                try:
                    ask = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    text, session = str(ask["text"]).strip(), str(ask.get("session", "main"))
                    max_tokens = int(ask.get("max_tokens", 1500))
                    image = str(ask["image"]) if self.path == "/see" else None
                except (KeyError, TypeError, ValueError):
                    self.send_error(400)
                    return
                if not text or session not in SESSIONS or (image is not None and not 0 < len(image) <= 8 * 1024 * 1024):
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
                    if image is not None:
                        relay.glance(text, image, max_tokens, write)
                    else:
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


def as_wav(sound: bytes) -> tuple[bytes, str]:
    """Her voice comes as MP3. Where ffmpeg is (laphvk), it goes back as 24 kHz mono 16-bit WAV, which every body plays;
    otherwise as it came (Windows decodes MP3 itself)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or sound[:4] == b"RIFF":
        return sound, "audio/wav" if sound[:4] == b"RIFF" else "audio/mpeg"
    try:
        done = subprocess.run([ffmpeg, "-loglevel", "error", "-i", "pipe:0", "-f", "wav", "-ar", "24000", "-ac", "1",
                               "-acodec", "pcm_s16le", "pipe:1"], input=sound, capture_output=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError):
        return sound, "audio/mpeg"
    return done.stdout, "audio/wav"


HANDS_PORT = 8774


def hands(what: str, call: dict | None = None, folder: Path | None = None, timeout: float = 120) -> dict | list:
    """MIRA's MCP using her body's hands here: ``kit`` (her tools, in MCP's shape), ``do`` (one tool call) or ``answer``
    (HavoK's own yes or no to a call her body asked first about, passed on by MIRA). Reached over
    SSH as ``argus companion hands kit|do <base64 json>``; the answer is JSON for her MCP to read."""
    try:
        door = json.loads(((folder or body_folder()) / "argus.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"error": "ARGUS isn't housing her body on this machine right now"}
    path, data = ("/kit", None) if what == "kit" else (f"/{what}", json.dumps(call or {}).encode("utf-8"))
    request = urllib.request.Request(f"http://127.0.0.1:{HANDS_PORT}{path}", data=data,
                                     headers={HEADER: str(door.get("token", "")), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"error": f"her body answered {exc.code}"}
    except (OSError, ValueError):
        return {"error": "her body isn't up on this machine"}


def start(host: str, companion: Path | None = None) -> Relay | None:
    relay = Relay(host, companion=companion)
    try:
        relay.serve()
    except OSError:
        logger.warning("relay: port %s taken; her body can't reach MIRA through ARGUS this run", PORT)
        return None
    return relay
