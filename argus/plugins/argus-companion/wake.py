"""'Hey Mira' for her body on winhvk: her companion runs wake_listen.py with HavoK's own wake model and keeps it running.

Everything it needs lives in her body's folder, outside ARGUS's managed environment: ``heymira\\venv`` (openwakeword 0.4.0
and onnxruntime, as laphvk's voice uses) and ``heymira\\hey_mira.onnx``. Without them nothing starts and her body says
nothing about it. laphvk's own voice (mira-agent) hears "Hey Mira" there, so this is winhvk's only.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

RESTART_FIRST, RESTART_MOST = 5.0, 600.0


def paths(body: Path) -> tuple[Path, Path, Path]:
    home = body / "heymira"   # not "wake": Capri's own wake pack uses that folder
    python = home / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return home, python, home / "hey_mira.onnx"


def start(body: Path) -> threading.Thread | None:
    home, python, model = paths(body)
    if not (python.exists() and model.exists()):
        logger.info("wake: no wake listener here (%s)", home)
        return None
    thread = threading.Thread(target=_keep, args=(home, python, model, body), name="mira-wake", daemon=True)
    thread.start()
    return thread


def _keep(home: Path, python: Path, model: Path, body: Path) -> None:
    """Runs the listener; a crash comes back after a wait that doubles each time it fails quickly, up to ten minutes."""
    wait = RESTART_FIRST
    script = Path(__file__).with_name("wake_listen.py")
    flags = 0x08000000 if sys.platform == "win32" else 0        # CREATE_NO_WINDOW
    while True:
        started = time.monotonic()
        log = home / "wake.log"
        if log.exists() and log.stat().st_size > 1024 * 1024:
            log.replace(home / "wake.log.old")
        with open(log, "a", encoding="utf-8") as out:
            proc = subprocess.Popen([str(python), "-I", str(script), "--model", str(model), "--body", str(body),
                                     "--parent", str(os.getpid())], stdout=out, stderr=subprocess.STDOUT, creationflags=flags)
            code = proc.wait()
        lasted = time.monotonic() - started
        wait = RESTART_FIRST if lasted > 600 else min(wait * 2, RESTART_MOST)
        logger.warning("wake: listener exited %s after %.0f s; again in %.0f s", code, lasted, wait)
        time.sleep(wait)
