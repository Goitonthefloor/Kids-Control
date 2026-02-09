from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
import os

from app.db import (
    SessionLocal,
    init_db,
    User,
    Child,
    Schedule,
    Override,
    ChildPolicy,
    PrewarnLog,
    DailyUsage,
    DayOverride,
)

from app.auth import authenticate_user
from app.policy import compute_access, as_aware_utc
from app.ui import (
    css_block,
    REASON_MAP_DE,
    render_login_page,
    render_dashboard,
    render_trace,
    render_schedule_editor,
    render_child_view,
)
from app.profiles import (
    ensure_profile_dir,
    list_profiles,
    load_profile,
    save_profile,
    PRESETS,
)

TZ = ZoneInfo("Europe/Berlin")
SECRET = os.getenv("KIDSCONTROL_SECRET", "dev-secret-change-me")

CHILD_VIEW_TOKEN = os.getenv("KIDSCONTROL_CHILD_VIEW_TOKEN", "")
WIDGET_TOKEN = os.getenv("KIDSCONTROL_WIDGET_TOKEN", "")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET)


def now_local() -> datetime:
    return datetime.now(TZ)

def logged_in(request: Request) -> str | None:
    return request.session.get("user")

def require_admin(request: Request):
    u = logged_in(request)
    if not u:
        return RedirectResponse("/login", status_code=302)
    
    # Check if user is admin
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(username=u, is_active=True).first()
        if not user or not user.is_admin:
            return RedirectResponse("/login", status_code=302)
    finally:
        db.close()
    
    return None


def _widget_remaining_minutes(state: dict) -> int | None:
    candidates = []
    for key in ("minutes_left_window", "daily_remaining"):
        value = state.get(key)
        if isinstance(value, int):
            candidates.append(value)
    if not candidates:
        return None
    return max(0, min(candidates))


def _widget_remaining_label(state: dict) -> str | None:
    reason = state.get("reason", "")
    if reason == "override-day":
        return "Unbegrenzt"
    if reason == "override":
        return str(state.get("override_text") or "Sonderfreigabe")
    remaining = _widget_remaining_minutes(state)
    if remaining is None:
        return None
    return f"Noch {remaining} Min"


def _widget_reason_label(reason: str) -> str:
    if not reason:
        return ""
    return REASON_MAP_DE.get(reason, reason)


@app.on_event("startup")
def _startup():
    init_db()
    ensure_profile_dir()


@app.get("/healthz")
def healthz():
    return {"ok": True}


# =========================
# AUTH
# =========================
@app.get("/login")
def login_page():
    return HTMLResponse(render_login_page(css_block(), "admin"))

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    try:
        if authenticate_user(db, username, password):
            # Update last login
            user = db.query(User).filter_by(username=username).first()
            if user:
                user.last_login = datetime.now(timezone.utc)
                db.commit()
            
            request.session["user"] = username
            return RedirectResponse("/", status_code=302)
        else:
            return HTMLResponse(
                render_login_page(css_block(), username, error="Ungültige Anmeldedaten"),
                status_code=401,
            )
    finally:
        db.close()

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# =========================
# DASHBOARD
# =========================
@app.get("/")
def dashboard(request: Request):
    r = require_admin(request)
    if r:
        return r

    db = SessionLocal()
    try:
        kids = db.query(Child).order_by(Child.username.asc()).all()
        html = render_dashboard(css_block(), kids, logged_in(request))
        return HTMLResponse(html)
    finally:
        db.close()


