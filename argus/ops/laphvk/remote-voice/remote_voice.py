#!/usr/bin/env python3
"""remote-voice: Mira's voice from her winhvk body, on laphvk's speakers (HavoK, 8 Nov 2026: "only Mira's voice").

    winhvk  her body (speaker menu: "laphvk's speakers") -> POST 127.0.0.1:18776/play (a WAV per line)
      | ssh -R over the LAN, opened from here (laphvk's firewall drops inbound; remote-mic goes the same way)
    laphvk  this player on 127.0.0.1:18776 -> paplay, the default output

Lines play one after another; /stop (she was talked over, or cut) drops what's queued and stops the one playing. While
ARGUS's quiet flag is up here, a line is refused (423) and her body plays it on winhvk instead. Nothing is kept: each
line is a temporary file in the runtime folder, gone once played.
"""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WINHVK = os.environ.get("REMOTE_VOICE_HOST", "HavoK@192.168.1.64")
NAME = os.environ.get("REMOTE_VOICE_NAME", "laphvk")
PORT = 18776
LARGEST = 20 * 1024 * 1024
QUIET = Path.home() / ".argus" / "companion" / "quiet"
RUNTIME = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()

stopping = threading.Event()
lines: queue.Queue[bytes] = queue.Queue()
playing_lock = threading.Lock()
playing: subprocess.Popen | None = None


def log(msg: str) -> None:
    print(f"remote-voice: {msg}", flush=True)


def stop_all() -> None:
    global playing
    while True:
        try:
            lines.get_nowait()
        except queue.Empty:
            break
    with playing_lock:
        if playing is not None and playing.poll() is None:
            playing.kill()


def player() -> None:
    global playing
    while not stopping.is_set():
        try:
            wav = lines.get(timeout=1)
        except queue.Empty:
            continue
        fd, path = tempfile.mkstemp(prefix="mira-voice-", suffix=".wav", dir=RUNTIME)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(wav)
            with playing_lock:
                playing = subprocess.Popen(["paplay", "--client-name=mira-remote-voice", path],
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            _, err = playing.communicate()
            if playing.returncode not in (0, -signal.SIGKILL) and err:
                log(f"paplay: {err.decode(errors='replace').strip()[:160]}")
        except OSError as exc:
            log(f"couldn't play a line: {exc}")
        finally:
            Path(path).unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:          # one line per event is ours, not per request
        pass

    def reply(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/who":
            self.reply(200, {"host": NAME, "quiet": QUIET.exists()})
        else:
            self.reply(404, {"error": "no such thing"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if self.path == "/stop":
            stop_all()
            self.reply(200, {"result": "stopped"})
            return
        if self.path != "/play":
            self.reply(404, {"error": "no such thing"})
            return
        if length <= 44 or length > LARGEST:
            self.reply(413, {"error": "not a line"})
            return
        wav = self.rfile.read(length)
        if wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
            self.reply(415, {"error": "WAV only"})
            return
        if QUIET.exists():
            self.reply(423, {"error": "laphvk is quiet"})
            return
        lines.put(wav)
        self.reply(200, {"result": "queued"})


def tunnel() -> None:
    """Keeps 127.0.0.1:18776 on winhvk pointed here. A session that held a while is reopened at once; one that never
    came up backs off to a minute, so an offline winhvk costs nothing (as remote-mic does)."""
    backoff = 2
    while not stopping.is_set():
        started = threading.Event()
        ssh = subprocess.Popen(["ssh", "-N", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "ExitOnForwardFailure=yes",
                                "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3",
                                "-R", f"127.0.0.1:{PORT}:127.0.0.1:{PORT}", WINHVK],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        timer = threading.Timer(10, started.set)
        timer.start()
        _, err = ssh.communicate()
        timer.cancel()
        held = started.is_set()
        last = (err or b"").decode(errors="replace").strip().splitlines()
        last = [line for line in last if "post-quantum" not in line and "store now" not in line and "upgraded" not in line]
        log(("tunnel to winhvk closed" if held else "winhvk unavailable") + (f": {last[-1][:160]}" if last else ""))
        backoff = 2 if held else min(backoff * 2, 60)
        stopping.wait(backoff)


def on_term(*_args) -> None:
    stopping.set()
    stop_all()
    raise SystemExit(0)


def main() -> int:
    signal.signal(signal.SIGTERM, on_term)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=player, name="player", daemon=True).start()
    threading.Thread(target=tunnel, name="tunnel", daemon=True).start()
    log(f"listening on 127.0.0.1:{PORT} as {NAME}'s speakers")
    try:
        server.serve_forever()
    finally:
        stopping.set()
        stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
