"""Offline fail-closed behavior for the child-PC agent."""

from __future__ import annotations

import io
import os
import urllib.error

from kidscontrol_agent.agent import LOCK_RETRY_SECONDS, _wait_until_next_sync, run_cycle, run_once
from kidscontrol_agent.offline import load_cached_policy, offline_policy, save_cached_policy


def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("KIDSCONTROL_POLICY_CACHE", str(tmp_path / "policy.json"))
    return {
        "server": "http://127.0.0.1:9",
        "device_key": "device-key",
        "poll_seconds": 30,
        "dry_run": True,
    }


def _silence(monkeypatch):
    monkeypatch.setattr("kidscontrol_agent.agent.user_session_active", lambda: True)
    monkeypatch.setattr("kidscontrol_agent.agent.save_cached_quota", lambda rules: None)
    monkeypatch.setattr("kidscontrol_agent.agent.warn_running_quotas", lambda *args, **kwargs: None)
    monkeypatch.setattr("kidscontrol_agent.agent.handle_commands", lambda *args, **kwargs: None)
    monkeypatch.setattr("kidscontrol_agent.agent.refresh_pending_updates", lambda: None)


def test_offline_without_cache_denies_and_locks(tmp_path, monkeypatch):
    _cfg(tmp_path, monkeypatch)
    policy = offline_policy()
    assert policy["allow_session"] is False
    assert policy["reason"] == "offline"
    assert policy["blocked_apps"] == []
    assert policy["actions"]["lock_session_when_denied"] is True


def test_offline_keeps_blocks_and_stops_quota_apps(tmp_path, monkeypatch):
    _cfg(tmp_path, monkeypatch)
    save_cached_policy(
        {
            "child": {"display_name": "Nora"},
            "allow_session": True,
            "blocked_apps": [{"pattern": "minecraft", "match_mode": "contains", "label": "Minecraft"}],
            "quota_apps": [{"id": 7, "pattern": "roblox", "match_mode": "exact", "label": "Roblox"}],
            "actions": {"kill_blocked_apps": False},
            "commands": [{"id": 1, "kind": "update_all"}],
        }
    )
    policy = offline_policy()
    assert policy["allow_session"] is False
    assert policy["child"]["display_name"] == "Nora"
    patterns = {rule["pattern"] for rule in policy["blocked_apps"]}
    assert patterns == {"minecraft", "roblox"}
    assert policy["actions"]["kill_blocked_apps"] is True
    assert "commands" not in policy
    cached = load_cached_policy()
    assert cached["allow_session"] is True
    assert "commands" not in cached
    if os.name != "nt":
        assert (tmp_path / "policy.json").stat().st_mode & 0o777 == 0o600


def test_sync_failure_enforces_fail_closed_policy(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _silence(monkeypatch)
    save_cached_policy(
        {
            "allow_session": True,
            "blocked_apps": [{"pattern": "steam", "match_mode": "startswith", "label": "Steam"}],
            "quota_apps": [],
        }
    )
    applied: list[dict] = []

    def fail_sync(*args, **kwargs):
        raise urllib.error.URLError("hub down")

    monkeypatch.setattr("kidscontrol_agent.agent.sync", fail_sync)
    monkeypatch.setattr("kidscontrol_agent.agent.enforce_policy", lambda policy, **kwargs: applied.append(policy))
    code = run_once(cfg)
    assert code == 1
    assert applied[0]["allow_session"] is False
    assert applied[0]["reason"] == "offline"
    assert applied[0]["blocked_apps"][0]["pattern"] == "steam"


def test_http_error_also_fail_closes(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _silence(monkeypatch)
    applied: list[dict] = []

    def fail_sync(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="http://hub/api/v1/agent/sync",
            code=503,
            msg="down",
            hdrs=None,
            fp=io.BytesIO(b"unavailable"),
        )

    monkeypatch.setattr("kidscontrol_agent.agent.sync", fail_sync)
    monkeypatch.setattr("kidscontrol_agent.agent.enforce_policy", lambda policy, **kwargs: applied.append(policy))
    code, denied, policy = run_cycle(cfg)
    assert code == 1
    assert denied is True
    assert policy["allow_session"] is False
    assert applied


def test_successful_sync_persists_allow_and_skips_commands_in_the_cache(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _silence(monkeypatch)
    fresh = {
        "child": {"display_name": "Nora"},
        "allow_session": True,
        "reason": "within_window",
        "remaining_minutes": 20,
        "blocked_apps": [],
        "quota_apps": [],
        "commands": [{"id": 4, "kind": "update_all"}],
        "actions": {"lock_session_when_denied": True, "kill_blocked_apps": True},
    }
    monkeypatch.setattr("kidscontrol_agent.agent.sync", lambda *args, **kwargs: fresh)
    monkeypatch.setattr("kidscontrol_agent.agent.enforce_policy", lambda *args, **kwargs: None)
    code, denied, policy = run_cycle(cfg)
    assert code == 0
    assert denied is False
    assert policy == fresh
    cached = load_cached_policy()
    assert cached["allow_session"] is True
    assert "commands" not in cached


def test_missing_device_key_does_not_lock(monkeypatch):
    called: list[int] = []
    monkeypatch.setattr("kidscontrol_agent.agent.enforce_policy", lambda *args, **kwargs: called.append(1))
    code = run_once({"server": "http://127.0.0.1:9", "device_key": "", "poll_seconds": 30, "dry_run": True})
    assert code == 2
    assert called == []


def test_denied_session_is_relocked_until_the_next_poll(monkeypatch):
    sleeps: list[int] = []
    applied: list[bool] = []
    monkeypatch.setattr("kidscontrol_agent.agent.time.sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(
        "kidscontrol_agent.agent.enforce_policy",
        lambda policy, **kwargs: applied.append(kwargs.get("announce", True)),
    )
    policy = {"allow_session": False, "actions": {"lock_session_when_denied": True}}
    _wait_until_next_sync(30, policy=policy, session_denied=True, dry_run=False)
    assert sleeps == [LOCK_RETRY_SECONDS] * (30 // LOCK_RETRY_SECONDS)
    assert applied == [False] * (len(sleeps) - 1)

    sleeps.clear()
    applied.clear()
    _wait_until_next_sync(30, policy=policy, session_denied=True, dry_run=True)
    assert sleeps == [30]
    assert applied == []
