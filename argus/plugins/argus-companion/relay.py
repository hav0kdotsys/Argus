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
import time
import urllib.error
import urllib.request
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import backend

logger = logging.getLogger(__name__)

PORT = 8773
HEADER = "X-Argus-Token"
SESSIONS = {"main": None, "body": "body", "game": "game"}      # session -> mira-api userId (the scope modifier)
# Her body's game looks (playing a game until stopped, live commentary) are many a minute, so they go to Gemini Flash
# through mira-api, not to her main brain (HavoK, 8 Nov): pinned per turn, in a session of their own, no tools.
GAME_PROVIDER = "googleai"
TURN_TIMEOUT = 600
TIMINGS = "turns.jsonl"          # one line per turn her body asked for, in the companion folder: how long it took
TIMINGS_KEEP = 3000
DIGEST_KEEP, DIGEST_HOURS, DIGEST_LINE = 6, 3, 200     # what her side session said lately, carried into her main one


def body_folder() -> Path:
    """Where Mira's body keeps its things: %LOCALAPPDATA%\\Mira, or ~/.config/Mira."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Mira"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "Mira"


def where_said(host: str, session: str) -> str:
    if session == "main":
        return f"\n\n(HavoK said this to your body on {host}.)"
    return f"\n\n(From your body on {host}.)"


def request_for(text: str, session: str, host: str, max_tokens: int, base: str, token: str,
                history: str = "", images: list | None = None, history_reply: str = "") -> urllib.request.Request:
    """history: what her session keeps of this turn instead of *text* (mira-api's ``historyText``), for a turn whose
    instructions would only weigh down every later turn. history_reply: what it keeps of her answer instead
    (``historyReply``), for work whose result lives elsewhere, like her body's words file; else her reply is kept whole."""
    body = {"messages": [{"role": "user", "content": text + where_said(host, session)}], "mode": "agent",
            "maxTokens": max_tokens, "temperature": 0.9}
    if history:
        # A generated turn: its words are instructions, not something to look up on the web, and it needs no tools.
        body["historyText"], body["trustedWeb"], body["tools"] = history, False, False
    if images:
        body["images"] = images
    if history_reply:
        body["historyReply"] = history_reply
    if SESSIONS[session]:
        body["userId"] = SESSIONS[session]
    if session == "game":
        body["provider"], body["mode"], body["tools"], body["trustedWeb"] = GAME_PROVIDER, "assistant", False, False
    return urllib.request.Request(
        f"{base.rstrip('/')}/v1/mira/call/stream", data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Accept": "text/event-stream", "X-Jarvis-Client": "desktop"})


def record(folder: Path, row: dict) -> None:
    """One turn's timing into the companion folder's turns.jsonl, kept to its last TIMINGS_KEEP lines."""
    path = folder / TIMINGS
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        if path.stat().st_size > TIMINGS_KEEP * 600:
            rows = path.read_text(encoding="utf-8").splitlines()[-TIMINGS_KEEP:]
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    except OSError:
        logger.debug("relay: couldn't record a turn's timing", exc_info=True)


def _event(kind: str, payload: dict) -> bytes:
    return f"event: {kind}\ndata: {json.dumps({'type': kind, **payload})}\n\n".encode()


class Relay:
    def __init__(self, host: str, folder: Path | None = None, port: int = PORT, companion: Path | None = None):
        self.host, self.folder, self.port = host, folder or body_folder(), port
        self.companion = companion            # where the shared quiet switch lives; quiet means her body makes no sound
        self.token = secrets.token_urlsafe(24)
        self.server: ThreadingHTTPServer | None = None
        self.seen: dict[str, dict] = {}         # session -> what her last turn there said about it (id, lock, who answered)
        self.lately: list[tuple[float, str]] = []   # (when, what she said) in her side session, not yet in her main one

    def announce(self) -> None:
        """argus.json in her body's folder: how it reaches this relay. HavoK-only on Linux."""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / "argus.json"
        temp = path.with_suffix(".tmp")
        door = {"port": self.port, "token": self.token, "host": self.host}
        if self.companion is not None:
            door["companion"] = str(self.companion)     # where her body reports what it sees (state.json)
        temp.write_text(json.dumps(door), encoding="utf-8")
        if sys.platform != "win32":
            temp.chmod(0o600)
        temp.replace(path)

    def stream(self, text: str, session: str, max_tokens: int, write, history: str = "", images: list | None = None,
               history_reply: str = "") -> None:
        base, token = backend._config()
        if not token:
            write(_event("turn.error", {"error": "ARGUS has no MIRA_AUTH_TOKEN on this machine", "status": "unconfigured"}))
            return
        if session == "main":
            text = self.digest() + text
        request = request_for(text, session, self.host, max_tokens, base, token, history, images, history_reply)
        started, first = time.monotonic(), None
        try:
            with urllib.request.urlopen(request, timeout=TURN_TIMEOUT) as response:
                for line in response:
                    if first is None and line.startswith(b"data:") and b"turn.delta" in line:
                        first = time.monotonic()
                    final = self.note(session, line)
                    if final is not None:
                        self.timed(session, "glance" if history else "turn", started, first, final)
                    write(line)
        except urllib.error.HTTPError as exc:
            write(_event("turn.error", {"error": f"mira-api answered {exc.code}", "status": "http"}))
        except (OSError, ValueError) as exc:
            logger.warning("relay: Mira's backend didn't answer (%s)", exc)
            write(_event("turn.error", {"error": "Mira's backend didn't answer", "status": "unreachable"}))

    def timed(self, session: str, kind: str, started: float, first: float | None, final: dict) -> None:
        """How long a turn took, end to end and to her first sentence, with mira-api's own breakdown (``latency.server``:
        session, memory, provider, first sentence) and who answered: what her latency and quota work is measured by."""
        if self.companion is None:
            return
        now = time.monotonic()
        server = (final.get("latency") or {}).get("server") or {}
        row = {"at": round(time.time()), "host": self.host, "session": session, "kind": kind,
               "ms": round((now - started) * 1000), "first_ms": round((first - started) * 1000) if first else None,
               "by": final.get("answeredBy") or final.get("provider"),
               "server": {k: v for k, v in server.items() if isinstance(v, (int, float))}}
        record(self.companion, row)

    def note(self, session: str, line: bytes) -> dict | None:
        """Her session's id and lock, from each turn.final passing through, so her body's brain picker can pin it. The
        turn.final itself, or None for any other line."""
        if not line.startswith(b"data:") or b"turn.final" not in line:
            return None
        try:
            final = json.loads(line[5:])
        except ValueError:
            return None
        if final.get("type") != "turn.final":
            return None
        about = final.get("session") or {}
        said = " ".join(str(((final.get("choice") or {}).get("message") or {}).get("content") or "").split())
        if session == "body" and 0 < len(said) <= DIGEST_LINE:      # longer is work (her words for MiraWords), not a moment
            self.lately = [*self.lately, (time.time(), said)][-DIGEST_KEEP:]
        self.seen[session] = {"id": about.get("sessionId"), "locked": about.get("lockedProvider"),
                              "answeredBy": final.get("answeredBy") or final.get("provider")}
        return final

    def digest(self) -> str:
        """What her body said on its own lately (its side session), once, at the top of HavoK's next words to her: the
        short digest that links the two sessions without filling her main history with every aside."""
        cutoff = time.time() - DIGEST_HOURS * 3600
        recent, self.lately = [said for at, said in self.lately if at >= cutoff], []
        if not recent:
            return ""
        return f"(Lately your body on {self.host} said, on its own: " + " / ".join(f'"{r}"' for r in recent) + ")\n\n"

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

    def glance(self, text: str, image: str, max_tokens: int, write) -> None:
        """Her body glanced at HavoK's screen: one turn in her side session with the picture itself attached, so she
        answers what she sees (it used to be described by a separate vision call first, ~150 a day). Her session keeps a
        short note; her reply (SAW and SAY) says what she saw."""
        self.stream(f"(Your body on {self.host} just glanced at HavoK's screen: the picture is attached. Leave out private "
                    f"details like passwords or message contents.)\n\n{text}",
                    "body", max_tokens, write, history=f"(Your body on {self.host} glanced at HavoK's screen.)",
                    images=[{"data": image, "mimeType": "image/jpeg"}])

    def game_look(self, text: str, images: list, max_tokens: int, write) -> None:
        """A look her body takes while it plays or comments on a game: the frames themselves to Gemini Flash in her game
        session, which keeps only a short note of each look."""
        self.stream(text, "game", max_tokens, write, history=f"(Your body on {self.host} looked at the game.)",
                    images=[{"data": image, "mimeType": "image/jpeg"} for image in images])

    def speak(self, text: str, kind: str = "replies") -> tuple[int, bytes, str]:
        """Her voice for her body: mira-api's TTS in the voice "mira" (ElevenLabs, Edge behind it). Asked as a
        notification, so her body never spends the credits kept for conversation. Never while ARGUS is quiet, and not
        for a kind of line HavoK has set to stay unspoken (204: her body shows it without a sound)."""
        if self.companion is not None and (self.companion / "quiet").exists():
            return 423, b'{"error":"quiet: her body makes no sound right now"}', "application/json"
        if self.companion is not None:
            from . import prefs
            if not prefs.speaks(self.companion, kind):
                return 204, b"", "application/json"
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

    def hear(self, wav: bytes, profile: str = "assistant") -> dict:
        """Her body's ears: what its mic heard (16 kHz mono WAV) goes to mira-api's Whisper, which tries Groq first and
        its own model underneath, so no speech model is downloaded to the PCs (HavoK, 8 Nov). What she hears isn't kept.
        profile "wake" checks a possible "Hey Mira" with debhvk's own model only: wake checks never go to a cloud API."""
        base, token = backend._config()
        if not token:
            return {"error": "ARGUS has no MIRA_AUTH_TOKEN on this machine"}
        boundary = "argus" + secrets.token_hex(12)
        head = "".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
                       for name, value in (("language", "en"), ("profile", "wake" if profile == "wake" else "assistant")))
        body = (head + f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="heard.wav"\r\n'
                       f"Content-Type: audio/wav\r\n\r\n").encode() + wav + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(f"{base.rstrip('/')}/v1/stt", data=body, headers={
            "Authorization": f"Bearer {token}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                heard = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return {"error": f"mira-api's ears answered {exc.code}"}
        except (OSError, ValueError):
            return {"error": "Mira's ears didn't answer"}
        return {"text": str(heard.get("text") or "")}

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
                if self.path in ("/hear", "/hear?profile=wake"):
                    if not self.allowed():
                        return
                    size = int(self.headers.get("Content-Length", "0"))
                    # 16 MB is over eight minutes of her 16 kHz mono, far past any one line.
                    if not 44 < size <= 16 * 1024 * 1024:
                        self.send_error(400)
                        return
                    self.answer(relay.hear(self.rfile.read(size), "wake" if self.path.endswith("=wake") else "assistant"))
                    return
                if self.path not in ("/turn", "/brain", "/speak", "/see"):
                    self.send_error(404)
                    return
                if not self.allowed():
                    return
                if self.path == "/speak":
                    try:
                        ask = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                        text, kind = str(ask["text"]).strip(), str(ask.get("kind") or "replies")
                    except (KeyError, TypeError, ValueError):
                        self.send_error(400)
                        return
                    if not text:
                        self.send_error(400)
                        return
                    self.sound(*relay.speak(text[:2000], kind))
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
                    # A game look can carry two frames (before and after), for Gemini to compare.
                    game = self.path == "/see" and ask.get("game") is True
                    frames = [image] + [str(extra) for extra in (ask.get("more") or [])[:1]] if game else []
                    # Her body's own work turns can ask her session to keep short notes instead of the whole exchange.
                    history = str(ask.get("history") or "").strip()[:2000]
                    history_reply = str(ask.get("history_reply") or "").strip()[:2000]
                except (KeyError, TypeError, ValueError):
                    self.send_error(400)
                    return
                if not text or session not in SESSIONS or any(not 0 < len(f) <= 8 * 1024 * 1024 for f in ([image] if image is not None else []) + frames):
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
                    if game:
                        relay.game_look(text, frames, max_tokens, write)
                    elif image is not None:
                        relay.glance(text, image, max_tokens, write)
                    else:
                        relay.stream(text, session, max_tokens, write, history=history, history_reply=history_reply)
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
    """MIRA's MCP using her body's hands here: ``kit`` (her tools, in MCP's shape), ``state`` (what's playing there),
    ``do`` (one tool call) or ``answer``
    (HavoK's own yes or no to a call her body asked first about, passed on by MIRA). Reached over
    SSH as ``argus companion hands kit|do <base64 json>``; the answer is JSON for her MCP to read."""
    try:
        door = json.loads(((folder or body_folder()) / "argus.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"error": "ARGUS isn't housing her body on this machine right now"}
    path, data = (f"/{what}", None) if what in ("kit", "state") else (f"/{what}", json.dumps(call or {}).encode("utf-8"))
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
