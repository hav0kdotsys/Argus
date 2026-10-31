"""ARGUS updates from its own repository: no upstream fetch, prompt or merge unless asked for."""

from pathlib import Path

import pytest

from hermes_cli import update_cmd_git


def test_upstream_sync_is_off_by_default(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("ARGUS_UPDATE_FROM_UPSTREAM", raising=False)

    def no_git(*_a, **_k):
        raise AssertionError("argus update must not touch upstream by default")

    monkeypatch.setattr("hermes_cli.update_custody.run_git", no_git)
    monkeypatch.setattr("hermes_cli.update_cmd._has_upstream_remote", no_git)
    # True = the origin compare is the complete check (origin is ARGUS's whole truth).
    assert update_cmd_git._sync_with_upstream_if_needed(["git"], tmp_path) is True


@pytest.mark.parametrize("value", ["1", "true", "yes"])
def test_opt_in_reaches_the_upstream_path(monkeypatch, tmp_path: Path, value):
    monkeypatch.setenv("ARGUS_UPDATE_FROM_UPSTREAM", value)
    seen = []
    monkeypatch.setattr("hermes_cli.update_cmd._has_upstream_remote", lambda *a, **k: seen.append("checked") or False)
    monkeypatch.setattr("hermes_cli.update_cmd._should_skip_upstream_prompt", lambda: True)
    assert update_cmd_git._sync_with_upstream_if_needed(["git"], tmp_path) is False
    assert seen == ["checked"]
