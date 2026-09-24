"""One notice each when a running program has 5, 2, or 1 minute left."""

from __future__ import annotations

import json
from pathlib import Path

from kidscontrol_agent.enforce import notify, running_rule_ids

WARN_LEVELS = (5, 2, 1)
WARN_CACHE = Path.home() / ".cache" / "kidscontrol" / "quota_warnings.json"


def remaining_whole_minutes(remaining_seconds: int) -> int:
    if remaining_seconds <= 0:
        return 0
    return (int(remaining_seconds) + 59) // 60


def quota_warning(remaining_seconds: int, sent: set[int]) -> tuple[int, int] | None:
    """Return (level, spoken minutes) for a notice that has not been shown yet."""
    minutes = remaining_whole_minutes(remaining_seconds)
    if minutes <= 0 or minutes > 5:
        return None
    if minutes in WARN_LEVELS and minutes not in sent:
        return minutes, minutes
    if minutes > 2 and 5 not in sent:
        return 5, minutes
    if minutes < 2 and 1 not in sent:
        return 1, minutes
    return None


def quota_warning_text(label: str, minutes: int) -> str:
    unit = "Minute" if minutes == 1 else "Minuten"
    return f"{label}: noch {minutes} {unit}"


def _load_sent() -> dict[str, list[int]]:
    if not WARN_CACHE.is_file():
        return {}
    try:
        data = json.loads(WARN_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _save_sent(state: dict[str, list[int]]) -> None:
    WARN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    WARN_CACHE.write_text(json.dumps(state), encoding="utf-8")


def warn_running_quotas(quota_apps: list[dict], *, dry_run: bool = False) -> list[str]:
    running = set(running_rule_ids(quota_apps or []))
    state = _load_sent()
    seen: set[int] = set()
    messages: list[str] = []
    for app in quota_apps or []:
        if not isinstance(app, dict):
            continue
        try:
            rule_id = int(app.get("id"))
            remaining = int(app.get("remaining_seconds") or 0)
        except (TypeError, ValueError):
            continue
        seen.add(rule_id)
        key = str(rule_id)
        if remaining_whole_minutes(remaining) > 5:
            state.pop(key, None)
            continue
        if rule_id not in running:
            continue
        sent: set[int] = set()
        for level in state.get(key) or []:
            try:
                sent.add(int(level))
            except (TypeError, ValueError):
                continue
        chosen = quota_warning(remaining, sent)
        if chosen is None:
            continue
        level, spoken = chosen
        label = str(app.get("label") or app.get("pattern") or "Programm")
        text = quota_warning_text(label, spoken)
        notify("KidsControl", text, dry_run=dry_run)
        print(f"[quota] {text}")
        messages.append(text)
        sent.update(item for item in WARN_LEVELS if item >= level)
        state[key] = sorted(sent)
    for key in list(state):
        try:
            if int(key) not in seen:
                state.pop(key, None)
        except (TypeError, ValueError):
            state.pop(key, None)
    _save_sent(state)
    return messages
