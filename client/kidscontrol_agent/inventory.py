"""Collect installed package versions and pending upgrades."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from kidscontrol_agent.enforce import detect_os

_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,80}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:~-]{0,79}$")
_SOURCE_RE = re.compile(r"^[A-Za-z0-9._+-]{1,32}$")
_APT_UP = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._+-]*)/\S+\s+(\S+)\s+\S+\s+\[upgradable from:\s*([^\]]+)\]\s*$"
)
_PACMAN_QU = re.compile(r"^(\S+)\s+(\S+)\s+->\s+(\S+)\s*$")
_BREW_VERBOSE = re.compile(r"^(\S+)\s+\(([^)]+)\)\s+<\s+(\S+)\s*$")
_DNF_ARCH = {"x86_64", "aarch64", "noarch", "i686", "i386", "armhfp", "ppc64le", "s390x"}

CACHE = Path.home() / ".cache" / "kidscontrol" / "watches.json"
QUOTA_CACHE = Path.home() / ".cache" / "kidscontrol" / "quota_apps.json"
PENDING_CACHE = Path.home() / ".cache" / "kidscontrol" / "pending.json"
PENDING_TTL_SECONDS = 15 * 60


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


def load_cached_quota() -> list[dict]:
    if not QUOTA_CACHE.is_file():
        return []
    try:
        data = json.loads(QUOTA_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data:
        if isinstance(item, dict) and item.get("pattern"):
            out.append(item)
    return out


def save_cached_quota(rules: list) -> None:
    clean: list[dict] = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        try:
            rule_id = int(rule.get("id"))
        except (TypeError, ValueError):
            continue
        pattern = str(rule.get("pattern") or "").strip()
        if not pattern:
            continue
        mode = str(rule.get("match_mode") or "contains")
        if mode not in {"contains", "exact", "startswith"}:
            mode = "contains"
        clean.append({"id": rule_id, "pattern": pattern, "match_mode": mode})
    QUOTA_CACHE.parent.mkdir(parents=True, exist_ok=True)
    QUOTA_CACHE.write_text(json.dumps(clean), encoding="utf-8")


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

    if package_name and not _PACKAGE_RE.fullmatch(package_name):
        return "failed", "Paketname ist nicht erlaubt"

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
            flag = "--id" if "." in package_name else "--name"
            cmd = ["winget", "upgrade", flag, package_name, "--accept-source-agreements", "--accept-package-agreements"]
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


def _version_ok(value: str) -> bool:
    return bool(_VERSION_RE.fullmatch(value)) and any(ch.isdigit() for ch in value)


def _safe_pending(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        name = str(item.get("name") or "").strip()
        if not _PACKAGE_RE.fullmatch(name) or name in seen:
            continue
        available = str(item.get("available") or "").strip()
        if not _version_ok(available):
            continue
        version = str(item.get("version") or "").strip()
        if version and not _version_ok(version):
            version = ""
        source = str(item.get("source") or "unknown").strip() or "unknown"
        if not _SOURCE_RE.fullmatch(source):
            source = "unknown"
        seen.add(name)
        out.append({"name": name, "version": version, "available": available, "source": source})
    return out


def parse_apt_upgradable(text: str) -> list[dict]:
    items: list[dict] = []
    for line in text.splitlines():
        match = _APT_UP.match(line.strip())
        if not match:
            continue
        items.append(
            {
                "name": match.group(1),
                "version": match.group(3).strip(),
                "available": match.group(2).strip(),
                "source": "apt",
            }
        )
    return _safe_pending(items)


def parse_dnf_check_update(text: str) -> list[dict]:
    items: list[dict] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        raw = parts[0]
        name = raw
        if "." in raw:
            base, arch = raw.rsplit(".", 1)
            if arch in _DNF_ARCH and base:
                name = base
        items.append({"name": name, "version": "", "available": parts[1], "source": "dnf"})
    return _safe_pending(items)


def parse_pacman_qu(text: str) -> list[dict]:
    items: list[dict] = []
    for line in text.splitlines():
        match = _PACMAN_QU.match(line.strip())
        if not match:
            continue
        items.append(
            {
                "name": match.group(1),
                "version": match.group(2),
                "available": match.group(3),
                "source": "pacman",
            }
        )
    return _safe_pending(items)


def _header_spans(header: str) -> list[tuple[int, int, str]]:
    words = list(re.finditer(r"\S+", header))
    spans: list[tuple[int, int, str]] = []
    for index, word in enumerate(words):
        start = word.start()
        end = words[index + 1].start() if index + 1 < len(words) else max(len(header), start + 1)
        spans.append((start, end, word.group()))
    return spans


def _is_rule(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 3:
        return False
    dashes = stripped.count("-")
    return dashes >= 3 and set(stripped) <= {"-", " "}


def _winget_header(labels: list[str]) -> bool:
    lowered = [label.lower() for label in labels]
    has_version = "version" in lowered
    has_offer = "available" in lowered or "verfügbar" in lowered or "id" in lowered
    return has_version and has_offer and len(lowered) >= 3


def parse_winget_upgrade(text: str) -> list[dict]:
    lines = text.splitlines()
    items: list[dict] = []
    index = 0
    while index < len(lines) - 1:
        spans = _header_spans(lines[index])
        labels = [label for _start, _end, label in spans]
        if not _winget_header(labels) or not _is_rule(lines[index + 1]):
            index += 1
            continue
        index += 2
        while index < len(lines) and lines[index].strip():
            row: dict[str, str] = {}
            for column, (start, end, label) in enumerate(spans):
                chunk = lines[index][start:] if column == len(spans) - 1 else lines[index][start:end]
                row[label.lower()] = chunk.strip()
            package_id = row.get("id") or ""
            available = row.get("available") or row.get("verfügbar") or ""
            if available.lower() in {"unknown", "unbekannt"}:
                available = ""
            items.append(
                {
                    "name": package_id,
                    "version": row.get("version") or "",
                    "available": available,
                    "source": "winget",
                }
            )
            index += 1
    return _safe_pending(items)


def parse_brew_outdated(text: str) -> list[dict]:
    items: list[dict] = []
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            for key in ("formulae", "casks"):
                for row in data.get(key) or []:
                    if not isinstance(row, dict):
                        continue
                    installed = row.get("installed_versions") or []
                    current = str(row.get("current_version") or row.get("current") or "")
                    version = str(installed[-1]) if installed else ""
                    items.append(
                        {
                            "name": str(row.get("name") or ""),
                            "version": version,
                            "available": current,
                            "source": "brew",
                        }
                    )
            return _safe_pending(items)
    for line in text.splitlines():
        match = _BREW_VERBOSE.match(line.strip())
        if not match:
            continue
        items.append(
            {
                "name": match.group(1),
                "version": match.group(2).strip(),
                "available": match.group(3).strip(),
                "source": "brew",
            }
        )
    return _safe_pending(items)


def _run_checked(cmd: list[str], *, timeout: int = 40) -> str | None:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except Exception:
        return None
    return proc.stdout or ""


def _collect_pending(os_name: str) -> list[dict] | None:
    if os_name == "linux":
        if shutil.which("apt"):
            text = _run_checked(["apt", "list", "--upgradable"], timeout=40)
            return None if text is None else parse_apt_upgradable(text)
        if shutil.which("dnf"):
            text = _run_checked(["dnf", "check-update", "-q"], timeout=60)
            return None if text is None else parse_dnf_check_update(text)
        if shutil.which("pacman"):
            text = _run_checked(["pacman", "-Qu"], timeout=40)
            return None if text is None else parse_pacman_qu(text)
        return []
    if os_name == "windows":
        if not shutil.which("winget"):
            return []
        text = _run_checked(["winget", "upgrade", "--accept-source-agreements"], timeout=60)
        return None if text is None else parse_winget_upgrade(text)
    if os_name == "macos":
        if not shutil.which("brew"):
            return []
        text = _run_checked(["brew", "outdated", "--verbose"], timeout=40)
        return None if text is None else parse_brew_outdated(text)
    return []


def cached_pending_updates() -> list[dict] | None:
    if not PENDING_CACHE.is_file():
        return None
    try:
        data = json.loads(PENDING_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    return _safe_pending([item for item in items if isinstance(item, dict)])


def _pending_cache_fresh() -> bool:
    if not PENDING_CACHE.is_file():
        return False
    try:
        data = json.loads(PENDING_CACHE.read_text(encoding="utf-8"))
        stamp = float(data.get("at") or 0)
    except Exception:
        return False
    return time.time() - stamp < PENDING_TTL_SECONDS


def refresh_pending_updates() -> None:
    try:
        if _pending_cache_fresh():
            return
        items = _collect_pending(detect_os())
        if items is None:
            return
        PENDING_CACHE.parent.mkdir(parents=True, exist_ok=True)
        PENDING_CACHE.write_text(
            json.dumps({"at": time.time(), "items": _safe_pending(items)}),
            encoding="utf-8",
        )
    except Exception:
        return
