"""Warning style: message window or toast, chosen from the client settings menu."""

import os
from pathlib import Path

import pytest

from kidscontrol_agent import notify_style
from kidscontrol_agent.agent import main
from kidscontrol_agent.enforce import notify
from kidscontrol_agent.notify_style import (
    default_style,
    load_notify_style,
    normalize_style,
    save_notify_style,
    set_active_env,
)
from kidscontrol_agent.settings import _build_settings_window, _text_settings, open_settings


def setup_function():
    set_active_env(None)


def teardown_function():
    set_active_env(None)


def test_normalize_and_platform_default(monkeypatch):
    assert normalize_style(" Meldungsfenster ") == "window"
    assert normalize_style("hinweis") == "toast"
    assert normalize_style("nope") is None
    monkeypatch.setattr(notify_style.os, "name", "nt")
    assert default_style() == "window"
    monkeypatch.setattr(notify_style.os, "name", "posix")
    assert default_style() == "toast"


def test_env_overrides_saved_file(tmp_path, monkeypatch):
    path = tmp_path / "notify-style"
    path.write_text("window\n", encoding="utf-8")
    monkeypatch.delenv("KIDSCONTROL_NOTIFY_STYLE", raising=False)
    monkeypatch.setattr(notify_style, "style_candidates", lambda: [path])
    assert load_notify_style() == "window"
    monkeypatch.setenv("KIDSCONTROL_NOTIFY_STYLE", "toast")
    assert load_notify_style() == "toast"


def test_invalid_or_unreadable_file_uses_default(tmp_path, monkeypatch):
    path = tmp_path / "notify-style"
    path.write_text("banana\n", encoding="utf-8")
    monkeypatch.delenv("KIDSCONTROL_NOTIFY_STYLE", raising=False)
    monkeypatch.setattr(notify_style, "style_candidates", lambda: [path])
    monkeypatch.setattr(notify_style.os, "name", "posix")
    assert load_notify_style() == "toast"
    path.write_text("window\n", encoding="utf-8")
    path.chmod(0)
    try:
        assert load_notify_style() == "toast"
    finally:
        path.chmod(0o600)


def test_save_roundtrip_beside_active_env(tmp_path, monkeypatch):
    monkeypatch.delenv("KIDSCONTROL_NOTIFY_STYLE", raising=False)
    monkeypatch.delenv("KIDSCONTROL_NOTIFY_STYLE_PATH", raising=False)
    env = tmp_path / "client.env"
    env.write_text("KIDSCONTROL_SERVER=http://127.0.0.1:8000\n", encoding="utf-8")
    set_active_env(env)
    saved = save_notify_style("fenster")
    assert saved == tmp_path / "notify-style"
    assert saved.read_text(encoding="utf-8") == "window\n"
    assert load_notify_style() == "window"


def test_save_without_rights_names_the_agent_file(tmp_path, monkeypatch):
    target = tmp_path / "locked" / "notify-style"
    monkeypatch.setenv("KIDSCONTROL_NOTIFY_STYLE_PATH", str(target))

    def denied(self, *args, **kwargs):
        raise OSError("denied")

    monkeypatch.setattr(Path, "mkdir", denied)
    with pytest.raises(PermissionError, match="Administratorrechten"):
        save_notify_style("toast")


def test_text_menu_saves_and_ignores_unknown_choice(tmp_path, monkeypatch, capsys):
    path = tmp_path / "notify-style"
    monkeypatch.setenv("KIDSCONTROL_NOTIFY_STYLE_PATH", str(path))
    monkeypatch.delenv("KIDSCONTROL_NOTIFY_STYLE", raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt: "1")
    assert _text_settings() == 0
    assert path.read_text(encoding="utf-8").strip() == "window"
    assert "Gespeichert: Meldungsfenster" in capsys.readouterr().out
    monkeypatch.setattr("builtins.input", lambda prompt: "x")
    assert _text_settings() == 0
    assert "Unverändert." in capsys.readouterr().out
    assert path.read_text(encoding="utf-8").strip() == "window"


def test_text_menu_reports_missing_rights(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt: "2")

    def denied(style: str) -> Path:
        raise PermissionError("Keine Schreibrechte für /etc/kidscontrol/notify-style.")

    monkeypatch.setattr("kidscontrol_agent.settings.save_notify_style", denied)
    assert _text_settings() == 1
    assert "Keine Schreibrechte" in capsys.readouterr().out


