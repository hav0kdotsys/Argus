"""'Hey Mira' on winhvk, with HavoK's own wake model (hey_mira.onnx, trained on his voice for her laphvk voice).

Runs in its own small venv (openwakeword 0.4.0 and onnxruntime, as on laphvk), started and watched by her companion
(wake.py). It hears the default mic as 80 ms frames that exist only while they're scored; nothing is recorded or kept.

  * a score of TRUST or more, loud enough to be speech, wakes her body (POST /wake on her hands port);
  * a score between SHOW and TRUST is checked first: the last two seconds go through ARGUS's relay to debhvk's own
    Whisper in its wake profile (which never leaves debhvk), and wake her only if it heard her name.

Its mic: the input named in heymira\\mic.txt (winhvk: TONOR), else the default.

Her body still decides: her "Hey Mira" setting, a chat already open, her mute or quiet key all leave her asleep.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import struct
import sys
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

RATE, FRAME = 16000, 1280                    # 80 ms frames, openWakeWord's step
SHOW, TRUST = 0.5, 0.9                       # laphvk's thresholds (mira-agent voice.py)
MIN_LEVEL = 0.03                             # frame RMS in the last 1.2 s: below it, room noise (laphvk, 20 Oct)
LEVEL_FRAMES = 15                            # 1.2 s
KEEP_FRAMES = 25                             # 2 s kept for a check
COOLDOWN = 3.0
HANDS = "http://127.0.0.1:8774"
NAME = re.compile(r"\bm(?:i|ee|ie|y)rr?ah?\b", re.IGNORECASE)


def log(message: str) -> None:
    print(f"[wake] {message}", flush=True)


def pick_mic(sd, wanted: str):
    """The input whose name holds *wanted* (heymira\\mic.txt, e.g. TONOR), on Windows' MME API, which converts to 16 kHz
    for us; None (the default input) when there's no such file or no such mic."""
    if not wanted:
        return None
    apis = sd.query_hostapis()
    found = [(i, d) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0 and wanted.lower() in d["name"].lower()]
    found.sort(key=lambda pair: apis[pair[1]["hostapi"]]["name"] != "MME")
    return found[0][0] if found else None


def door(folder: Path) -> dict:
    return json.loads((folder / "argus.json").read_text(encoding="utf-8"))


def post(url: str, token: str, body: bytes, kind: str, timeout: float) -> dict:
    request = urllib.request.Request(url, data=body, headers={"X-Argus-Token": token, "Content-Type": kind})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b"{}")


def wav(pcm: bytes) -> bytes:
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def parent_alive(pid: int) -> bool:
    """On Windows a child outlives its parent; the companion's own process is watched so a restart leaves one listener."""
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
    if not handle:
        return False
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x102   # WAIT_TIMEOUT: still running
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--body", required=True, help="her body's data folder (argus.json)")
    parser.add_argument("--parent", type=int, default=0)
    args = parser.parse_args()

    import numpy as np
    import sounddevice as sd
    from openwakeword.model import Model

    model = Model(wakeword_model_paths=[args.model])
    folder = Path(args.body)
    frames: deque[bytes] = deque(maxlen=KEEP_FRAMES)
    levels: deque[float] = deque(maxlen=LEVEL_FRAMES)
    quiet_until = [0.0]
    checking = threading.Event()

    def wake(score: float, how: str) -> None:
        try:
            got = post(HANDS + "/wake", door(folder)["token"], b"{}", "application/json", 5)
            log(f"hey mira {score:.2f} ({how}): {got.get('result')}")
        except (OSError, ValueError, KeyError) as exc:
            log(f"hey mira {score:.2f} ({how}), but her body didn't answer ({exc})")

    def check(score: float, clip: bytes) -> None:
        try:
            d = door(folder)
            heard = post(f"http://127.0.0.1:{d['port']}/hear?profile=wake", d["token"], wav(clip), "audio/wav", 15)
            text = str(heard.get("text") or "")
            if NAME.search(text):
                wake(score, f"checked: {text!r}")
            else:
                log(f"hey mira {score:.2f} not confirmed (heard {text!r})")
        except (OSError, ValueError, KeyError) as exc:
            log(f"hey mira {score:.2f} couldn't be checked ({exc})")
        finally:
            checking.clear()

    choice = Path(args.model).with_name("mic.txt")
    wanted = choice.read_text(encoding="utf-8").strip() if choice.exists() else ""
    mic = pick_mic(sd, wanted)
    name = sd.query_devices(mic, "input")["name"] if mic is not None else sd.query_devices(kind="input")["name"]
    if wanted and mic is None:
        log(f"no mic called {wanted!r} here, so the default")
    log(f"listening on {name} with {Path(args.model).name}")
    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME, device=mic) as stream:
        last_parent_check = time.monotonic()
        while True:
            data, _overflow = stream.read(FRAME)
            pcm = bytes(data)
            samples = np.frombuffer(pcm, dtype=np.int16)
            frames.append(pcm)
            levels.append(float(np.sqrt(np.mean((samples.astype(np.float32) / 32768.0) ** 2))) if samples.size else 0.0)
            now = time.monotonic()
            if args.parent and now - last_parent_check > 5:
                last_parent_check = now
                if not parent_alive(args.parent):
                    log("her companion is gone, so this listener stops")
                    return 0
            score = max(model.predict(samples).values() or [0.0])
            if score < SHOW or now < quiet_until[0] or checking.is_set():
                continue
            if max(levels) < MIN_LEVEL:
                continue
            quiet_until[0] = now + COOLDOWN
            model.reset()
            if score >= TRUST:
                wake(float(score), "trusted")
            else:
                checking.set()
                threading.Thread(target=check, args=(float(score), b"".join(frames)), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
