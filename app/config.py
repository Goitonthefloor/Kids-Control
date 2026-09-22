"""Runtime configuration from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "data"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def data_dir() -> Path:
    raw = _env("KIDSCONTROL_DATA_DIR")
    path = Path(raw) if raw else DEFAULT_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_url() -> str:
    raw = _env("DATABASE_URL")
    if raw:
        return raw
    return f"sqlite:///{data_dir() / 'kidscontrol.sqlite3'}"


SECRET = _env("KIDSCONTROL_SECRET", "dev-secret-change-me")
ADMIN_USER = _env("KIDSCONTROL_ADMIN_USER", "admin")
ADMIN_PASSWORD = _env("KIDSCONTROL_ADMIN_PASSWORD", "admin")
TIMEZONE = _env("KIDSCONTROL_TZ", "Europe/Berlin")
HOST = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "8000") or "8000")
AGENT_POLL_SECONDS = int(_env("KIDSCONTROL_AGENT_POLL_SECONDS", "30") or "30")
