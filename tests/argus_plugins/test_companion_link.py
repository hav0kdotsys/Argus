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
