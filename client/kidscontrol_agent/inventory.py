"""Collect installed package versions for a watch list."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from kidscontrol_agent.enforce import detect_os

CACHE = Path.home() / ".cache" / "kidscontrol" / "watches.json"


def load_cached_watches() -> list[str]:
    if not CACHE.is_file():
        return []
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [str(x) for x in data if str(x).strip()]
    return []


def save_cached_watches(names: list[str]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(sorted(set(names))), encoding="utf-8")


def query_versions(names: list[str]) -> list[dict]:
    os_name = detect_os()
    out: list[dict] = []
    for name in names:
        version, source = _lookup(os_name, name)
        out.append({"name": name, "version": version, "source": source})
    return out


def _lookup(os_name: str, name: str) -> tuple[str, str]:
    if os_name == "linux":
        return _lookup_linux(name)
    if os_name == "macos":
        return _lookup_brew(name)
    if os_name == "windows":
        return _lookup_winget(name)
    return "", "unknown"


def _run(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    except Exception:
        return ""
    return (proc.stdout or "").strip()


def _lookup_linux(name: str) -> tuple[str, str]:
    dpkg = _run(["dpkg-query", "-W", "-f", "${Version}", name])
    if dpkg and "no packages found" not in dpkg.lower():
        return dpkg.splitlines()[0], "apt"
    rpm = _run(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}", name])
    if rpm and not rpm.startswith("package ") and "not installed" not in rpm:
        return rpm.splitlines()[0], "rpm"
    pac = _run(["pacman", "-Q", name])
    if pac and "error" not in pac.lower():
        parts = pac.split()
        if len(parts) >= 2:
            return parts[1], "pacman"
    return "", "linux"


def _lookup_brew(name: str) -> tuple[str, str]:
    text = _run(["brew", "list", "--versions", name])
    if not text:
        return "", "brew"
    parts = text.split()
    if len(parts) >= 2:
        return parts[-1], "brew"
    return "", "brew"


def _lookup_winget(name: str) -> tuple[str, str]:
    text = _run(["winget", "list", "--name", name, "--accept-source-agreements"])
    for line in text.splitlines():
        if name.lower() in line.lower() and "name" not in line.lower():
            cols = line.split()
            if len(cols) >= 2:
                return cols[-2], "winget"
    return "", "winget"


def _linux_sudo() -> str:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return ""
    return "sudo -n "


def run_update(package_name: str | None, *, dry_run: bool = False) -> tuple[str, str]:
    """Return (status, output). status is done|failed."""
    os_name = detect_os()
    if dry_run:
        target = package_name or "ALL"
        return "done", f"dry-run update {target} on {os_name}"

    if os_name == "linux":
        sudo = _linux_sudo()
        if package_name:
            script = (
                "set -eu; pkg=\"$1\"; "
                f"if command -v apt-get >/dev/null; then {sudo}apt-get update && {sudo}apt-get install -y --only-upgrade \"$pkg\"; "
                f"elif command -v dnf >/dev/null; then {sudo}dnf upgrade -y \"$pkg\"; "
                f"elif command -v pacman >/dev/null; then {sudo}pacman -Syu --noconfirm \"$pkg\"; "
                "else echo 'kein Paketmanager'; exit 3; fi"
            )
            cmd = ["bash", "-lc", script, "kc-update", package_name]
        else:
            script = (
                "set -eu; "
                f"if command -v apt-get >/dev/null; then {sudo}apt-get update && {sudo}apt-get upgrade -y; "
                f"elif command -v dnf >/dev/null; then {sudo}dnf upgrade -y; "
                f"elif command -v pacman >/dev/null; then {sudo}pacman -Syu --noconfirm; "
                "else echo 'kein Paketmanager'; exit 3; fi"
            )
            cmd = ["bash", "-lc", script]
    elif os_name == "macos":
        if package_name:
            cmd = ["brew", "upgrade", package_name]
        else:
            cmd = ["brew", "upgrade"]
    elif os_name == "windows":
        if package_name:
            cmd = ["winget", "upgrade", "--name", package_name, "--accept-source-agreements", "--accept-package-agreements"]
        else:
            cmd = ["winget", "upgrade", "--all", "--accept-source-agreements", "--accept-package-agreements"]
    else:
        return "failed", f"OS {os_name} nicht unterstützt"

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except Exception as exc:
        return "failed", str(exc)
    text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[-4000:]
    return ("done" if proc.returncode == 0 else "failed"), text
