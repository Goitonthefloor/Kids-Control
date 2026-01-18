from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.exc import IntegrityError

from app.db import Child, Schedule, Override, ChildPolicy, PrewarnLog, DailyUsage, DayOverride


def as_aware_utc(dt):
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def now_local(tz: ZoneInfo):
    return datetime.now(tz)

def mins_now(tz: ZoneInfo) -> int:
    n = now_local(tz)
    return n.hour * 60 + n.minute

def fmt_hm_from_minutes(m: int) -> str:
    h = m // 60
    mm = m % 60
    return f"{h:02d}:{mm:02d}"

def fmt_remaining(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    m = seconds // 60
    h = m // 60
    mm = m % 60
    if h > 0:
        return f"{h}h {mm}min"
    return f"{mm}min"

def compute_access(db, user: str, tz: ZoneInfo, include_debug: bool = False) -> dict:
    child = db.query(Child).filter_by(username=user).first()
    if not child:
        return {"allow": False, "reason": "unknown-user"}

    now_loc = now_local(tz)
    day = now_loc.date().isoformat()
    wd = now_loc.weekday()
    mnow = mins_now(tz)
    now_utc = datetime.now(timezone.utc)

    dbg = {"tz_now": now_loc.isoformat(), "weekday": wd, "mins_now": mnow, "day": day}

    # Day override (bool toggle for today)
    do = db.query(DayOverride).filter_by(username=user, day=day, enabled=True).first()
    if do:
        out = {"allow": True, "reason": "override-day", "override_text": "Heute unbegrenzt"}
        if include_debug:
            out["debug"] = dbg
        return out

    # Hour override (latest active)
    ov = (
        db.query(Override)
        .filter(Override.username == user)
        .order_by(Override.grant_until.desc())
        .first()
    )
    if ov:
        until = as_aware_utc(ov.grant_until)
        if until and until > now_utc:
            sec_left = int((until - now_utc).total_seconds())
            out = {
                "allow": True,
                "reason": "override",
                "until": until.isoformat(),
                "override_seconds_left": sec_left,
                "override_text": f"Noch {fmt_remaining(sec_left)}",
            }
            if include_debug:
                dbg["override_until"] = until.isoformat()
                dbg["override_seconds_left"] = sec_left
                out["debug"] = dbg
            return out

    # Schedule
    sched = db.query(Schedule).filter_by(username=user, weekday=wd).first()
    if not sched:
        out = {"allow": False, "reason": "no-schedule"}
        if include_debug:
            out["debug"] = dbg
        return out

    start_min = int(sched.start_min)
    end_min = int(sched.end_min)
    limit = int(sched.daily_minutes or 0)

    dbg["start_min"] = start_min
    dbg["end_min"] = end_min
    dbg["daily_minutes"] = limit

    if not (start_min <= mnow <= end_min):
        out = {"allow": False, "reason": "outside-time"}
        if include_debug:
            out["debug"] = dbg
        return out

    # Daily minutes (0 => kein Zugriff)
    if limit <= 0:
        out = {"allow": False, "reason": "no-daily-minutes", "daily_limit": 0, "daily_remaining": 0, "daily_used": 0}
        if include_debug:
            out["debug"] = dbg
        return out

    # cleanup old rows
    cutoff = (now_loc.date() - timedelta(days=14)).isoformat()
    db.query(DailyUsage).filter(DailyUsage.day < cutoff).delete(synchronize_session=False)
    db.commit()

    # store last_seen_at as naive UTC (SQLite-safe)
    now_utc_naive = datetime.utcnow()
    usage = db.query(DailyUsage).filter_by(username=user, day=day).first()
    if not usage:
        usage = DailyUsage(username=user, day=day, used_minutes=0, last_seen_at=now_utc_naive)
        db.add(usage)
        db.commit()
        db.refresh(usage)

    last = usage.last_seen_at
    if getattr(last, "tzinfo", None) is not None:
        last = last.astimezone(timezone.utc).replace(tzinfo=None)

    delta_min = int((now_utc_naive - last).total_seconds() // 60)
    if delta_min < 0:
        delta_min = 0
    if delta_min > 2:
        delta_min = 0

    if delta_min > 0:
        usage.used_minutes += delta_min
        usage.last_seen_at = now_utc_naive
        db.commit()

    remaining = limit - int(usage.used_minutes)
    minutes_left_window = end_min - mnow

    if remaining <= 0:
        out = {
            "allow": False,
            "reason": "daily-limit-reached",
            "daily_used": int(usage.used_minutes),
            "daily_limit": limit,
            "daily_remaining": 0,
        }
        if include_debug:
            dbg["daily_used"] = int(usage.used_minutes)
            dbg["daily_remaining"] = 0
            out["debug"] = dbg
        return out

    # Prewarn
    policy = db.query(ChildPolicy).filter_by(username=user).first()
    warn_minutes = int(policy.warn_minutes) if policy else 10
    mode = policy.after_expiry_mode if policy else "LOCK"

    warn = False
    if warn_minutes > 0 and 0 <= minutes_left_window <= warn_minutes:
        warn = True
        try:
            db.add(PrewarnLog(username=user, day=day, mode=mode, shown_at=now_loc.isoformat()))
            db.commit()
        except IntegrityError:
            db.rollback()

    out = {
        "allow": True,
        "reason": "schedule",
        "warn": warn,
        "minutes_left_window": minutes_left_window,
        "window_end_hm": fmt_hm_from_minutes(end_min),
        "daily_used": int(usage.used_minutes),
        "daily_limit": limit,
        "daily_remaining": remaining,
    }
    if include_debug:
        dbg["daily_used"] = int(usage.used_minutes)
        dbg["daily_remaining"] = remaining
        dbg["warn_minutes"] = warn_minutes
        dbg["warn"] = warn
        out["debug"] = dbg
    return out
