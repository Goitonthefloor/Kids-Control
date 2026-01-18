"""
KidsControl – FastAPI Admin UI + Client API

Umsetzung:
1) Zeitplan-UI editierbar + Presets (Dropdown) + Profil speichern/laden
2) Override-UX (Heute unbegrenzt Toggle, +1h robust, Restzeit als hh:mm)
3) Trace UI im gleichen Design + Erklärung + Debug einklappbar
4) Kind-Ansicht (read-only) optional via Token
5) Code aufgeräumt: Policy/Format/UI in Module ausgelagert
"""

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
import os

from app.db import (
    SessionLocal,
    init_db,
    Child,
    Schedule,
    Override,
    ChildPolicy,
    PrewarnLog,
    DailyUsage,
    DayOverride,
)

from app.policy import compute_access, as_aware_utc
from app.ui import (
    css_block,
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

ADMIN_USER = os.getenv("KIDSCONTROL_ADMIN_USER", "administrator")
ADMIN_PASSWORD = os.getenv("KIDSCONTROL_ADMIN_PASSWORD", "")

CHILD_VIEW_TOKEN = os.getenv("KIDSCONTROL_CHILD_VIEW_TOKEN", "")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET)


def now_local() -> datetime:
    return datetime.now(TZ)

def logged_in(request: Request) -> str | None:
    return request.session.get("user")

