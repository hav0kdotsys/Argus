"""argus-companion's link between Mira's bodies, her ears, and moments that never hold up Hannah's clicks."""

from __future__ import annotations

import importlib.util
import json
import math
import random
import sys
import threading
import time
from array import array
from pathlib import Path

_PKG = Path(__file__).resolve().parents[2] / "argus" / "plugins" / "argus-companion"


def _mod(name: str):
    spec = importlib.util.spec_from_file_location("argus_companion_l", _PKG / "__init__.py",
                                                  submodule_search_locations=[str(_PKG)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return importlib.import_module(f"argus_companion_l.{name}")


def test_windows_track_text_reads_as_playing_or_not():
    link = _mod("link")
    assert link.parse_track("Noah Kahan - Draw You Out [Playing]") == {"playing": True, "artist": "Noah Kahan",
                                                                       "title": "Draw You Out"}
    assert link.parse_track("Lo-fi beats [Paused]")["playing"] is False
    assert link.parse_track("")["playing"] is False


def test_a_switch_changed_on_one_machine_wins_and_a_machine_coming_up_never_overrides_it(tmp_path):
    link = _mod("link")
    here, there = tmp_path / "here", tmp_path / "there"
    here.mkdir()
    there.mkdir()
    a, b = link.Switches(here), link.Switches(there)
    a.report(now=100.0)
    b.report(now=100.0)
    (there / "quiet").write_text("quiet", encoding="utf-8")         # Hannah quiets her on the other machine
    theirs = b.report(now=200.0)
    assert theirs["quiet"] == {"v": True, "at": 200.0}
    assert a.take(theirs) == ["quiet"] and (here / "quiet").exists()
    # the first sight of a value is "changed at 0": it never beats a real change
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    newcomer = link.Switches(fresh).report(now=300.0)
    assert a.take(newcomer) == [] and (here / "quiet").exists()


def test_a_move_for_the_other_body_lands_there_once(tmp_path):
    link = _mod("link")
    here, there = tmp_path / "here", tmp_path / "there"
    here.mkdir()
    there.mkdir()
    link.send_there(here, "hop_in")
    sender, receiver = link.Link(here, "laphvk"), link.Link(there, "winhvk")
    report = sender.report()
    receiver.hear(report)
    first = json.loads((there / "body.json").read_text(encoding="utf-8"))
    assert first["do"] == "hop_in"
    receiver.hear(report)                                             # re-sent before the echo: not done twice
    assert json.loads((there / "body.json").read_text(encoding="utf-8"))["id"] == first["id"]
    sender.delivered({"got": sorted(receiver.done_moves)})
    assert not (here / "link-out.json").exists()


def test_their_beat_arrives_on_this_machines_clock(tmp_path):
    link = _mod("link")
    receiver = link.Link(tmp_path, "winhvk")
    receiver.hear({"host": "laphvk", "music": {"playing": True, "bpm": 120.0, "beat_at": 1000.0}}, shift=-2.5)
    heard = json.loads((tmp_path / "link.json").read_text(encoding="utf-8"))
    assert heard["peer"] == "laphvk" and heard["music"]["beat_at"] == 997.5


def _clicks(bpm: float, seconds: float, rate: int) -> array:
    random.seed(3)
    period, out = 60 / bpm, array("h")
    for i in range(int(rate * seconds)):
        t = i / rate
        v = random.gauss(0, 800) + 12000 * math.exp(-(t % period) * 40) * math.sin(2 * math.pi * 60 * t)
        out.append(max(-32767, min(32767, int(v))))
    return out


def test_her_ears_find_the_tempo_and_where_the_beat_fell():
    ears = _mod("ears")
    frames, _ = ears.onset_frames(_clicks(128, 8.0, ears.RATE), (0.0, 0.0, 0.0))
    bpm, ago, _strength = ears.tempo(frames[-800:])
    assert abs(bpm - 128) < 2
    expect = 8.0 % (60 / 128)
    assert min(abs(ago - expect), 60 / 128 - abs(ago - expect)) < 0.03
    silent, _ = ears.onset_frames(array("h", [0] * ears.RATE * 4), (0.0, 0.0, 0.0))
    assert ears.tempo(silent)[0] == 0.0


def test_a_tempo_heard_twice_locks_and_a_long_silence_lets_go():
    ears = _mod("ears")
    lock = ears.BeatLock()
    lock.take(120.0, 0.1, 50.0)
    assert lock.bpm == 0.0
    lock.take(121.0, 0.1, 50.5)
    assert abs(lock.bpm - 121.0) < 0.01
    for _ in range(8):
        lock.take(0.0, 0.0, 51.0)
    assert lock.bpm == 0.0


def test_a_slow_mind_never_blocks_the_ticker_and_only_one_moment_thinks_at_a_time(tmp_path, monkeypatch):
    ticker = _mod("ticker")
    release = threading.Event()
    calls = []

    def slow(folder, kind, *args, **kwargs):
        calls.append(kind)
        release.wait(5)

    monkeypatch.setattr(ticker, "moment_now", slow)
    started = time.time()
    assert ticker.moment_soon(tmp_path, "pat", 0) is True
    assert ticker.moment_soon(tmp_path, "popin", 0) is False      # still thinking about the pat
    assert time.time() - started < 1.0
    release.set()
    for _ in range(50):
        if not ticker._thinking.locked():
            break
        time.sleep(0.05)
    assert calls == ["pat"] and ticker.moment_soon(tmp_path, "water", 0) is True


def test_her_words_come_from_her_own_backend_in_her_companion_session(monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    backend = _mod("backend")
    seen = {}

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):
            seen.update(path=self.path, auth=self.headers.get("Authorization"), client=self.headers.get("X-Jarvis-Client"),
                        body=json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            data = json.dumps({"status": "success", "answeredBy": "groqcloud",
                               "choice": {"message": {"content": "<think>hm</think>Drink something, gremlin."}}})
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data.encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(backend, "_config", lambda: (f"http://127.0.0.1:{server.server_port}", "tok"))
        assert backend.call("a moment") == ("Drink something, gremlin.", "groqcloud")
        assert seen["path"] == "/v1/mira/call" and seen["auth"] == "Bearer tok" and seen["client"] == "api"
        assert seen["body"]["userId"] == "companion" and seen["body"]["mode"] == "agent"
        monkeypatch.setattr(backend, "_config", lambda: ("http://127.0.0.1:9", "tok"))
        assert backend.call("a moment") == ("", "")                    # her backend down: she just doesn't speak
    finally:
        server.shutdown()


def test_the_move_arrow_lands_on_the_screen_squares_and_clears(tmp_path):
    coach = _mod("chess_coach")
    board = coach.Board("winhvk", "Play vs Computer - Chess.com", (100, 50, 1100, 850))
    # a screenshot at twice the window's size (physical vs logical pixels): the squares map back onto the screen
    assert coach.on_screen(board, (2000, 1600), (200, 100, 1000, 900)) == (200, 100, 600, 500)
    coach.arrow(tmp_path, {"box": (200, 100, 600, 500), "from": "e2", "to": "e4", "white_bottom": True})
    first = json.loads((tmp_path / "arrow.json").read_text(encoding="utf-8"))
    assert first["from"] == "e2" and first["to"] == "e4" and first["at"] > 0
    coach.set_coach(tmp_path, False)                                   # coaching off: the arrow goes
    assert json.loads((tmp_path / "arrow.json").read_text(encoding="utf-8"))["at"] == 0


def test_her_body_reaches_her_backend_only_through_the_relay_and_in_the_right_session(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import urllib.error
    import urllib.request

    relay = _mod("relay")
    backend = _mod("backend")
    seen = []

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):
            seen.append((self.path, self.headers.get("Authorization"), self.headers.get("X-Jarvis-Client"),
                         json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for kind, data in (("turn.started", {}), ("turn.final", {"choice": {"message": {"content": "Hi."}}})):
                self.wfile.write(f"event: {kind}\ndata: {json.dumps({'type': kind, **data})}\n\n".encode())

    mira = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=mira.serve_forever, daemon=True).start()
    monkeypatch.setattr(backend, "_config", lambda: (f"http://127.0.0.1:{mira.server_port}", "tok"))
    body = relay.Relay("winhvk", tmp_path, port=0)
    server = body.serve()
    try:
        told = json.loads((tmp_path / "argus.json").read_text(encoding="utf-8"))
        assert told["token"] == body.token and told["host"] == "winhvk"
        url = f"http://127.0.0.1:{server.server_port}/turn"

        def turn(session, token=body.token):
            request = urllib.request.Request(url, data=json.dumps({"text": "dance", "session": session}).encode(),
                                             headers={relay.HEADER: token})
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.read().decode()

        out = turn("main")
        assert "event: turn.final" in out and '"Hi."' in out
        path, auth, client, sent = seen[-1]
        assert path == "/v1/mira/call/stream" and auth == "Bearer tok" and client == "desktop"
        assert "userId" not in sent and sent["messages"][0]["content"].startswith("dance")   # her main session
        assert "on winhvk" in sent["messages"][0]["content"]
        turn("body")
        assert seen[-1][3]["userId"] == "body"                                             # the side session
        turn("main")                                    # what she said there reaches her main session, once
        assert seen[-1][3]["messages"][0]["content"].startswith('(Lately your body on winhvk said, on its own: "Hi.")')
        turn("main")
        assert seen[-1][3]["messages"][0]["content"].startswith("dance")
        try:
            turn("main", token="wrong")
            raise AssertionError("a request without her token got through")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown()
        mira.shutdown()


def test_mira_reaches_her_bodys_hands_with_the_token_argus_made(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    relay = _mod("relay")
    calls = []

    class Body(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def _answer(self, data, code=200):
            out = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def do_GET(self):
            self._answer([{"name": "animate"}] if self.headers.get(relay.HEADER) == "t0k" else {"error": "forbidden"},
                         200 if self.headers.get(relay.HEADER) == "t0k" else 403)

        def do_POST(self):
            calls.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self._answer({"result": "Dancing." if self.path == "/do" else "Opened Spotify."})

    body = ThreadingHTTPServer(("127.0.0.1", 0), Body)
    threading.Thread(target=body.serve_forever, daemon=True).start()
    monkeypatch.setattr(relay, "HANDS_PORT", body.server_port)
    try:
        assert relay.hands("kit", folder=tmp_path) == {"error": "ARGUS isn't housing her body on this machine right now"}
        (tmp_path / "argus.json").write_text(json.dumps({"port": 1, "token": "t0k"}), encoding="utf-8")
        assert relay.hands("kit", folder=tmp_path) == [{"name": "animate"}]
        assert relay.hands("do", {"tool": "animate", "args": {"name": "dance"}}, folder=tmp_path) == {"result": "Dancing."}
        assert relay.hands("answer", {"args": {"text": "yes"}}, folder=tmp_path) == {"result": "Opened Spotify."}
        assert calls == [("/do", {"tool": "animate", "args": {"name": "dance"}}), ("/answer", {"args": {"text": "yes"}})]
        (tmp_path / "argus.json").write_text(json.dumps({"port": 1, "token": "stale"}), encoding="utf-8")
        assert relay.hands("kit", folder=tmp_path) == {"error": "her body answered 403"}
    finally:
        body.shutdown()


def test_her_bodys_brain_picker_pins_the_session_her_last_answer_came_from(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import urllib.request

    relay = _mod("relay")
    backend = _mod("backend")
    pinned = []

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def reply(self, body):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.reply({"providers": {"claude-code": {"ok": True, "down": False}, "groqcloud": {"ok": False, "down": True}}})

        def do_POST(self):
            sent = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path.endswith("/provider"):
                pinned.append((self.path, sent["provider"]))
                self.reply({"status": "ok"})
                return
            self.send_response(200)
            self.end_headers()
            final = {"type": "turn.final", "answeredBy": "claude-code",
                     "session": {"sessionId": "s1", "lockedProvider": "claude-code"}, "choice": {"message": {"content": "Hi."}}}
            self.wfile.write(f"event: turn.final\ndata: {json.dumps(final)}\n\n".encode())

    mira = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=mira.serve_forever, daemon=True).start()
    monkeypatch.setattr(backend, "_config", lambda: (f"http://127.0.0.1:{mira.server_port}", "tok"))
    body = relay.Relay("laphvk", tmp_path, port=0)
    server = body.serve()
    base = f"http://127.0.0.1:{server.server_port}"

    def call(path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(base + path, data=data, headers={relay.HEADER: body.token})
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read().decode()

    try:
        assert "error" in json.loads(call("/brain", {"session": "main", "provider": "groqcloud"}))   # no session known yet
        assert not pinned
        call("/turn", {"text": "hi", "session": "main"})
        brains = json.loads(call("/brains"))
        assert set(brains["providers"]) == {"claude-code", "groqcloud"} and brains["providers"]["groqcloud"]["down"]
        assert brains["sessions"]["main"] == {"id": "s1", "locked": "claude-code", "answeredBy": "claude-code"}
        assert json.loads(call("/brain", {"session": "main", "provider": "groqcloud"})) == {"locked": "groqcloud"}
        assert pinned == [("/v1/mira/session/s1/provider", "groqcloud")]
    finally:
        server.shutdown()
        mira.shutdown()


def test_her_body_speaks_in_her_own_voice_and_never_while_argus_is_quiet(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import urllib.error
    import urllib.request

    relay = _mod("relay")
    backend = _mod("backend")
    asked = []

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):
            asked.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            data = b"RIFF\x00\x00\x00\x00WAVEfmt "
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    mira = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=mira.serve_forever, daemon=True).start()
    monkeypatch.setattr(backend, "_config", lambda: (f"http://127.0.0.1:{mira.server_port}", "tok"))
    companion = tmp_path / "companion"
    companion.mkdir()
    body = relay.Relay("laphvk", tmp_path, port=0, companion=companion)
    server = body.serve()

    def speak():
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/speak", data=json.dumps({"text": "hi"}).encode(),
                                         headers={relay.HEADER: body.token})
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.headers["Content-Type"], response.read()

    try:
        kind, sound = speak()
        assert kind == "audio/wav" and sound.startswith(b"RIFF")
        assert asked == [("/v1/tts", {"text": "hi", "voice": "mira", "purpose": "notification"})]
        (companion / "quiet").write_text("quiet", encoding="utf-8")
        try:
            speak()
            raise AssertionError("she spoke while ARGUS was quiet")
        except urllib.error.HTTPError as exc:
            assert exc.code == 423
        assert len(asked) == 1
    finally:
        server.shutdown()
        mira.shutdown()


def test_her_bodys_glance_is_seen_by_her_vision_and_answered_in_her_side_session(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import urllib.request

    relay = _mod("relay")
    backend = _mod("backend")
    asked = []

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):
            sent = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            asked.append((self.path, sent))
            self.send_response(200)
            self.end_headers()
            if self.path.endswith("/camera/analyze"):
                self.wfile.write(json.dumps({"status": "success", "content": "Factorio, a burning base."}).encode())
                return
            final = {"type": "turn.final", "choice": {"message": {"content": "Your base is on fire."}}}
            self.wfile.write(f"event: turn.final\ndata: {json.dumps(final)}\n\n".encode())

    mira = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=mira.serve_forever, daemon=True).start()
    monkeypatch.setattr(backend, "_config", lambda: (f"http://127.0.0.1:{mira.server_port}", "tok"))
    body = relay.Relay("winhvk", tmp_path, port=0)
    server = body.serve()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/see",
                                         data=json.dumps({"text": "React in one line.", "image": "/9j/AAAA"}).encode(),
                                         headers={relay.HEADER: body.token})
        with urllib.request.urlopen(request, timeout=10) as response:
            out = response.read().decode()
        assert "Your base is on fire." in out
        (look, frame), (turn, said) = asked
        assert look == "/v1/mira/camera/analyze" and frame["imageBase64"] == "/9j/AAAA"
        assert turn == "/v1/mira/call/stream" and said["userId"] == "body"
        assert "Factorio, a burning base." in said["messages"][0]["content"]
        assert said["messages"][0]["content"].count("React in one line.") == 1
    finally:
        server.shutdown()
        mira.shutdown()


def test_music_on_her_other_pc_has_her_body_here_dance_and_her_other_body_arriving_glitches_her(tmp_path):
    bridge_mod = _mod("bridge")
    did = []
    up = [True]

    def act(tool, args):
        if not up[0]:
            return {"error": "her body isn't up on this machine"}
        did.append(args["name"])
        return {"result": "ok"}

    bridge = bridge_mod.Bridge(tmp_path, act=act)

    def hear(at, playing):
        (tmp_path / "link.json").write_text(json.dumps({"peer": "winhvk", "at": at, "music": {"playing": playing}}), encoding="utf-8")

    hear(1000, True)
    up[0] = False
    assert bridge.tick(False, now=1001) == []             # her body isn't up yet: nothing changes, it tries again
    up[0] = True
    assert bridge.tick(False, now=1002) == ["dance"]
    assert bridge.tick(False, now=1003) == []             # still dancing: not asked again
    assert bridge.tick(True, now=1004) == ["stop_dancing"]   # music here too: her own ears take it from here
    hear(1005, False)
    assert bridge.tick(False, now=1006) == []
    hear(1300, False)                                     # her other body was gone five minutes, and is back
    assert bridge.tick(False, now=1301) == ["glitch"]
    assert did == ["dance", "stop_dancing", "glitch"]
