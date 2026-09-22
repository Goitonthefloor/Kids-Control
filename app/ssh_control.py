"""SSH helpers for Linux child devices (key-based, non-interactive)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app import config
from app.db import Device


def ssh_target(device: Device) -> str:
    host = (device.ssh_host or device.hostname or "").strip()
    user = (device.ssh_user or "").strip()
    if not host or not user:
        raise ValueError("SSH-Host und SSH-Benutzer müssen gesetzt sein.")
    return f"{user}@{host}"


def ssh_argv(device: Device, remote_command: str) -> list[str]:
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=8",
        "-p",
        str(int(device.ssh_port or 22)),
    ]
    key = (device.ssh_key_path or "").strip()
    if key:
        argv.extend(["-i", key])
    argv.append(ssh_target(device))
    argv.append(remote_command)
    return argv


def run_ssh(device: Device, remote_command: str, *, timeout: int = 180) -> tuple[int, str]:
    if not device.ssh_enabled:
        raise ValueError("SSH ist für dieses Gerät nicht aktiv.")
    proc = subprocess.run(
        ssh_argv(device, remote_command),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    text = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, text[-4000:]


LINUX_UPDATE_ONE = r"""
set -eu
pkg=$(printf '%s' "$1" | tr -cd 'A-Za-z0-9._+-')
if [ -z "$pkg" ]; then echo "leeres Paket"; exit 2; fi
if command -v apt-get >/dev/null 2>&1; then
  sudo -n apt-get update && sudo -n apt-get install -y --only-upgrade "$pkg"
elif command -v dnf >/dev/null 2>&1; then
  sudo -n dnf upgrade -y "$pkg"
elif command -v pacman >/dev/null 2>&1; then
  sudo -n pacman -Syu --noconfirm "$pkg"
else
  echo "Kein unterstützter Paketmanager (apt/dnf/pacman)."
  exit 3
fi
"""

LINUX_UPDATE_ALL = r"""
set -eu
if command -v apt-get >/dev/null 2>&1; then
  sudo -n apt-get update && sudo -n apt-get upgrade -y
elif command -v dnf >/dev/null 2>&1; then
  sudo -n dnf upgrade -y
elif command -v pacman >/dev/null 2>&1; then
  sudo -n pacman -Syu --noconfirm
else
  echo "Kein unterstützter Paketmanager (apt/dnf/pacman)."
  exit 3
fi
"""


def store_private_key(device_id: int, private_key: str) -> Path:
    text = (private_key or "").strip()
    if "PRIVATE KEY" not in text or len(text) > 16000:
        raise ValueError("invalid_private_key")
    directory = config.data_dir() / "keys"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    path = directory / f"device-{device_id}"
    path.write_text(text + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def remote_update_script(package_name: str | None) -> str:
    if package_name:
        # Pass package as $1 via a here-doc wrapper
        safe = package_name.replace("'", "")
        return f"bash -s -- '{safe}' <<'KC_UPDATE'\n{LINUX_UPDATE_ONE}\nKC_UPDATE"
    return f"bash -s <<'KC_UPDATE'\n{LINUX_UPDATE_ALL}\nKC_UPDATE"
