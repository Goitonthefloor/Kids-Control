"""Install the agent as a system service, outside the child account."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def is_privileged() -> bool:
    """True when this process is root or a Windows administrator."""
    if os.name == "nt":
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def package_root() -> Path:
    """Directory that contains the kidscontrol_agent package."""
    return Path(__file__).resolve().parent.parent


def render_systemd_unit(*, python: str, install_dir: Path, env_file: Path) -> str:
    return f"""[Unit]
Description=KidsControl Client Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory={install_dir}
Environment=PYTHONPATH={install_dir}
EnvironmentFile=-{env_file}
ExecStart={python} -m kidscontrol_agent --env {env_file}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


def render_launchd_plist(*, python: str, install_dir: Path, env_file: Path) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.kidscontrol.agent</string>
  <key>UserName</key>
  <string>root</string>
  <key>GroupName</key>
  <string>wheel</string>
  <key>WorkingDirectory</key>
  <string>{install_dir}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>{install_dir}</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>-m</string>
    <string>kidscontrol_agent</string>
    <string>--env</string>
    <string>{env_file}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
"""


def render_windows_runner(*, python: str, install_dir: Path, env_file: Path) -> str:
    return (
        "@echo off\r\n"
        f"set PYTHONPATH={install_dir}\r\n"
        ":kidscontrol_loop\r\n"
        f"\"{python}\" -m kidscontrol_agent --env \"{env_file}\"\r\n"
        "timeout /t 5 /nobreak >nul\r\n"
        "goto kidscontrol_loop\r\n"
    )


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def _lock_unix(install_dir: Path, env_file: Path) -> None:
    env_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(env_file.parent, 0o700)
        if env_file.is_file():
            os.chmod(env_file, 0o600)
    except OSError:
        pass
    if install_dir.is_dir():
        for dirpath, _dirnames, filenames in os.walk(install_dir):
            try:
                os.chmod(dirpath, 0o755)
            except OSError:
                continue
            for name in filenames:
                try:
                    os.chmod(Path(dirpath) / name, 0o644)
                except OSError:
                    continue


def windows_task_argv(runner: Path) -> list[str]:
    return [
        "schtasks", "/Create", "/F",
        "/TN", "KidsControlAgent",
        "/SC", "ONSTART",
        "/RU", "SYSTEM",
        "/RL", "HIGHEST",
        "/TR", str(runner),
    ]


def install_system_service(env_file: Path, *, python: str | None = None, install_dir: Path | None = None) -> str:
    """Install and start the agent as root (Unix) or SYSTEM (Windows)."""
    if not is_privileged():
        raise PermissionError("system service requires administrator rights")
    root = install_dir or package_root()
    executable = python or sys.executable
    system = sys.platform
    if system.startswith("linux"):
        unit = Path("/etc/systemd/system/kidscontrol-agent.service")
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(render_systemd_unit(python=executable, install_dir=root, env_file=env_file), encoding="utf-8")
        os.chmod(unit, 0o644)
        _lock_unix(root, env_file)
        _run(["systemctl", "daemon-reload"])
        started = _run(["systemctl", "enable", "--now", "kidscontrol-agent"])
        if started.returncode != 0:
            detail = (started.stderr or started.stdout or "").strip()
            raise RuntimeError(detail or "systemctl enable failed")
        return "kidscontrol-agent läuft als root"
    if system == "darwin":
        plist = Path("/Library/LaunchDaemons/com.kidscontrol.agent.plist")
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(render_launchd_plist(python=executable, install_dir=root, env_file=env_file), encoding="utf-8")
        os.chmod(plist, 0o644)
        _lock_unix(root, env_file)
        _run(["launchctl", "bootout", "system", str(plist)])
        started = _run(["launchctl", "bootstrap", "system", str(plist)])
        if started.returncode != 0:
            started = _run(["launchctl", "load", "-w", str(plist)])
        if started.returncode != 0:
            detail = (started.stderr or started.stdout or "").strip()
            raise RuntimeError(detail or "launchctl bootstrap failed")
        return "com.kidscontrol.agent läuft als root"
    if system == "win32":
        root.mkdir(parents=True, exist_ok=True)
        runner = root / "run-agent.cmd"
        runner.write_bytes(render_windows_runner(python=executable, install_dir=root, env_file=env_file).encode("ascii", errors="replace"))
        _run(["icacls", str(root), "/inheritance:r", "/grant:r", "SYSTEM:(OI)(CI)F", "Administrators:(OI)(CI)F"])
        started = _run(windows_task_argv(runner))
        if started.returncode != 0:
            detail = (started.stderr or started.stdout or "").strip()
            raise RuntimeError(detail or "schtasks create failed")
        _run(["schtasks", "/Run", "/TN", "KidsControlAgent"])
        return "KidsControlAgent läuft als SYSTEM"
    raise RuntimeError(f"kein Systemdienst für {system}")