def require_admin(request: Request):
    u = logged_in(request)
    if not u or u != ADMIN_USER:
        return RedirectResponse("/login", status_code=302)
    return None


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
    return HTMLResponse(render_login_page(css_block(), ADMIN_USER))

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not ADMIN_PASSWORD:
        return HTMLResponse(
            "<h1>Server nicht konfiguriert</h1><p>KIDSCONTROL_ADMIN_PASSWORD fehlt.</p>",
            status_code=500,
        )
    if username != ADMIN_USER or password != ADMIN_PASSWORD:
        return HTMLResponse(
            "<h1>Login fehlgeschlagen</h1><p>Benutzer oder Passwort falsch.</p><p><a href='/login'>Zurück</a></p>",
            status_code=401,
        )
    request.session["user"] = username
    return RedirectResponse("/dashboard", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# =========================
# CLIENT API
# =========================
@app.get("/api/check-access")
def api_check_access(user: str, host: str | None = None):
    db = SessionLocal()
    try:
        return JSONResponse(compute_access(db, user=user, tz=TZ, include_debug=False))
    finally:
        db.close()


# =========================
# ADMIN API
# =========================
@app.get("/api/admin/decision-trace/{user}")
def api_admin_decision_trace(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r
    db = SessionLocal()
    try:
        return JSONResponse(compute_access(db, user=user, tz=TZ, include_debug=True))
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
        from datetime import timedelta, datetime, timezone

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

        db.add(
            Override(
                username=user,
                grant_until=until,
                grant_type="HOUR",
                created_by=request.session.get("user", "unknown"),
            )
        )
        db.commit()
        return RedirectResponse("/dashboard", status_code=302)
    finally:
        db.close()


@app.post("/grant/{user}/day")
def grant_day_toggle(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r

    db = SessionLocal()
    try:
        day = now_local().date().isoformat()
        do = db.query(DayOverride).filter_by(username=user).first()
        if not do:
            do = DayOverride(username=user, day=day, enabled=True)
            db.add(do)
        else:
            if do.day != day:
                do.day = day
                do.enabled = True
            else:
                do.enabled = not do.enabled
            do.updated_at = datetime.now(timezone.utc)
        db.commit()
        return RedirectResponse("/dashboard", status_code=302)
    finally:
        db.close()


@app.post("/ui/reset-daily/{user}")
def ui_reset_daily(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r
    db = SessionLocal()
    try:
        day = now_local().date().isoformat()
        db.query(DailyUsage).filter_by(username=user, day=day).delete(synchronize_session=False)
        db.commit()
        return RedirectResponse("/dashboard", status_code=302)
    finally:
        db.close()


# =========================
# 1) ZEITPLAN UI (inkl. Presets + Profil sichern/laden)
# =========================
@app.get("/ui/schedule/{user}")
def ui_schedule_get(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r
    db = SessionLocal()
    try:
        html = render_schedule_editor(    
            css=css_block(),        
            user=user,
            display_name=_display_name(db, user),
            schedules=_get_week_schedule(db, user),
            presets=PRESETS,
            profiles=list_profiles(),
        )
        return HTMLResponse(html)
    finally:
        db.close()

@app.post("/ui/schedule/{user}")
async def ui_schedule_post(
    request: Request,
    user: str,
    action: str = Form(...),
    preset: str = Form(""),
    profile_name: str = Form(""),
):
    r = require_admin(request)
    if r:
        return r

    db = SessionLocal()
    try:
        form = dict((await request.form()).items())

        if action == "apply_preset":
            if preset and preset in PRESETS:
                _apply_profile_to_user(db, user, PRESETS[preset])
            return RedirectResponse(f"/ui/schedule/{user}", status_code=302)

        if action == "save_profile":
            prof = _profile_from_form(form)
            name = (profile_name or "").strip()
            if name:
                save_profile(name, prof)
            return RedirectResponse(f"/ui/schedule/{user}", status_code=302)

        if action == "load_profile":
            name = (profile_name or "").strip()
            if name:
                prof = load_profile(name)
                if prof:
                    _apply_profile_to_user(db, user, prof)
            return RedirectResponse(f"/ui/schedule/{user}", status_code=302)

        if action == "save_schedule":
            prof = _profile_from_form(form)
            _apply_profile_to_user(db, user, prof)
            return RedirectResponse(f"/ui/schedule/{user}", status_code=302)

        return RedirectResponse(f"/ui/schedule/{user}", status_code=302)
    finally:
        db.close()


# =========================
# DASHBOARD UI
# =========================
@app.get("/dashboard")
def dashboard(request: Request):
    if not logged_in(request):
        return RedirectResponse("/login", status_code=302)

    db = SessionLocal()
    try:
        kids = db.query(Child).order_by(Child.username.asc()).all()
        states = []
        for k in kids:
            st = compute_access(db, user=k.username, tz=TZ, include_debug=False)
            states.append({"username": k.username, "display_name": k.display_name or k.username, "state": st})

        return HTMLResponse(render_dashboard(css_block(), now_local().isoformat(), states))
    finally:
        db.close()


# =========================
# TRACE UI (gleicher Tab)
# =========================
@app.get("/trace/{user}")
def trace_ui(request: Request, user: str):
    r = require_admin(request)
    if r:
        return r
    db = SessionLocal()
    try:
        data = compute_access(db, user=user, tz=TZ, include_debug=True)
        return HTMLResponse(render_trace(css_block(), user, _display_name(db, user), data))
    finally:
        db.close()


# =========================
# KIND-ANSICHT (read-only, optional Token)
# =========================
@app.get("/k/{user}")
def child_view(user: str, t: str | None = None):
    if CHILD_VIEW_TOKEN and (not t or t != CHILD_VIEW_TOKEN):
        return HTMLResponse("<h1>401</h1><p>Nicht autorisiert.</p>", status_code=401)

    db = SessionLocal()
    try:
        data = compute_access(db, user=user, tz=TZ, include_debug=False)
        return HTMLResponse(render_child_view(css_block(), user, _display_name(db, user), data))
    finally:
        db.close()


# =========================
# INTERNAL DB HELPERS
# =========================
def _display_name(db, user: str) -> str:
    c = db.query(Child).filter_by(username=user).first()
    return (c.display_name or user) if c else user

def _get_week_schedule(db, user: str):
    out = {}
    for wd in range(7):
        s = db.query(Schedule).filter_by(username=user, weekday=wd).first()
        if not s:
            s = Schedule(username=user, weekday=wd, start_min=900, end_min=1110, daily_minutes=120)
            db.add(s)
            db.commit()
            db.refresh(s)
        out[wd] = {"start_min": int(s.start_min), "end_min": int(s.end_min), "daily_minutes": int(s.daily_minutes or 0)}
    return out

def _profile_from_form(form: dict):
    prof = {"week": {}}
    for wd in range(7):
        sh = int(form.get(f"wd{wd}_start_h", "15") or 15)
        sm = int(form.get(f"wd{wd}_start_m", "0") or 0)
        eh = int(form.get(f"wd{wd}_end_h", "18") or 18)
        em = int(form.get(f"wd{wd}_end_m", "0") or 0)
        dm = int(form.get(f"wd{wd}_daily", "120") or 0)
        prof["week"][str(wd)] = {"start_min": sh * 60 + sm, "end_min": eh * 60 + em, "daily_minutes": dm}
    return prof

def _apply_profile_to_user(db, user: str, prof: dict):
    week = prof.get("week", {}) or {}
    for wd in range(7):
        w = week.get(str(wd)) or week.get(wd) or {}
        start_min = int(w.get("start_min", 900))
        end_min = int(w.get("end_min", 1110))
        daily = int(w.get("daily_minutes", 120))
        s = db.query(Schedule).filter_by(username=user, weekday=wd).first()
        if not s:
            s = Schedule(username=user, weekday=wd, start_min=start_min, end_min=end_min, daily_minutes=daily)
            db.add(s)
        else:
            s.start_min = start_min
            s.end_min = end_min
            s.daily_minutes = daily
    db.commit()
