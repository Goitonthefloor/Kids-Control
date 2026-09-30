"""Regressions from the initial review; no real desktop/account mutations."""
import os
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from threading import Event
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import policy
from app.db import Base, Child, AppRule, AppUsage
from app.oneclick import _linux_script, _linux_ticket_script, _windows_script, _windows_ticket_script
from kidscontrol_agent import agent, enforce


@pytest.mark.parametrize("events,expected", [
    ([(0, 1, True), (15, 2, False), (30, 1, True), (45, 2, False), (60, 1, True)], 60),
    ([(0, 1, True), (15, 2, True), (30, 1, True), (45, 2, True), (60, 1, True)], 60),
    ([(0, 1, False), (30, 1, True), (60, 1, False), (90, 1, False)], 30),
    ([(0, 1, True), (181, 1, True)], 0),
    ([(0, 1, True), (10, 2, True), (20, 2, True), (30, 1, True)], 30),
])
def test_app_clocks_union_without_idle_interference(monkeypatch, events, expected):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    start = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
    class Clock(datetime):
        current = start
        @classmethod
        def now(cls, tz=None):
            return cls.current
    monkeypatch.setattr(policy, "datetime", Clock)
    with Session(engine, autoflush=False) as db:
        child = Child(slug="test", display_name="Test", timezone="UTC")
        db.add(child); db.flush()
        rule = AppRule(child_id=child.id, pattern="game", scope="quota", daily_minutes=10)
        db.add(rule); db.flush()
        for seconds, device_id, running in events:
            Clock.current = start + timedelta(seconds=seconds)
            policy.tick_running_apps(db, child, [rule.id] if running else [], device_id=device_id)
        usage = db.query(AppUsage).one()
        assert usage.used_minutes * 60 + usage.remainder_seconds == expected


def test_notice_uses_nonwaiting_spawn(monkeypatch):
    calls = []
    monkeypatch.setattr(enforce, "_notice_processes", [])
    monkeypatch.setattr(enforce, "detect_os", lambda: "linux")
    monkeypatch.setattr(enforce, "_linux_user_argv", lambda args, extra: args)
    monkeypatch.setattr(enforce.subprocess, "run", lambda *a, **k: pytest.fail("blocking notifier"))
    monkeypatch.setattr(enforce.subprocess, "Popen", lambda *a, **k: calls.append(a) or SimpleNamespace(poll=lambda: None))
    enforce._run_desktop(["zenity", "--warning"])
    assert len(calls) == 1


