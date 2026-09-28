"""Last policy cache and the fail-closed rules used when the hub is unreachable."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

OFFLINE_REASON = "offline"
OFFLINE_LABEL = "Server nicht erreichbar"


def policy_cache_path() -> Path:
    override = os.getenv("KIDSCONTROL_POLICY_CACHE", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".cache" / "kidscontrol" / "policy.json"


def _clean_rules(rules: object) -> list[dict]:
    out: list[dict] = []
    if not isinstance(rules, list):
        return out
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        pattern = str(rule.get("pattern") or "").strip()
        if not pattern:
            continue
        mode = str(rule.get("match_mode") or "contains")
        if mode not in {"contains", "exact", "startswith"}:
            mode = "contains"
        item = {
            "pattern": pattern,
            "match_mode": mode,
            "label": str(rule.get("label") or pattern),
        }
        if rule.get("id") is not None:
            item["id"] = rule.get("id")
        out.append(item)
    return out


def save_cached_policy(policy: dict) -> None:
    """Persist the enforcement fields from a successful sync. Commands are omitted."""
    payload = {
        "child": policy.get("child") if isinstance(policy.get("child"), dict) else {},
        "allow_session": bool(policy.get("allow_session")),
        "blocked_apps": _clean_rules(policy.get("blocked_apps")),
        "quota_apps": _clean_rules(policy.get("quota_apps")),
        "actions": policy.get("actions") if isinstance(policy.get("actions"), dict) else {},
    }
    path = policy_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        os.chmod(path, 0o600)
    except OSError as exc:
        print(f"Policy-Cache nicht geschrieben: {exc}", file=sys.stderr)


def load_cached_policy() -> dict | None:
    path = policy_cache_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def offline_policy() -> dict:
    """Deny the session when the hub cannot be reached.

    Blocked apps from the last successful sync are still stopped. Quota apps
    are stopped too: their remaining time cannot be trusted without the hub.
    With no cache, the session is locked and no extra apps are killed.
    """
    cached = load_cached_policy() or {}
    blocked = _clean_rules(cached.get("blocked_apps"))
    seen = {(rule["pattern"], rule["match_mode"]) for rule in blocked}
    for rule in _clean_rules(cached.get("quota_apps")):
        key = (rule["pattern"], rule["match_mode"])
        if key in seen:
            continue
        blocked.append(rule)
        seen.add(key)
    child = cached.get("child") if isinstance(cached.get("child"), dict) else {}
    return {
        "child": child,
        "allow_session": False,
        "reason": OFFLINE_REASON,
        "reason_label": OFFLINE_LABEL,
        "warn": False,
        "blocked_apps": blocked,
        "quota_apps": [],
        "actions": {
            "lock_session_when_denied": True,
            "kill_blocked_apps": True,
        },
    }
