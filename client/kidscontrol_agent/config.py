"""Load agent configuration from env file or process environment."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_ENV_PATHS = [
    Path.cwd() / "client.env",
    Path("/etc/kidscontrol/client.env"),
    Path.home() / ".config" / "kidscontrol" / "client.env",
]


def _parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def load_config(env_path: str | None = None) -> dict:
    file_env: dict[str, str] = {}
    if env_path:
        file_env = _parse_env_file(Path(env_path))
    else:
        for candidate in DEFAULT_ENV_PATHS:
            if candidate.is_file():
                file_env = _parse_env_file(candidate)
                break

    def get(name: str, default: str = "") -> str:
        return (os.getenv(name) or file_env.get(name) or default).strip()

    server = get("KIDSCONTROL_SERVER", "http://127.0.0.1:8000").rstrip("/")
    device_key = get("KIDSCONTROL_DEVICE_KEY")
    poll = int(get("KIDSCONTROL_POLL_SECONDS", "30") or "30")
    dry_run = get("KIDSCONTROL_DRY_RUN", "0") in {"1", "true", "yes"}
    return {
        "server": server,
        "device_key": device_key,
        "poll_seconds": max(5, poll),
        "dry_run": dry_run,
    }
