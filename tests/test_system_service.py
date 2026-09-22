"""The agent must install as a system service, not as the child account."""

from pathlib import Path

from kidscontrol_agent.enforce import is_protected_process
from kidscontrol_agent.service_install import (
    render_launchd_plist,
    render_systemd_unit,
    render_windows_runner,
    windows_task_argv,
)
from kidscontrol_agent.setup import main


def test_systemd_unit_runs_as_root():
    text = render_systemd_unit(
        python="/usr/bin/python3",
        install_dir=Path("/opt/kidscontrol-client"),
        env_file=Path("/etc/kidscontrol/client.env"),
    )
    assert "User=root" in text
    assert "Group=root" in text
    assert "Restart=always" in text
    assert "/etc/kidscontrol/client.env" in text


def test_launchd_plist_runs_as_root():
    text = render_launchd_plist(
        python="/usr/bin/python3",
        install_dir=Path("/opt/kidscontrol-client"),
        env_file=Path("/etc/kidscontrol/client.env"),
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


def test_setup_refuses_unprivileged_account():
    code = main(["--server", "http://127.0.0.1:9", "--token", "test-token"])
    assert code == 1


def test_agent_does_not_target_itself_or_pid1():
    assert is_protected_process(1, "systemd")
    assert is_protected_process(0, "python3")
    import os

    assert is_protected_process(os.getpid(), "python3")
    assert is_protected_process(4242, "sshd")
    assert not is_protected_process(4242, "minecraft")
