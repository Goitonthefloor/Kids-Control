"""Runtime configuration from the environment and data/server.env."""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "data"

_ENV_FILE_KEYS = (
    "KIDSCONTROL_ADMIN_USER",
    "KIDSCONTROL_ADMIN_PASSWORD",
    "KIDSCONTROL_SETUP_PASSWORD",
    "KIDSCONTROL_SECRET",
    "KIDSCONTROL_TZ",
    "KIDSCONTROL_DATA_DIR",
    "KIDSCONTROL_AGENT_POLL_SECONDS",
    "DATABASE_URL",
    "HOST",
    "PORT",
)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def data_dir() -> Path:
    raw = _env("KIDSCONTROL_DATA_DIR")
    path = Path(raw) if raw else DEFAULT_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def server_env_path() -> Path:
    return data_dir() / "server.env"


def parse_env_file(path: Path) -> dict[str, str]:
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


def load_server_env_into_process() -> None:
    """Fill empty process variables from data/server.env."""
    for key, value in parse_env_file(server_env_path()).items():
        if key in _ENV_FILE_KEYS and not os.getenv(key):
            os.environ[key] = value


def database_url() -> str:
    raw = _env("DATABASE_URL")
    if raw:
        return raw
    return f"sqlite:///{data_dir() / 'kidscontrol.sqlite3'}"


def admin_user() -> str:
    return _env("KIDSCONTROL_ADMIN_USER", "admin") or "admin"


def admin_password() -> str:
    return _env("KIDSCONTROL_ADMIN_PASSWORD")


def setup_password() -> str:
    return _env("KIDSCONTROL_SETUP_PASSWORD")


def secret() -> str:
    return _env("KIDSCONTROL_SECRET", "dev-secret-change-me")


def timezone_name() -> str:
    return _env("KIDSCONTROL_TZ", "Europe/Berlin") or "Europe/Berlin"


def host() -> str:
    return _env("HOST", "0.0.0.0") or "0.0.0.0"


def port() -> int:
    return int(_env("PORT", "8000") or "8000")


def agent_poll_seconds() -> int:
    return int(_env("KIDSCONTROL_AGENT_POLL_SECONDS", "30") or "30")


def is_configured() -> bool:
    return bool(admin_password()) and bool(setup_password())


def passwords_match(given: str, expected: str) -> bool:
    if not given or not expected:
        return False
    return secrets.compare_digest(
        hashlib.sha256(given.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )


def __getattr__(name: str):
    mapping = {
        "SECRET": secret,
        "ADMIN_USER": admin_user,
        "ADMIN_PASSWORD": admin_password,
        "SETUP_PASSWORD": setup_password,
        "TIMEZONE": timezone_name,
        "HOST": host,
        "PORT": port,
        "AGENT_POLL_SECONDS": agent_poll_seconds,
    }
    if name in mapping:
        return mapping[name]()
    raise AttributeError(name)


load_server_env_into_process()
