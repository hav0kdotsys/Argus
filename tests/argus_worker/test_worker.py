"""ARGUS's worker: its config reader and how it keeps HavoK's units in line with argus.yaml."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "argus" / "worker" / "argus_worker.py"


def _worker():
    spec = importlib.util.spec_from_file_location("argus_worker_t", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_argus_yaml_reads_as_written_and_anything_unclear_is_an_error_not_a_guess(tmp_path):
    worker = _worker()
    path = tmp_path / "argus.yaml"
    path.write_text("# laphvk\nhost: laphvk\nuser: havok\nbody:\n  enabled: true  # her body\n"
                    "devices:\n  - winhvk\n  - debhvk\n", encoding="utf-8")
    config = worker.load(path)
    assert config["host"] == "laphvk" and config["user"] == "havok" and config["body"] == {"enabled": True}
    assert config["companion"] == {"enabled": True} and config["devices"] == ["winhvk", "debhvk"]
    for bad in ("body:\n  enabled: maybe\n", "boddy:\n  enabled: true\n", "body: true\n", "user: a\nuser: b\n",
                "body:\n  enabled: true\n    x: 1\n", "host laphvk\n"):
        path.write_text(bad, encoding="utf-8")
        with pytest.raises(worker.ConfigError):
            worker.load(path)
    with pytest.raises(worker.ConfigError):
        worker.load(tmp_path / "missing.yaml")


def test_her_body_on_runs_it_and_stands_the_old_body_down_and_off_is_the_rollback(monkeypatch):
    worker = _worker()
    monkeypatch.setattr(worker.os, "geteuid", lambda: 0)
    running = {worker.COMPANION: "active", worker.BODY: "inactive", worker.OLD_BODY: "active"}
    calls = []

    def fake(command, **_):
        calls.append(command)
        assert command[:4] == ["systemctl", "--user", "-M", "havok@"]      # HavoK's own manager, from root
        verb, unit = command[4], command[-1]
        if verb == "show":
            return subprocess.CompletedProcess(command, 0, "loaded\n" if unit in running else "not-found\n", "")
        if verb == "is-active":
            return subprocess.CompletedProcess(command, 0, running[unit] + "\n", "")
        running[unit] = "active" if verb == "start" else "inactive"
        return subprocess.CompletedProcess(command, 0, "", "")

    on = {"host": "laphvk", "user": "havok", "body": {"enabled": True}, "companion": {"enabled": True}}
    assert sorted(worker.apply(on, run=fake, say=lambda _: None)) == ["started mira-body.service", "stopped mira-pet.service"]
    assert worker.apply(on, run=fake, say=lambda _: None) == []                         # settled: nothing more to do
    off = {**on, "body": {"enabled": False}}
    assert sorted(worker.apply(off, run=fake, say=lambda _: None)) == ["started mira-pet.service", "stopped mira-body.service"]
    assert running[worker.COMPANION] == "active"


def test_a_machine_without_her_bodies_has_nothing_started_for_them(monkeypatch):
    worker = _worker()
    monkeypatch.setattr(worker.os, "geteuid", lambda: 0)
    calls = []

    def fake(command, **_):
        calls.append(command[4])
        return subprocess.CompletedProcess(command, 0, "not-found\n" if command[4] == "show" else "inactive\n", "")

    headless = {"host": "debhvk", "user": "havok", "body": {"enabled": False}, "companion": {"enabled": False}}
    assert worker.apply(headless, run=fake, say=lambda _: None) == []
    assert "start" not in calls and "stop" not in calls
