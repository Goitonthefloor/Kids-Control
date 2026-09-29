"""Install the agent as a system service, outside the child account."""

from __future__ import annotations

import os
import subprocess
import sys
import shutil
import json
from xml.sax.saxutils import escape
from pathlib import Path

ADMIN_NOTICE = (
    "Das Kinderkonto darf kein Administrator sein. "
    "Mit sudo oder Windows-Adminrechten kann es den Dienst trotzdem stoppen."
)


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
    def quote(value):
        return json.dumps(str(value).replace("%", "%%"), ensure_ascii=False)
    return f"""[Unit]
Description=KidsControl Client Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory={quote(install_dir)}
Environment={quote('PYTHONPATH=' + str(install_dir))}
EnvironmentFile=-{quote(env_file)}
ExecStart={quote(python)} -m kidscontrol_agent --env {quote(env_file)}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


def render_launchd_plist(*, python: str, install_dir: Path, env_file: Path) -> str:
    python, install_dir, env_file = (escape(str(value)) for value in (python, install_dir, env_file))
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
        "chcp 65001 >nul\r\n"
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
    os.chown(env_file.parent, 0, 0)
    os.chmod(env_file.parent, 0o700)
    if install_dir.is_dir():
        if any(p.is_symlink() for p in install_dir.rglob("*")):
            raise PermissionError("Symlinks im Dienstverzeichnis sind nicht erlaubt")
        for dirpath, _dirnames, filenames in os.walk(install_dir):
            os.chown(dirpath, 0, 0)
            os.chmod(dirpath, 0o755)
            for name in filenames:
                path = Path(dirpath) / name
                if path.is_symlink():
                    raise PermissionError(f"Symlink im Dienstverzeichnis: {path}")
                os.chown(path, 0, 0)
                os.chmod(path, 0o644)
    # Apply last: an env file inside install_dir must not become world-readable.
    if env_file.is_file():
        os.chown(env_file, 0, 0)
        os.chmod(env_file, 0o600)


def _trusted_unix_path(path: Path) -> None:
    """Reject writable owners/ancestors, including a user-owned interpreter."""
    if path.is_symlink():
        raise PermissionError(f"Unsicherer symbolischer Pfad: {path}")
    for part in (path, *path.parents):
        if not part.exists():
            continue
        info = part.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise PermissionError(f"Dienstpfad muss root gehören und geschützt sein: {part}")


def service_paths() -> tuple[Path, Path]:
    windows = sys.platform == "win32"
    root = (Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "KidsControl"
            if windows else Path("/opt/kidscontrol-client"))
    target_env = root / "client.env" if windows else Path("/etc/kidscontrol/client.env")
    return root, target_env


def _prepare_install(source: Path, env_file: Path, python: str) -> tuple[Path, Path]:
    """Copy code out of the download/child account before registering a service."""
    windows = sys.platform == "win32"
    root, target_env = service_paths()
    if not windows:
        _trusted_unix_path(root)
        _trusted_unix_path(target_env)
        _trusted_unix_path(Path(python).resolve())
    else:
        executable = Path(python).resolve()
        system_roots = [Path(os.environ[k]).resolve() for k in ("ProgramFiles", "ProgramFiles(x86)", "SystemRoot") if os.environ.get(k)]
        if not any(executable.is_relative_to(base) for base in system_roots):
            raise PermissionError("Python für alle Benutzer unter Programme installieren; kein Interpreter im Benutzerprofil")
    root.mkdir(parents=True, exist_ok=True)
    if not windows:
        _lock_unix(root, target_env)
    package = source / "kidscontrol_agent"
    if any(p.is_symlink() for p in package.rglob("*")) or package.is_symlink():
        raise PermissionError("Agent-Paket darf keine Symlinks enthalten")
    if source.resolve() != root.resolve():
        shutil.copytree(package, root / "kidscontrol_agent", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    target_env.parent.mkdir(parents=True, exist_ok=True)
    if env_file.resolve() != target_env.resolve():
        shutil.copyfile(env_file, target_env)
    if windows:
        for args in (["/reset", "/T"], ["/inheritance:r", "/grant:r",
                     "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F", "/T"]):
            result = _run(["icacls", str(root), *args])
            if result.returncode:
                raise PermissionError("Dienstverzeichnis konnte nicht geschützt werden")
    else:
        _lock_unix(root, target_env)
    return root, target_env


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
    root, env_file = _prepare_install(root, env_file, executable)
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
        runner.write_bytes(render_windows_runner(python=executable, install_dir=root, env_file=env_file).encode("utf-8"))
        started = _run(windows_task_argv(runner))
        if started.returncode != 0:
            detail = (started.stderr or started.stdout or "").strip()
            raise RuntimeError(detail or "schtasks create failed")
        _run(["schtasks", "/Run", "/TN", "KidsControlAgent"])
        return "KidsControlAgent läuft als SYSTEM"
    raise RuntimeError(f"kein Systemdienst für {system}")