def test_settings_flag_uses_env_path(tmp_path, monkeypatch):
    env = tmp_path / "client.env"
    seen: dict[str, Path | None] = {}

    def fake_open() -> int:
        seen["active"] = notify_style._active_env
        return 3

    monkeypatch.setattr("kidscontrol_agent.settings.open_settings", fake_open)
    assert main(["--settings", "--env", str(env)]) == 3
    assert seen["active"] == env


def test_open_settings_falls_back_to_text_menu(tmp_path, monkeypatch, capsys):
    path = tmp_path / "notify-style"
    monkeypatch.setenv("KIDSCONTROL_NOTIFY_STYLE_PATH", str(path))
    monkeypatch.delenv("KIDSCONTROL_NOTIFY_STYLE", raising=False)
    monkeypatch.setattr(
        "kidscontrol_agent.settings._gui_settings",
        lambda: (_ for _ in ()).throw(RuntimeError("no display")),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    assert open_settings() == 0
    assert "Fenster nicht verfügbar" in capsys.readouterr().out
    assert path.read_text(encoding="utf-8").strip() == "toast"


def test_notify_picks_window_or_toast(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))

    monkeypatch.setattr("kidscontrol_agent.enforce.subprocess.run", fake_run)
    monkeypatch.setattr("kidscontrol_agent.enforce.detect_os", lambda: "linux")
    monkeypatch.setattr(
        "kidscontrol_agent.enforce.shutil.which",
        lambda name: "/usr/bin/zenity" if name == "zenity" else None,
    )
    notify("Titel", "Text", style="window")
    notify("Titel", "Text", style="toast")
    assert calls[0][0] == "zenity"
    assert calls[1][0] == "notify-send"

    monkeypatch.setattr("kidscontrol_agent.enforce.detect_os", lambda: "windows")
    notify("Titel", "Text", style="window")
    notify("Titel", "Text", style="toast")
    assert calls[2][0] == "powershell"
    assert "MessageBox" in calls[2][3]
    assert "ShowBalloonTip" in calls[3][3]

    monkeypatch.setattr("kidscontrol_agent.enforce.detect_os", lambda: "macos")
    notify("Titel", "Text", style="window")
    notify("Titel", "Text", style="toast")
    assert "display dialog" in " ".join(calls[4])
    assert "display notification" in " ".join(calls[5])


def test_linux_window_without_zenity_uses_tk(monkeypatch):
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr("kidscontrol_agent.enforce.detect_os", lambda: "linux")
    monkeypatch.setattr("kidscontrol_agent.enforce.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "kidscontrol_agent.enforce._tk_message",
        lambda title, message: shown.append((title, message)),
    )
    notify("Titel", "Text", style="meldungsfenster")
    assert shown == [("Titel", "Text")]


def test_dry_run_does_not_launch_a_notifier(monkeypatch, capsys):
    monkeypatch.setattr(
        "kidscontrol_agent.enforce.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("notifier")),
    )
    notify("Titel", "Text", dry_run=True, style="window")
    assert "[notify] Titel: Text" in capsys.readouterr().out


def _widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _widgets(child)


def test_settings_window_saves_the_selected_style(tmp_path, monkeypatch):
    pytest.importorskip("tkinter")
    if not os.environ.get("DISPLAY"):
        pytest.skip("no display")
    path = tmp_path / "notify-style"
    monkeypatch.setenv("KIDSCONTROL_NOTIFY_STYLE_PATH", str(path))
    monkeypatch.delenv("KIDSCONTROL_NOTIFY_STYLE", raising=False)
    root = _build_settings_window()
    try:
        root.update()
        assert root.title() == "KidsControl Einstellungen"
        texts = []
        for widget in _widgets(root):
            try:
                texts.append(widget.cget("text"))
            except Exception:
                continue
        assert "Meldungsfenster  –  muss bestätigt werden" in texts
        assert "Toast  –  kurzer Hinweis, verschwindet von selbst" in texts
        for widget in _widgets(root):
            try:
                if widget.cget("value") == "window":
                    widget.invoke()
            except Exception:
                continue
        for widget in _widgets(root):
            try:
                if widget.cget("text") == "Speichern":
                    widget.invoke()
            except Exception:
                continue
        assert path.read_text(encoding="utf-8").strip() == "window"
    finally:
        root.destroy()
