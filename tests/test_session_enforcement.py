"""Session lock and notifications aimed at the interactive user."""

from __future__ import annotations

from kidscontrol_agent.enforce import _linux_desktop_session, lock_session, notify


def test_macos_lock_uses_the_shortcut_when_system_binaries_are_missing(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr("kidscontrol_agent.enforce.detect_os", lambda: "macos")
    monkeypatch.setattr("kidscontrol_agent.enforce._try_sac_lock", lambda: False)
    monkeypatch.setattr("kidscontrol_agent.enforce.os.path.isfile", lambda path: False)
    monkeypatch.setattr("kidscontrol_agent.enforce._is_root", lambda: False)
    monkeypatch.setattr(
        "kidscontrol_agent.enforce.subprocess.run",
        lambda argv, **kwargs: calls.append(list(argv)),
    )
    lock_session()
    assert calls[0][0] == "osascript"
    assert "key code 12" in calls[0][2]
    assert all("CGSession" not in part for part in calls[0])


def test_macos_prefers_the_login_framework(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr("kidscontrol_agent.enforce.detect_os", lambda: "macos")
    monkeypatch.setattr("kidscontrol_agent.enforce._try_sac_lock", lambda: True)
    monkeypatch.setattr(
        "kidscontrol_agent.enforce.subprocess.run",
        lambda argv, **kwargs: calls.append(list(argv)),
    )
    lock_session()
    assert calls == []


def test_macos_uses_cgsession_only_when_the_binary_exists(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr("kidscontrol_agent.enforce.detect_os", lambda: "macos")
    monkeypatch.setattr("kidscontrol_agent.enforce._try_sac_lock", lambda: False)
    monkeypatch.setattr("kidscontrol_agent.enforce._is_root", lambda: True)
    monkeypatch.setattr("kidscontrol_agent.enforce._macos_console_uid", lambda: 501)
    monkeypatch.setattr(
        "kidscontrol_agent.enforce.os.path.isfile",
        lambda path: path.endswith("CGSession"),
    )
    monkeypatch.setattr(
        "kidscontrol_agent.enforce.subprocess.run",
        lambda argv, **kwargs: calls.append(list(argv)),
    )
    lock_session()
    assert calls[0][:3] == ["launchctl", "asuser", "501"]
    assert calls[0][3].endswith("CGSession")
    assert calls[0][4] == "-suspend"


def test_linux_toast_targets_the_graphical_user(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr("kidscontrol_agent.enforce.detect_os", lambda: "linux")
    monkeypatch.setattr("kidscontrol_agent.enforce._is_root", lambda: True)
    monkeypatch.setattr(
        "kidscontrol_agent.enforce._linux_desktop_session",
        lambda: {"Name": "mia", "User": "1000", "Display": ":1", "Type": "wayland", "Active": "yes"},
    )
    monkeypatch.setattr(
        "kidscontrol_agent.enforce.shutil.which",
        lambda name: "/usr/sbin/runuser" if name == "runuser" else None,
    )
    monkeypatch.setattr(
        "kidscontrol_agent.enforce._spawn_notice",
        lambda argv, **kwargs: calls.append(list(argv)),
    )
    notify("Titel", "Text", style="toast")
    argv = calls[0]
    assert argv[:5] == ["runuser", "-u", "mia", "--", "env"]
    assert "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus" in argv
    assert "DISPLAY=:1" in argv
    assert "WAYLAND_DISPLAY=wayland-0" in argv
    assert argv[argv.index("notify-send"):] == ["notify-send", "--", "Titel", "Text"]


def test_linux_session_skips_tty_and_remote(monkeypatch):
    monkeypatch.setattr("kidscontrol_agent.enforce._is_root", lambda: True)
    monkeypatch.setattr(
        "kidscontrol_agent.enforce.shutil.which",
        lambda name: "/bin/loginctl" if name == "loginctl" else None,
    )

    def fake_check_output(argv, **kwargs):
        if argv[:2] == ["loginctl", "list-sessions"]:
            return "1 1000 mia\n2 1000 mia\n3 1000 mia\n"
        session = argv[2]
        if session == "1":
            return "Name=mia\nUser=1000\nActive=yes\nDisplay=\nType=tty\nRemote=no\nState=active\n"
        if session == "2":
            return "Name=mia\nUser=1000\nActive=yes\nDisplay=:0\nType=x11\nRemote=yes\nState=active\n"
        return "Name=mia\nUser=1000\nActive=yes\nDisplay=:0\nType=wayland\nRemote=no\nState=active\n"

    monkeypatch.setattr("kidscontrol_agent.enforce.subprocess.check_output", fake_check_output)
    info = _linux_desktop_session()
    assert info is not None
    assert info["Type"] == "wayland"
    assert info["Display"] == ":0"


def test_windows_message_runs_in_the_console_session(monkeypatch):
    spawned: list[tuple[str, dict]] = []
    monkeypatch.setattr("kidscontrol_agent.enforce.detect_os", lambda: "windows")
    monkeypatch.setattr("kidscontrol_agent.enforce._windows_service_session", lambda: True)

    def spawn(command, extra_env=None):
        spawned.append((command, extra_env or {}))
        return True

    monkeypatch.setattr("kidscontrol_agent.enforce._windows_run_as_console_user", spawn)
    monkeypatch.setattr(
        "kidscontrol_agent.enforce.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("session 0 dialog")),
    )
    notify("Titel", "Hallo", style="window")
    command, extra = spawned[0]
    assert "powershell" in command
    assert "Popup" in command
    assert extra["KC_TITLE"] == "Titel"
    assert extra["KC_MESSAGE"] == "Hallo"
    assert "Hallo" not in command


def test_windows_lock_also_targets_the_console_session(monkeypatch):
    calls: list[object] = []
    monkeypatch.setattr("kidscontrol_agent.enforce.detect_os", lambda: "windows")
    monkeypatch.setattr(
        "kidscontrol_agent.enforce.subprocess.run",
        lambda argv, **kwargs: calls.append(list(argv)),
    )
    monkeypatch.setattr(
        "kidscontrol_agent.enforce._windows_run_as_console_user",
        lambda command, extra_env=None: calls.append(command) or True,
    )
    lock_session()
    assert calls[0][0] == "rundll32.exe"
    assert "LockWorkStation" in calls[0][1]
    assert calls[1] == "rundll32.exe user32.dll,LockWorkStation"
