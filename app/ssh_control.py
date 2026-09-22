"""SSH helpers for Linux child devices (key-based, non-interactive)."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

from app import config
from app.db import Device

PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,80}$")


def ssh_target(device: Device) -> str:
    host = (device.ssh_host or device.hostname or "").strip()
    user = (device.ssh_user or "").strip()
    if not host or not user:
        raise ValueError("SSH-Host und SSH-Benutzer müssen gesetzt sein.")
    return f"{user}@{host}"


def known_hosts_path() -> Path:
    path = config.data_dir() / "known_hosts"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _pin_host_key(device: Device) -> bool:
    """Write the client-reported host key. Returns True when a key is pinned."""
    pubkey = " ".join((device.ssh_host_pubkey or "").split())
    host = (device.ssh_host or device.hostname or "").strip()
    if not pubkey or not host or any(ch in host for ch in " \t\r\n#|[]"):
        return False
    port = int(device.ssh_port or 22)
    marker = f"[{host}]:{port} "
    line = f"{marker}{pubkey}"
    path = known_hosts_path()
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    kept = [row for row in existing.splitlines() if row and not row.startswith(marker)]
    kept.append(line)
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return True


def ssh_argv(device: Device, remote_command: str) -> list[str]:
    pinned = _pin_host_key(device)
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts_path()}",
        "-o",
        "StrictHostKeyChecking=yes" if pinned else "StrictHostKeyChecking=accept-new",
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
        if not PACKAGE_NAME_RE.fullmatch(package_name):
            raise ValueError("unsafe package name")
        return f"bash -s -- {shlex.quote(package_name)} <<'KC_UPDATE'\n{LINUX_UPDATE_ONE}\nKC_UPDATE"
    return f"bash -s <<'KC_UPDATE'\n{LINUX_UPDATE_ALL}\nKC_UPDATE"
