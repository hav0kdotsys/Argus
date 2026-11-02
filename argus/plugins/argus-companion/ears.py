"""Her ears on laphvk: the beat of whatever is playing, so she dances on it.

While an MPRIS player is playing, the companion listens to the default output's monitor (``parec``, 8 kHz mono, a
few kB/s) and keeps a beat lock: the tempo from the autocorrelation of the sound's onsets over the last few seconds,
and when the last beat fell. ``beat.json`` ({"bpm", "beat_at", "at"}, beat_at in this machine's unix seconds) is what
her body nods to and what the link sends to her other body. Nothing is recorded or kept: each 10 ms of sound becomes
one loudness number, and only the last few seconds of those exist.

winhvk's body has the same ears in C# (MiraPet/Ears.cs, WASAPI loopback), writing the same ``beat.json``.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
import time
from array import array
from pathlib import Path

logger = logging.getLogger(__name__)

RATE = 8000
FPS = 100                     # onset frames per second (10 ms each)
HOP = RATE // FPS
WINDOW = 8.0                  # seconds of onsets a tempo is read from
SLOWEST, FASTEST = 70.0, 180.0
LATENCY = 0.06                # capture + pipe delay, taken off when the beat fell


_LOW = 1 - math.exp(-2 * math.pi * 150 / RATE)     # a one-pole low-pass at 150 Hz: the kick and the bass


def onset_frames(samples: array, state: tuple[float, float, float]) -> tuple[list[float], tuple[float, float, float]]:
    """10 ms loudness steps up (half-wave rectified log energy flux, the whole sound plus its low end, where the
    kick lives) for a run of 16-bit samples. ``state`` carries (level, low level, low-pass) between runs."""
    level, low_level, lp = state
    out = []
    for i in range(0, len(samples) - HOP + 1, HOP):
        energy = low = 0.0
        for v in samples[i:i + HOP]:
            lp += _LOW * (v - lp)
            energy += v * v
            low += lp * lp
        now, now_low = math.log1p(energy / HOP / 1e4), math.log1p(low / HOP / 1e4)
        out.append(max(0.0, now - level) + max(0.0, now_low - low_level))
        level, low_level = now, now_low
    return out, (level, low_level, lp)


def fold(bpm: float) -> float:
    while bpm >= FASTEST:
        bpm /= 2
    while bpm < SLOWEST:
        bpm *= 2
    return bpm


def tempo(onsets: list[float], fps: int = FPS) -> tuple[float, float, float]:
    """(bpm, seconds since the last beat at the end of ``onsets``, strength 0-1); bpm 0 when there's no pulse."""
    n = len(onsets)
    if n < fps * 3:
        return 0.0, 0.0, 0.0
    mean = sum(onsets) / n
    x = [v - mean for v in onsets]
    zero = sum(v * v for v in x)
    if zero <= 1e-9:
        return 0.0, 0.0, 0.0
    lo, hi = int(fps * 60 / FASTEST), int(fps * 60 / SLOWEST) + 1
    r = {lag: sum(x[i] * x[i - lag] for i in range(lag, n)) / zero for lag in range(lo, min(3 * hi + 3, n - 1))}
    scores = {}
    for lag in range(lo, hi + 1):
        # the beat's multiples line up too (bars, half bars): count them, so a pulse beats a lone echo
        pulse = r[lag] + 0.5 * r.get(2 * lag, 0.0) + 0.25 * r.get(3 * lag, 0.0)
        bpm = 60.0 * fps / lag
        scores[lag] = pulse * math.exp(-0.5 * (math.log2(bpm / 120.0) / 0.9) ** 2)   # a gentle lean toward ~120
    best = max(scores, key=scores.get)
    strength = scores[best]
    if strength < 0.1:
        return 0.0, 0.0, max(0.0, strength)
    left, right = scores.get(best - 1, scores[best]), scores.get(best + 1, scores[best])
    bend = left - 2 * scores[best] + right
    lag = best + (0.5 * (left - right) / bend if bend < 0 else 0.0)
    period = lag
    # phase: the offset whose comb of beats (stepping back from the end) collects the most onset
    whole = round(period)
    sums = []
    for offset in range(whole):
        total, k = 0.0, 0
        while True:
            i = n - 1 - offset - round(k * period)
            if i < 0:
                break
            total += onsets[i]
            k += 1
        sums.append(total)
    ago = max(range(whole), key=sums.__getitem__)
    return 60.0 * fps / period, ago / fps, min(1.0, strength)


class BeatLock:
    """A tempo has to be heard twice before she dances to it, and keeps its place through a bar or two of
    breakdown."""

    def __init__(self):
        self.bpm = 0.0
        self.beat_at = 0.0
        self._pending = 0.0
        self._misses = 0

    def take(self, bpm: float, ago: float, now: float) -> None:
        if bpm <= 0:
            self._misses += 1
            if self._misses >= 8:
                self.bpm = self._pending = 0.0
            return
        self._misses = 0
        bpm = fold(bpm)
        beat_at = now - ago - LATENCY
        if self.bpm and abs(bpm / self.bpm - 1) < 0.04:
            self.bpm = self.bpm * 0.8 + bpm * 0.2
            self.beat_at = beat_at
        elif self._pending and abs(bpm / self._pending - 1) < 0.04:
            self.bpm, self.beat_at, self._pending = bpm, beat_at, 0.0
        else:
            self._pending = bpm


def write(folder: Path, lock: BeatLock) -> None:
    tmp = folder / "beat.json.tmp"
    data = {"bpm": round(lock.bpm, 2), "beat_at": round(lock.beat_at, 3), "at": time.time()} if lock.bpm else {"at": 0}
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(folder / "beat.json")


def listen(folder: Path, playing) -> None:
    """Forever: while ``playing()`` says music's on, hear it and keep ``beat.json`` current."""
    parec = shutil.which("parec")
    if not parec:
        logger.info("companion ears: no parec here; she dances without the beat")
        return
    while True:
        if not playing():
            time.sleep(2)
            continue
        proc = subprocess.Popen([parec, "--device=@DEFAULT_MONITOR@", "--format=s16le", f"--rate={RATE}",
                                 "--channels=1", "--latency-msec=30", "--client-name=mira-ears"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            _hear(folder, proc, playing)
        finally:
            proc.kill()
            proc.wait()
            write(folder, BeatLock())


def _hear(folder: Path, proc: subprocess.Popen, playing) -> None:
    lock, frames, level = BeatLock(), [], (0.0, 0.0, 0.0)
    keep = int(WINDOW * FPS)
    next_read, next_check = time.time() + 0.5, time.time() + 2
    while True:
        chunk = proc.stdout.read(HOP * 2 * 10)          # 100 ms
        if not chunk:
            return
        samples = array("h")
        samples.frombytes(chunk[: len(chunk) // 2 * 2])
        new, level = onset_frames(samples, level)
        frames = (frames + new)[-keep:]
        now = time.time()
        if now >= next_read:
            next_read = now + 0.5
            bpm, ago, _strength = tempo(frames)
            lock.take(bpm, ago, now)
            write(folder, lock)
        if now >= next_check:
            next_check = now + 2
            if not playing():
                return