def test_app_warns_before_kill_and_restart_does_not_extend_grace(monkeypatch):
    now, killed, notices = [0.0], [], []
    pid = [100]
    monkeypatch.setattr(agent, "_app_deadlines", {})
    monkeypatch.setattr(agent.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(agent, "notify", lambda title, text, **kw: notices.append(text))
    monkeypatch.setattr(agent, "find_matching_pids", lambda rules: [(pid[0], "game", "Game")])
    monkeypatch.setattr(agent, "kill_pid", lambda p, **kw: killed.append(p))
    rules = {"allow_session": True, "blocked_apps": [{"pattern": "game", "label": "Game"}]}
    agent.enforce_policy(rules)
    assert len(notices) == 1 and not killed and "30 Sekunden" in notices[0]
    now[0], pid[0] = 29, 200
    agent.enforce_policy(rules)
    assert not killed and len(notices) == 1
    now[0] = 30
    agent.enforce_policy(rules)
    assert killed == [200]
    agent.enforce_policy({"allow_session": True, "blocked_apps": []})
    assert agent._app_deadlines == {}


def test_slow_updates_do_not_block_enforcement_and_results_are_retried(monkeypatch):
    entered, release = Event(), Event()
    runs, locks = [], []
    monkeypatch.setattr(agent, "save_cached_watches", lambda x: None)
    monkeypatch.setattr(agent, "refresh_pending_updates", lambda: None)
    reports = []
    def report(server, key, cid, status, output):
        reports.append(status)
        if status == "done" and reports.count("done") == 1:
            raise OSError("network dropped after update")
    def update(*args, **kwargs):
        runs.append(1); entered.set()
        assert release.wait(3)
        return "done", "ok"
    monkeypatch.setattr(agent, "run_update", update)
    monkeypatch.setattr(agent, "report_command", report)
    monkeypatch.setattr(agent, "lock_session", lambda **k: locks.append(1))
    worker = agent.Maintenance()
    cfg = {"server": "hub", "device_key": "key", "dry_run": False}
    policy = {"commands": [{"id": 1, "kind": "update_all"}]}
    with ThreadPoolExecutor(max_workers=1) as executor:
        task = executor.submit(worker.run, cfg, policy)
        try:
            assert entered.wait(3)
            agent.enforce_policy({"allow_session": False}, announce=False)
            assert locks == [1] and not task.done()
        finally:
            release.set()
        with pytest.raises(OSError):
            task.result(timeout=3)
    worker.run(cfg, policy)
    worker.run(cfg, policy)
    assert len(runs) == 1
    assert reports == ["running", "done", "done"]


def test_posix_only_child_processes(monkeypatch):
    monkeypatch.setattr(enforce, "_target_uid", 1001)
    monkeypatch.setattr(enforce.subprocess, "check_output", lambda *a, **k:
                        "10 1000 game\n11 1001 game\n12 0 systemd\n")
    assert [p.pid for p in enforce._list_posix()] == [11]


def _linux_installer_reaches_sudo_when_sudo_user_unset(script: str, tmp_path):
    """The child runs the installer directly. SUDO_USER does not exist until sudo."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    marker = tmp_path / "sudo-called"
    sudo = bindir / "sudo"
    sudo.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > " + repr(str(marker)) + "\nexit 0\n", encoding="utf-8")
    sudo.chmod(0o755)
    path = tmp_path / "setup.sh"
    path.write_text(script, encoding="utf-8")
    env = os.environ.copy()
    env.pop("SUDO_USER", None)
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(["bash", str(path)], env=env, capture_output=True, text=True, timeout=10)
    assert "unbound variable" not in result.stderr
    assert marker.is_file(), result.stderr
    assert "bash" in marker.read_text(encoding="utf-8")


def test_linux_oneclick_survives_unset_sudo_user(tmp_path):
    script = _linux_script("http://127.0.0.1:8000", "token", systemd=True)
    assert 'export KIDSCONTROL_ACCOUNT="${SUDO_USER:-}"' in script
    assert 'export KIDSCONTROL_ACCOUNT="$SUDO_USER"' not in script
    subprocess.run(["bash", "-n", "-c", script], check=True)
    _linux_installer_reaches_sudo_when_sudo_user_unset(script, tmp_path)


def test_linux_ticket_installer_survives_unset_sudo_user(tmp_path):
    script = _linux_ticket_script("http://127.0.0.1:8000", "ticket", systemd=True)
    assert 'export KIDSCONTROL_ACCOUNT="${SUDO_USER:-}"' in script
    subprocess.run(["bash", "-n", "-c", script], check=True)
    _linux_installer_reaches_sudo_when_sudo_user_unset(script, tmp_path)


def test_windows_oneclick_forwards_child_account_across_uac():
    """UAC starts a new process, so a variable set before RunAs never arrives."""
    for script in (
        _windows_script("http://127.0.0.1:8000", "token"),
        _windows_ticket_script("http://127.0.0.1:8000", "ticket"),
    ):
        assert 'set "KIDSCONTROL_ACCOUNT=%~1"' in script
        assert "$env:USERNAME" in script
        assert "KIDSCONTROL_ACCOUNT=%USERNAME%" not in script.split("if errorlevel 1", 1)[1].split("exit /b", 1)[0]
        assert '--account "%KIDSCONTROL_ACCOUNT%"' in script


def test_restart_does_not_lock_before_hub_answers(monkeypatch):
    started, release = Event(), Event()
    enforced, waits = [], []

    def cycle(cfg, *, apply=False):
        started.set()
        assert release.wait(3)
        return 0, False, {
            "allow_session": True,
            "blocked_apps": [],
            "quota_apps": [],
            "actions": {"lock_session_when_denied": True, "kill_blocked_apps": True},
        }

    def enforce(policy, **kwargs):
        enforced.append(bool(policy.get("allow_session")))
        raise KeyboardInterrupt

    def sleep(_seconds):
        if not release.is_set():
            waits.append(1)
        if started.is_set():
            release.set()

    monkeypatch.setattr(agent, "run_cycle", cycle)
    monkeypatch.setattr(agent, "enforce_policy", enforce)
    monkeypatch.setattr(agent, "warn_running_quotas", lambda *a, **k: None)
    monkeypatch.setattr(agent.Maintenance, "run", lambda self, cfg, policy: None)
    monkeypatch.setattr(agent, "ManagedSession", lambda cfg: object())
    monkeypatch.setattr(agent.time, "sleep", sleep)
    code = agent.run_loop({
        "server": "http://hub",
        "device_key": "key",
        "dry_run": False,
        "poll_seconds": 30,
    })
    assert code == 0
    assert waits, "the loop never waited for the first sync"
    assert enforced == [True]


def test_hub_failure_still_fails_closed_after_the_attempt(monkeypatch):
    started, release = Event(), Event()
    enforced = []

    def cycle(cfg, *, apply=False):
        started.set()
        assert release.wait(3)
        return 1, True, {
            "allow_session": False,
            "blocked_apps": [],
            "quota_apps": [],
            "actions": {"lock_session_when_denied": True},
        }

    def enforce(policy, **kwargs):
        enforced.append(release.is_set() and not policy.get("allow_session"))
        raise KeyboardInterrupt

    monkeypatch.setattr(agent, "run_cycle", cycle)
    monkeypatch.setattr(agent, "enforce_policy", enforce)
    monkeypatch.setattr(agent, "warn_running_quotas", lambda *a, **k: None)
    monkeypatch.setattr(agent.Maintenance, "run", lambda self, cfg, policy: None)
    monkeypatch.setattr(agent, "ManagedSession", lambda cfg: object())
    monkeypatch.setattr(agent.time, "sleep", lambda _s: release.set() if started.is_set() else None)
    code = agent.run_loop({
        "server": "http://hub",
        "device_key": "key",
        "dry_run": False,
        "poll_seconds": 30,
    })
    assert code == 0
    assert enforced == [True]


def test_windows_only_local_child_processes(monkeypatch):
    monkeypatch.setattr(enforce, "_target_user", "Mia")
    monkeypatch.setenv("COMPUTERNAME", "PC")
    monkeypatch.setattr(enforce.subprocess, "check_output", lambda *a, **k:
        '"game.exe","10","Console","1","1 K","Running","PC\\Parent"\n'
        '"game.exe","11","Console","2","1 K","Running","PC\\Mia"\n'
        '"game.exe","12","Console","3","1 K","Running","DOMAIN\\Mia"\n')
    assert [p.pid for p in enforce._list_windows()] == [11]
