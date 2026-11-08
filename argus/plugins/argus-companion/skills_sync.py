"""Her body's skill mods into MIRA's own skill store (HavoK, 8 Nov 2026, port decision #4).

Her body lists the skill mods turned on in it as ``skills.json`` beside ``argus.json``. When that list changes, this
copies it to debhvk and runs ``~/argus/argus/ops/mod_skills.py <host> <file>`` there, which keeps each one as know-how in
MIRA's store, where she can use it from any device. Turned off here, it's moved aside there. A failed send is tried
again with a growing wait (one minute, doubling, up to an hour); nothing else in the companion waits on it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CHECK = 60.0
WAIT_MOST = 3600.0
REMOTE = "python3 ~/argus/argus/ops/mod_skills.py"


def send(listed: Path, host: str, folder: Path) -> tuple[bool, str]:
    """scp the list across, then run the store's script on it. On Windows ssh's Cloudflare proxy (cloudflared, its
    ProxyCommand) inherits ssh's stdio and keeps it open after ssh exits, so a pipe on stdin or stdout never ends (8 Nov):
    nothing goes on stdin, and what the script says goes to a file."""
    remote = f"/tmp/mira-skills-{host}.json"
    out = folder / "skills-send.out"
    opts = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
    try:
        with open(out, "wb") as said:
            copied = subprocess.run(["scp", "-q", *opts, str(listed), f"debhvk:{remote}"], stdin=subprocess.DEVNULL,
                                    stdout=said, stderr=subprocess.STDOUT, timeout=90, check=False)
            ran = copied.returncode == 0 and subprocess.run(["ssh", *opts, "debhvk", f"{REMOTE} {host} {remote}"],
                                                             stdin=subprocess.DEVNULL, stdout=said, stderr=subprocess.STDOUT,
                                                             timeout=90, check=False).returncode == 0
        return ran, out.read_text(encoding="utf-8", errors="replace").strip()[-300:]
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def start(body: Path, host: str, folder: Path) -> threading.Thread | None:
    if shutil.which("ssh") is None:
        logger.info("skills: no ssh here, so her skill mods stay on this PC")
        return None
    thread = threading.Thread(target=_keep, args=(body, host, folder), name="mira-skills", daemon=True)
    thread.start()
    return thread


def _keep(body: Path, host: str, folder: Path) -> None:
    sent_file = folder / "skills-sent.json"
    try:
        sent = json.loads(sent_file.read_text(encoding="utf-8")).get("hash")
    except (OSError, ValueError, AttributeError):
        sent = None
    wait, next_try = CHECK, 0.0
    while True:
        time.sleep(CHECK)
        try:
            data = (body / "skills.json").read_bytes()
        except OSError:
            continue                                  # no list yet: her body writes one in a real run
        digest = hashlib.sha256(data).hexdigest()
        if digest == sent or time.time() < next_try:
            continue
        ok, detail = send(body / "skills.json", host, folder)
        if ok:
            sent, wait, next_try = digest, CHECK, 0.0
            sent_file.write_text(json.dumps({"hash": digest, "at": time.time(), "result": detail}), encoding="utf-8")
            logger.info("skills: her skill mods are in MIRA's store (%s)", detail)
        else:
            wait = min(wait * 2, WAIT_MOST)
            next_try = time.time() + wait
            logger.warning("skills: couldn't send her skill mods to debhvk (%s); again in %.0f s", detail, wait)