# =========================
# CHILD VIEW
# =========================
@app.get("/child/{user}")
def child_view(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r

    db = SessionLocal()
    try:
        state = compute_access(db, user=user, tz=TZ, include_debug=True)
        html = render_child_view(css_block(), user, state)
        return HTMLResponse(html)
    finally:
        db.close()


@app.get("/trace/{user}")
def trace_view(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r

    db = SessionLocal()
    try:
        html = render_trace(css_block(), db, user, tz=TZ)
        return HTMLResponse(html)
    finally:
        db.close()


@app.get("/api/admin/usage/{user}")
def api_admin_usage(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r

    db = SessionLocal()
    try:
        rows = (
            db.query(DailyUsage)
            .filter_by(username=user)
            .order_by(DailyUsage.day.desc())
            .limit(30)
            .all()
        )
        return JSONResponse(
            [{"day": x.day, "used_minutes": x.used_minutes, "last_seen_at": str(x.last_seen_at)} for x in rows]
        )
    finally:
        db.close()

@app.post("/api/admin/reset-daily/{user}")
def api_admin_reset_daily(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r
    db = SessionLocal()
    try:
        day = now_local().date().isoformat()
        db.query(DailyUsage).filter_by(username=user, day=day).delete(synchronize_session=False)
        db.commit()
        return JSONResponse({"ok": True, "user": user, "day": day})
    finally:
        db.close()


@app.get("/api/widget/status")
def api_widget_status(t: str | None = None):
    if WIDGET_TOKEN and t != WIDGET_TOKEN:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    db = SessionLocal()
    try:
        kids = db.query(Child).order_by(Child.username.asc()).all()
        payload = []
        for k in kids:
            state = compute_access(db, user=k.username, tz=TZ, include_debug=False)
            payload.append(
                {
                    "username": k.username,
                    "display_name": k.display_name or k.username,
                    "allow": bool(state.get("allow")),
                    "reason": state.get("reason", ""),
                    "reason_label": _widget_reason_label(state.get("reason", "")),
                    "warn": bool(state.get("warn", False)),
                    "remaining_minutes": _widget_remaining_minutes(state),
                    "remaining_label": _widget_remaining_label(state),
                    "daily_remaining": state.get("daily_remaining"),
                    "daily_limit": state.get("daily_limit"),
                    "minutes_left_window": state.get("minutes_left_window"),
                    "override_text": state.get("override_text"),
                }
            )
        return JSONResponse({"server_time": now_local().isoformat(), "kids": payload})
    finally:
        db.close()


# =========================
# UI ACTIONS
# =========================
@app.post("/grant/{user}/hour")
def grant_hour(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r

    db = SessionLocal()
    try:
        from datetime import timedelta

        now = datetime.now(timezone.utc)

        last = (
            db.query(Override)
            .filter(Override.username == user, Override.grant_type == "HOUR")
            .order_by(Override.grant_until.desc())
            .first()
        )

        last_until = as_aware_utc(last.grant_until) if last else None
        base = last_until if (last_until and last_until > now) else now
        until = base + timedelta(hours=1)

        override = Override(
            username=user,
            grant_until=until,
            grant_type="HOUR",
            created_by=logged_in(request) or "admin",
            created_at=now,
        )
        db.add(override)
        db.commit()

        return RedirectResponse(f"/child/{user}", status_code=302)
    finally:
        db.close()


@app.post("/grant/{user}/day")
def grant_day(request: Request, user: str, enable: str = Form("1")):
    r = require_admin(request)
    if r:
        return r

    db = SessionLocal()
    try:
        day = now_local().date().isoformat()
        do = db.query(DayOverride).filter_by(username=user, day=day).first()

        enable_bool = enable == "1"
        now = datetime.now(timezone.utc)

        if not do:
            do = DayOverride(username=user, day=day, enabled=enable_bool, updated_at=now)
            db.add(do)
        else:
            do.enabled = enable_bool
            do.updated_at = now

        db.commit()
        return RedirectResponse(f"/child/{user}", status_code=302)
    finally:
        db.close()


# =========================
# SCHEDULE EDITOR
# =========================
@app.get("/schedule/{user}")
def schedule_view(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r

    db = SessionLocal()
    try:
        schedules = db.query(Schedule).filter_by(username=user).order_by(Schedule.weekday).all()
        html = render_schedule_editor(css_block(), user, schedules)
        return HTMLResponse(html)
    finally:
        db.close()


@app.post("/schedule/{user}")
def schedule_save(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r

    db = SessionLocal()
    try:
        import asyncio
        form = asyncio.run(request.form())

        for wd in range(7):
            start_str = form.get(f"start_{wd}", "900")
            end_str = form.get(f"end_{wd}", "1110")
            daily_str = form.get(f"daily_{wd}", "120")

            start_min = int(start_str) if start_str.isdigit() else 900
            end_min = int(end_str) if end_str.isdigit() else 1110
            daily_minutes = int(daily_str) if daily_str.isdigit() else 120

            sched = db.query(Schedule).filter_by(username=user, weekday=wd).first()
            if not sched:
                sched = Schedule(username=user, weekday=wd)
                db.add(sched)

            sched.start_min = start_min
            sched.end_min = end_min
            sched.daily_minutes = daily_minutes

        db.commit()
        return RedirectResponse(f"/child/{user}", status_code=302)
    finally:
        db.close()


# =========================
# PROFILE MANAGEMENT
# =========================
@app.post("/profile/{user}/save")
def profile_save_endpoint(request: Request, user: str, name: str = Form(...)):
    r = require_admin(request)
    if r:
        return r

    db = SessionLocal()
    try:
        schedules = db.query(Schedule).filter_by(username=user).order_by(Schedule.weekday).all()
        profile_data = {
            str(s.weekday): {
                "start_min": s.start_min,
                "end_min": s.end_min,
                "daily_minutes": s.daily_minutes,
            }
            for s in schedules
        }
        save_profile(name, profile_data)
        return RedirectResponse(f"/schedule/{user}", status_code=302)
    finally:
        db.close()


@app.post("/profile/{user}/load")
def profile_load_endpoint(request: Request, user: str, name: str = Form(...)):
    r = require_admin(request)
    if r:
        return r

    profile_data = load_profile(name)
    if not profile_data:
        return HTMLResponse("<h3>Profil nicht gefunden</h3>", status_code=404)

    db = SessionLocal()
    try:
        for wd_str, data in profile_data.items():
            wd = int(wd_str)
            sched = db.query(Schedule).filter_by(username=user, weekday=wd).first()
            if not sched:
                sched = Schedule(username=user, weekday=wd)
                db.add(sched)

            sched.start_min = data["start_min"]
            sched.end_min = data["end_min"]
            sched.daily_minutes = data["daily_minutes"]

        db.commit()
        return RedirectResponse(f"/schedule/{user}", status_code=302)
    finally:
        db.close()


# =========================
# API FOR CLIENTS
# =========================
@app.get("/api/check/{user}")
def api_check(user: str, debug: str = "0"):
    db = SessionLocal()
    try:
        include_debug = debug == "1"
        state = compute_access(db, user=user, tz=TZ, include_debug=include_debug)
        return JSONResponse(state)
    finally:
        db.close()
