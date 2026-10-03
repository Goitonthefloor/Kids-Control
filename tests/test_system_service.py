"""The agent must install as a system service, not as the child account."""

import shutil
import subprocess
from pathlib import Path, PurePosixPath

from kidscontrol_agent.enforce import is_protected_process
from kidscontrol_agent.service_install import (
    render_launchd_plist,
    render_systemd_unit,
    render_windows_runner,
    windows_task_argv,
)
from kidscontrol_agent.setup import main


def test_systemd_unit_runs_as_root(tmp_path):
    text = render_systemd_unit(
        python="/usr/bin/python3",
        install_dir=PurePosixPath("/opt/kids%control"),
        env_file=PurePosixPath("/etc/kids%control/client.env"),
    )
    assert "User=root" in text
    assert "Group=root" in text
    assert "Restart=always" in text
    # Quotes here are part of the path. systemd then refuses to start the unit.
    assert 'WorkingDirectory="/' not in text
    assert "WorkingDirectory=/opt/kids%%control\n" in text
    assert 'EnvironmentFile=-"/' not in text
    assert "EnvironmentFile=-/etc/kids%%control/client.env\n" in text
    assert 'ExecStart="/usr/bin/python3" -m kidscontrol_agent --env "/etc/kids%%control/client.env"\n' in text
    analyze = shutil.which("systemd-analyze")
    if not analyze:
        return
    unit = tmp_path / "kidscontrol-agent.service"
    unit.write_text(text, encoding="utf-8")
    result = subprocess.run([analyze, "verify", str(unit)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr + result.stdout


def test_launchd_plist_runs_as_root():
    text = render_launchd_plist(
        python="/usr/bin/python3",
        install_dir=PurePosixPath("/opt/kidscontrol-client"),
        env_file=PurePosixPath("/etc/kidscontrol/client.env"),
    )
    assert "<key>UserName</key>" in text
    assert "<string>root</string>" in text
    assert "com.kidscontrol.agent" in text


def test_windows_task_runs_as_system():
    argv = windows_task_argv(Path(r"C:\ProgramData\KidsControl\run-agent.cmd"))
    assert "SYSTEM" in argv
    assert "ONSTART" in argv
    assert "KidsControlAgent" in argv
    runner = render_windows_runner(
        python=r"C:\Python\python.exe",
        install_dir=Path(r"C:\ProgramData\KidsControl"),
        env_file=Path(r"C:\ProgramData\KidsControl\client.env"),
    )
    assert "LOCALAPPDATA" not in runner
    assert "kidscontrol_loop" in runner


def test_setup_refuses_unprivileged_account(monkeypatch):
    monkeypatch.setattr("kidscontrol_agent.setup.is_privileged", lambda: False)
    code = main(["--server", "http://127.0.0.1:9", "--token", "test-token"])
    assert code == 1


def test_agent_does_not_target_itself_or_pid1():
    assert is_protected_process(1, "systemd")
    assert is_protected_process(0, "python3")
    import os

    assert is_protected_process(os.getpid(), "python3")
    assert is_protected_process(4242, "sshd")
    assert not is_protected_process(4242, "minecraft")
