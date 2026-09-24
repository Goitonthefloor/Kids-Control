"""Access policy: session allow/deny + blocked apps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db import AppRule, AppUsage, Child, DailyUsage, DayOverride, Override, Schedule

REASON_LABELS_DE = {
    "override": "Sonderfreigabe",
    "override-day": "Heute unbegrenzt",
    "schedule": "Zeitplan",
    "outside-time": "Außerhalb der Zeit",
    "no-schedule": "Kein Zeitplan",
    "unknown-child": "Unbekanntes Kind",
    "inactive": "Deaktiviert",
    "daily-limit-reached": "Tageslimit erreicht",
    "no-daily-minutes": "Kein Zugriff (0 Minuten)",
}


def as_aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def now_local(tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


def mins_now(tz: ZoneInfo) -> int:
    n = now_local(tz)
    return n.hour * 60 + n.minute


def fmt_remaining(seconds: int) -> str:
    seconds = max(0, seconds)
    m = seconds // 60
    h, mm = divmod(m, 60)
    if h > 0:
        return f"{h}h {mm}min"
    return f"{mm}min"


def fmt_hm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def in_window(start_min: int, end_min: int, now_min: int) -> bool:
    """True when now is inside the window. A window that passes midnight wraps."""
    if start_min == end_min:
        return False
    if start_min < end_min:
        return start_min <= now_min <= end_min
    return now_min >= start_min or now_min <= end_min


def minutes_until_end(start_min: int, end_min: int, now_min: int) -> int:
    if start_min < end_min:
        return max(0, end_min - now_min)
    if now_min >= start_min:
        return (24 * 60 - now_min) + end_min
    return max(0, end_min - now_min)


def apply_usage_tick(used_minutes: int, remainder_seconds: int, delta_seconds: float, *, max_gap: int = 180) -> tuple[int, int]:
    """Add elapsed seconds. Gaps longer than max_gap are ignored (the PC was off or asleep)."""
    if delta_seconds < 0 or delta_seconds > max_gap:
        delta_seconds = 0
    remainder = int(remainder_seconds) + int(delta_seconds)
    gained = remainder // 60
    return int(used_minutes) + gained, remainder % 60


def child_tz(child: Child) -> ZoneInfo:
    try:
        return ZoneInfo(child.timezone or "Europe/Berlin")
    except Exception:
        return ZoneInfo("Europe/Berlin")


def compute_session(db: Session, child: Child, *, tick_usage: bool = False) -> dict:
    """Decide whether the child may use a PC right now."""
    if not child.active:
        return {"allow": False, "reason": "inactive"}

    tz = child_tz(child)
    now_loc = now_local(tz)
    day = now_loc.date().isoformat()
    wd = now_loc.weekday()
    mnow = mins_now(tz)
    now_utc = datetime.now(timezone.utc)

    do = (
        db.query(DayOverride)
        .filter_by(child_id=child.id, day=day, enabled=True)
        .first()
    )
    if do:
        return {
            "allow": True,
            "reason": "override-day",
            "override_text": "Heute unbegrenzt",
            "remaining_minutes": None,
        }

    ov = (
        db.query(Override)
        .filter(Override.child_id == child.id)
        .order_by(Override.grant_until.desc())
        .first()
    )
    if ov:
        until = as_aware_utc(ov.grant_until)
        if until and until > now_utc:
            sec_left = int((until - now_utc).total_seconds())
            return {
                "allow": True,
                "reason": "override",
                "until": until.isoformat(),
                "override_seconds_left": sec_left,
                "override_text": f"Noch {fmt_remaining(sec_left)}",
                "remaining_minutes": max(0, sec_left // 60),
            }

    sched = db.query(Schedule).filter_by(child_id=child.id, weekday=wd).first()
    if not sched:
        return {"allow": False, "reason": "no-schedule"}

    start_min = int(sched.start_min)
    end_min = int(sched.end_min)
    limit = int(sched.daily_minutes or 0)

    if not in_window(start_min, end_min, mnow):
        return {
            "allow": False,
            "reason": "outside-time",
            "window_start_hm": fmt_hm(start_min),
            "window_end_hm": fmt_hm(end_min),
        }

    if limit <= 0:
        return {
            "allow": False,
            "reason": "no-daily-minutes",
            "daily_limit": 0,
            "daily_remaining": 0,
            "daily_used": 0,
        }

    cutoff = (now_loc.date() - timedelta(days=14)).isoformat()
    db.query(DailyUsage).filter(DailyUsage.day < cutoff).delete(synchronize_session=False)

    usage = db.query(DailyUsage).filter_by(child_id=child.id, day=day).first()
    if not usage:
        usage = DailyUsage(child_id=child.id, day=day, used_minutes=0, remainder_seconds=0, last_seen_at=now_utc)
        db.add(usage)
        db.flush()

    if tick_usage:
        last = as_aware_utc(usage.last_seen_at) or now_utc
        delta_seconds = (now_utc - last).total_seconds()
        used, remainder = apply_usage_tick(
            int(usage.used_minutes or 0),
            int(getattr(usage, "remainder_seconds", 0) or 0),
            delta_seconds,
        )
        usage.used_minutes = used
        usage.remainder_seconds = remainder
        usage.last_seen_at = now_utc
        db.flush()

    remaining = limit - int(usage.used_minutes)
    minutes_left_window = minutes_until_end(start_min, end_min, mnow)

    if remaining <= 0:
        return {
            "allow": False,
            "reason": "daily-limit-reached",
            "daily_used": int(usage.used_minutes),
            "daily_limit": limit,
            "daily_remaining": 0,
            "remaining_minutes": 0,
        }

    warn = bool(child.warn_minutes > 0 and 0 <= minutes_left_window <= int(child.warn_minutes))
    remaining_minutes = min(remaining, minutes_left_window)

    return {
        "allow": True,
        "reason": "schedule",
        "warn": warn,
        "minutes_left_window": minutes_left_window,
        "window_end_hm": fmt_hm(end_min),
        "daily_used": int(usage.used_minutes),
        "daily_limit": limit,
        "daily_remaining": remaining,
        "remaining_minutes": remaining_minutes,
    }


def _local_day(child: Child) -> str:
    return now_local(child_tz(child)).date().isoformat()


def usage_clock(db: Session, rule_id: int, day: str) -> tuple[int, int]:
    row = db.query(AppUsage).filter_by(rule_id=rule_id, day=day).first()
    if not row:
        return 0, 0
    return int(row.used_minutes or 0), int(row.remainder_seconds or 0)


def used_minutes_for(db: Session, rule_id: int, day: str) -> int:
    return usage_clock(db, rule_id, day)[0]


def quota_exhausted(db: Session, child: Child, rule: AppRule) -> bool:
    limit = int(rule.daily_minutes or 0)
    if limit <= 0:
        return True
    return used_minutes_for(db, rule.id, _local_day(child)) >= limit


def program_rows(db: Session, child: Child) -> list[dict]:
    day = _local_day(child)
    rows: list[dict] = []
    for rule in child.app_rules:
        used = used_minutes_for(db, rule.id, day) if rule.scope == "quota" else 0
        limit = int(rule.daily_minutes or 0)
        rows.append(
            {
                "id": rule.id,
                "label": rule.label,
                "pattern": rule.pattern,
                "match_mode": rule.match_mode,
                "scope": rule.scope,
                "enabled": rule.enabled,
                "daily_minutes": rule.daily_minutes,
                "used_minutes": used,
                "exhausted": bool(rule.enabled and rule.scope == "quota" and (limit <= 0 or used >= limit)),
            }
        )
    return rows


def tick_running_apps(db: Session, child: Child, running_ids: list) -> None:
    """Add elapsed time for quota programs the agent currently sees running."""
    wanted: set[int] = set()
    if isinstance(running_ids, list):
        for item in running_ids[:50]:
            try:
                wanted.add(int(item))
            except (TypeError, ValueError):
                continue
    tz = child_tz(child)
    today = now_local(tz).date()
    day = today.isoformat()
    now_utc = datetime.now(timezone.utc)
    cutoff = (today - timedelta(days=14)).isoformat()
    db.query(AppUsage).filter(AppUsage.child_id == child.id, AppUsage.day < cutoff).delete(synchronize_session=False)
    rules = (
        db.query(AppRule)
        .filter(AppRule.child_id == child.id, AppRule.enabled.is_(True), AppRule.scope == "quota")
        .all()
    )
    for rule in rules:
        usage = db.query(AppUsage).filter_by(rule_id=rule.id, day=day).first()
        if usage is None:
            db.add(
                AppUsage(
                    child_id=child.id,
                    rule_id=rule.id,
                    day=day,
                    used_minutes=0,
                    remainder_seconds=0,
                    last_seen_at=now_utc,
                )
            )
            db.flush()
            continue
        if rule.id in wanted:
            last = as_aware_utc(usage.last_seen_at) or now_utc
            used, remainder = apply_usage_tick(
                int(usage.used_minutes or 0),
                int(usage.remainder_seconds or 0),
                (now_utc - last).total_seconds(),
            )
            usage.used_minutes = used
            usage.remainder_seconds = remainder
        usage.last_seen_at = now_utc
    db.flush()


def active_quota_apps(db: Session, child: Child) -> list[dict]:
    day = _local_day(child)
    out: list[dict] = []
    rules = (
        db.query(AppRule)
        .filter(AppRule.child_id == child.id, AppRule.enabled.is_(True), AppRule.scope == "quota")
        .order_by(AppRule.id.asc())
        .all()
    )
    for rule in rules:
        limit = int(rule.daily_minutes or 0)
        used, remainder = usage_clock(db, rule.id, day)
        if limit <= 0 or used >= limit:
            continue
        remaining_seconds = max(0, limit * 60 - (used * 60 + max(0, remainder)))
        out.append(
            {
                "id": rule.id,
                "label": rule.label or rule.pattern,
                "pattern": rule.pattern,
                "match_mode": rule.match_mode,
                "daily_minutes": limit,
                "used_minutes": used,
                "remaining_seconds": remaining_seconds,
            }
        )
    return out


def list_blocked_apps(db: Session, child: Child, *, session_allowed: bool) -> list[dict]:
    rules = (
        db.query(AppRule)
        .filter(AppRule.child_id == child.id, AppRule.enabled.is_(True))
        .order_by(AppRule.id.asc())
        .all()
    )
    out: list[dict] = []
    for rule in rules:
        if rule.scope == "when_denied" and session_allowed:
            continue
        if rule.scope == "quota" and not quota_exhausted(db, child, rule):
            continue
        out.append(
            {
                "id": rule.id,
                "label": rule.label or rule.pattern,
                "pattern": rule.pattern,
                "match_mode": rule.match_mode,
                "scope": rule.scope,
            }
        )
    return out


def build_agent_policy(db: Session, child: Child, *, tick_usage: bool) -> dict:
    session = compute_session(db, child, tick_usage=tick_usage)
    allow = bool(session.get("allow"))
    reason = session.get("reason", "")
    blocked = list_blocked_apps(db, child, session_allowed=allow)
    return {
        "child": {"slug": child.slug, "display_name": child.display_name},
        "allow_session": allow,
        "reason": reason,
        "reason_label": REASON_LABELS_DE.get(reason, reason),
        "warn": bool(session.get("warn", False)),
        "remaining_minutes": session.get("remaining_minutes"),
        "override_text": session.get("override_text"),
        "daily_used": session.get("daily_used"),
        "daily_limit": session.get("daily_limit"),
        "daily_remaining": session.get("daily_remaining"),
        "minutes_left_window": session.get("minutes_left_window"),
        "window_end_hm": session.get("window_end_hm"),
        "blocked_apps": blocked,
        "quota_apps": active_quota_apps(db, child),
        "actions": {
            "lock_session_when_denied": True,
            "kill_blocked_apps": True,
        },
    }


SCHEDULE_PRESETS = {
    "Schule (Standard)": {
        i: {"start_min": 900, "end_min": 1110 if i < 4 else (1200 if i == 4 else 1320), "daily_minutes": 120 if i < 4 else (180 if i != 5 else 240)}
        for i in range(7)
    },
    "Ferien": {
        i: {"start_min": 600, "end_min": 1320 if i != 5 else 1380, "daily_minutes": 240 if i != 5 else 300}
        for i in range(7)
    },
    "Komplett gesperrt": {i: {"start_min": 0, "end_min": 0, "daily_minutes": 0} for i in range(7)},
}
