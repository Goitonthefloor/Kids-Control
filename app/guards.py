"""Small request guards: local setup, safe redirects, login throttling."""

from __future__ import annotations

import time
from urllib.parse import urlparse

_failures: dict[str, list[float]] = {}


def is_local_client(host: str | None) -> bool:
    """True for loopback and the ASGI test client. Remote peers are rejected."""
    return (host or "") in {"127.0.0.1", "::1", "localhost", "testclient"}


def safe_redirect_target(target: str | None, default: str = "/dashboard") -> str:
    """Only same-site relative paths. Blocks absolute and protocol-relative URLs."""
    if not target:
        return default
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return default
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return default
    if "\n" in target or "\r" in target:
        return default
    return target


def too_many_failures(key: str, *, limit: int = 8, window_seconds: int = 300) -> bool:
    now = time.monotonic()
    recent = [stamp for stamp in _failures.get(key, []) if now - stamp < window_seconds]
    _failures[key] = recent
    return len(recent) >= limit


def record_failure(key: str) -> None:
    _failures.setdefault(key, []).append(time.monotonic())


def clear_failures(key: str) -> None:
    _failures.pop(key, None)
