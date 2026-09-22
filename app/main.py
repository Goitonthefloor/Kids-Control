"""KidsControl – central parental control hub."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from zoneinfo import ZoneInfo

from app import config
from app.db import (
    AppRule,
    AuditLog,
    Child,
    DailyUsage,
    DayOverride,
    Device,
    DeviceCommand,
    Override,
    Schedule,
    SessionLocal,
    SoftwareItem,
    SoftwareWatch,
    audit,
    init_db,
    utcnow,
)
from app.ssh_control import remote_update_script, run_ssh
from app.policy import (
    REASON_LABELS_DE,
    SCHEDULE_PRESETS,
    build_agent_policy,
    compute_session,
    list_blocked_apps,
)
from app.ui import render_audit, render_child_page, render_dashboard, render_login


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="KidsControl", version="1.0.0", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET)


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(config.TIMEZONE)
    except Exception:
        return ZoneInfo("Europe/Berlin")


def now_local() -> datetime:
    return datetime.now(tz())


def logged_in(request: Request) -> str | None:
    return request.session.get("user")


def require_admin(request: Request):
    user = logged_in(request)
    if not user or user != config.ADMIN_USER:
        return RedirectResponse("/login", status_code=302)
    return None


def get_child_by_slug(db, slug: str) -> Child | None:
    return db.query(Child).filter_by(slug=slug).first()


def _store_inventory(db, device: Device, inventory: list) -> None:
    for item in inventory:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("package_name") or "").strip()
        if not name:
            continue
        version = str(item.get("version") or "").strip()
        source = str(item.get("source") or "agent").strip() or "agent"
        row = db.query(SoftwareItem).filter_by(device_id=device.id, package_name=name).first()
        if not row:
            row = SoftwareItem(device_id=device.id, package_name=name)
            db.add(row)
        row.version = version or "nicht installiert"
        row.source = source
        row.reported_at = utcnow()


def default_schedules_for(child_id: int) -> list[Schedule]:
    preset = SCHEDULE_PRESETS["Schule (Standard)"]
    return [
        Schedule(
            child_id=child_id,
            weekday=wd,
            start_min=vals["start_min"],
            end_min=vals["end_min"],
            daily_minutes=vals["daily_minutes"],
        )
        for wd, vals in preset.items()
    ]


# startup handled by lifespan


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "kidscontrol", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@app.get("/login")
def login_page():
    return HTMLResponse(render_login(config.ADMIN_USER))


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not config.ADMIN_PASSWORD:
        return HTMLResponse(
            render_login(config.ADMIN_USER, error="KIDSCONTROL_ADMIN_PASSWORD ist nicht gesetzt."),
            status_code=500,
        )
    if username == config.ADMIN_USER and password == config.ADMIN_PASSWORD:
        request.session["user"] = username
        return RedirectResponse("/dashboard", status_code=302)
    return HTMLResponse(render_login(config.ADMIN_USER, error="Login fehlgeschlagen."), status_code=401)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/")
def root(request: Request):
    if logged_in(request):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


# ---------------------------------------------------------------------------
# Dashboard & children
# ---------------------------------------------------------------------------


@app.get("/dashboard")
def dashboard(request: Request):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        kids_out = []
        for child in db.query(Child).order_by(Child.display_name.asc()).all():
            state = compute_session(db, child, tick_usage=False)
            devices = [
                {"name": d.name, "os_family": d.os_family, "last_seen_at": d.last_seen_at}
                for d in child.devices
            ]
            kids_out.append(
                {
                    "slug": child.slug,
                    "display_name": child.display_name,
                    "state": state,
                    "devices": [
                        {"name": d["name"], "os_family": d["os_family"]} for d in devices
                    ],
                    "blocked_app_count": len(
                        list_blocked_apps(db, child, session_allowed=bool(state.get("allow")))
                    ),
                }
            )
        flash = request.session.pop("flash", None)
        return HTMLResponse(render_dashboard(now_local().isoformat(timespec="seconds"), kids_out, flash=flash))
    finally:
        db.close()


@app.post("/ui/children/add")
def add_child(
    request: Request,
    display_name: str = Form(...),
    slug: str = Form(...),
):
    denied = require_admin(request)
    if denied:
        return denied
    slug = slug.strip().lower()
    display_name = display_name.strip()
    db = SessionLocal()
    try:
        if db.query(Child).filter_by(slug=slug).first():
            request.session["flash"] = f"Kurz-ID „{slug}“ existiert bereits."
            return RedirectResponse("/dashboard", status_code=302)
        child = Child(
            slug=slug,
            display_name=display_name,
            timezone=config.TIMEZONE,
        )
        db.add(child)
        db.flush()
        for sched in default_schedules_for(child.id):
            db.add(sched)
        audit(db, actor=config.ADMIN_USER, action="CHILD_CREATE", child_slug=slug, details=display_name)
        db.commit()
        request.session["flash"] = f"Kind „{display_name}“ angelegt."
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.get("/ui/child/{slug}")
def child_page(request: Request, slug: str):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        schedules = {
            s.weekday: {
                "start_min": s.start_min,
                "end_min": s.end_min,
                "daily_minutes": s.daily_minutes,
            }
            for s in child.schedules
        }
        apps = [
            {
                "id": a.id,
                "label": a.label,
                "pattern": a.pattern,
                "match_mode": a.match_mode,
                "scope": a.scope,
                "enabled": a.enabled,
            }
            for a in child.app_rules
        ]
        devices = []
        for d in child.devices:
            items = (
                db.query(SoftwareItem)
                .filter_by(device_id=d.id)
                .order_by(SoftwareItem.package_name.asc())
                .all()
            )
            cmds = (
                db.query(DeviceCommand)
                .filter_by(device_id=d.id)
                .order_by(DeviceCommand.id.desc())
                .limit(5)
                .all()
            )
            devices.append(
                {
                    "id": d.id,
                    "name": d.name,
                    "os_family": d.os_family,
                    "hostname": d.hostname,
                    "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
                    "device_key": d.device_key,
                    "ssh_enabled": bool(d.ssh_enabled),
                    "ssh_host": d.ssh_host or "",
                    "ssh_port": d.ssh_port or 22,
                    "ssh_user": d.ssh_user or "",
                    "ssh_key_path": d.ssh_key_path or "",
                    "software": [
                        {
                            "package_name": i.package_name,
                            "version": i.version,
                            "source": i.source,
                            "reported_at": i.reported_at.isoformat() if i.reported_at else "",
                        }
                        for i in items
                    ],
                    "commands": [
                        {
                            "id": c.id,
                            "kind": c.kind,
                            "package_name": c.package_name,
                            "status": c.status,
                            "via": c.via,
                            "output": (c.output or "")[:240],
                        }
                        for c in cmds
                    ],
                }
            )
        watches = [
            {"id": w.id, "package_name": w.package_name, "label": w.label}
            for w in child.watches
        ]
        flash = request.session.pop("flash", None)
        return HTMLResponse(
            render_child_page(
                {
                    "slug": child.slug,
                    "display_name": child.display_name,
                    "timezone": child.timezone,
                    "warn_minutes": child.warn_minutes,
                    "active": child.active,
                },
                schedules,
                apps,
                devices,
                list(SCHEDULE_PRESETS.keys()),
                flash=flash,
                watches=watches,
            )
        )
    finally:
        db.close()


@app.post("/ui/child/{slug}/settings")
async def child_settings(request: Request, slug: str):
    denied = require_admin(request)
    if denied:
        return denied
    form = await request.form()
    timezone_name = str(form.get("timezone") or config.TIMEZONE).strip() or config.TIMEZONE
    warn_minutes = int(form.get("warn_minutes") or 10)
    active = int(form.get("active") or 1)
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        child.timezone = timezone_name
        child.warn_minutes = max(0, min(120, warn_minutes))
        child.active = bool(active)
        audit(db, actor=config.ADMIN_USER, action="CHILD_SETTINGS", child_slug=slug)
        db.commit()
        request.session["flash"] = "Einstellungen gespeichert."
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.post("/ui/child/{slug}/schedule")
async def child_schedule(request: Request, slug: str):
    denied = require_admin(request)
    if denied:
        return denied
    form = await request.form()
    action = str(form.get("action") or "save")
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)

        if action == "reset_daily":
            day = now_local().date().isoformat()
            db.query(DailyUsage).filter_by(child_id=child.id, day=day).delete(synchronize_session=False)
            audit(db, actor=config.ADMIN_USER, action="RESET_DAILY", child_slug=slug, details=day)
            db.commit()
            request.session["flash"] = "Tagesnutzung zurückgesetzt."
            return RedirectResponse(f"/ui/child/{slug}", status_code=302)

        week: dict[int, dict] = {}
        if action == "apply_preset":
            preset_name = str(form.get("preset") or "")
            preset = SCHEDULE_PRESETS.get(preset_name)
            if not preset:
                request.session["flash"] = "Unbekanntes Preset."
                return RedirectResponse(f"/ui/child/{slug}", status_code=302)
            week = {int(k): dict(v) for k, v in preset.items()}
            audit(db, actor=config.ADMIN_USER, action="APPLY_PRESET", child_slug=slug, details=preset_name)
        else:
            for wd in range(7):
                sh = int(form.get(f"wd{wd}_start_h") or 0)
                sm = int(form.get(f"wd{wd}_start_m") or 0)
                eh = int(form.get(f"wd{wd}_end_h") or 0)
                em = int(form.get(f"wd{wd}_end_m") or 0)
                daily = int(form.get(f"wd{wd}_daily") or 0)
                week[wd] = {
                    "start_min": max(0, min(23, sh)) * 60 + max(0, min(59, sm)),
                    "end_min": max(0, min(23, eh)) * 60 + max(0, min(59, em)),
                    "daily_minutes": max(0, min(1440, daily)),
                }
            audit(db, actor=config.ADMIN_USER, action="SCHEDULE_SAVE", child_slug=slug)

        for wd, vals in week.items():
            row = db.query(Schedule).filter_by(child_id=child.id, weekday=wd).first()
            if not row:
                row = Schedule(child_id=child.id, weekday=wd)
                db.add(row)
            row.start_min = vals["start_min"]
            row.end_min = vals["end_min"]
            row.daily_minutes = vals["daily_minutes"]
        db.commit()
        request.session["flash"] = "Zeitplan gespeichert."
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.post("/ui/child/{slug}/apps/add")
def add_app_rule(
    request: Request,
    slug: str,
    label: str = Form(""),
    pattern: str = Form(...),
    match_mode: str = Form("contains"),
    scope: str = Form("always"),
):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        pattern = pattern.strip()
        if not pattern:
            request.session["flash"] = "Muster darf nicht leer sein."
            return RedirectResponse(f"/ui/child/{slug}", status_code=302)
        if match_mode not in {"contains", "exact", "startswith"}:
            match_mode = "contains"
        if scope not in {"always", "when_denied"}:
            scope = "always"
        db.add(
            AppRule(
                child_id=child.id,
                label=(label or pattern).strip(),
                pattern=pattern,
                match_mode=match_mode,
                scope=scope,
                enabled=True,
            )
        )
        audit(db, actor=config.ADMIN_USER, action="APP_RULE_ADD", child_slug=slug, details=pattern)
        db.commit()
        request.session["flash"] = f"App-Sperre „{pattern}“ hinzugefügt."
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.post("/ui/child/{slug}/apps/{rule_id}/delete")
def delete_app_rule(request: Request, slug: str, rule_id: int):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        rule = db.query(AppRule).filter_by(id=rule_id, child_id=child.id).first()
        if rule:
            audit(db, actor=config.ADMIN_USER, action="APP_RULE_DELETE", child_slug=slug, details=rule.pattern)
            db.delete(rule)
            db.commit()
        request.session["flash"] = "App-Sperre entfernt."
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.post("/ui/child/{slug}/devices/add")
def add_device(
    request: Request,
    slug: str,
    name: str = Form(...),
    os_family: str = Form("unknown"),
):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        if os_family not in {"linux", "windows", "macos", "unknown"}:
            os_family = "unknown"
        key = secrets.token_urlsafe(24)
        db.add(
            Device(
                child_id=child.id,
                name=name.strip(),
                device_key=key,
                os_family=os_family,
            )
        )
        audit(db, actor=config.ADMIN_USER, action="DEVICE_ADD", child_slug=slug, details=name.strip())
        db.commit()
        request.session["flash"] = f"Gerät angelegt. Device-Key: {key}"
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.post("/ui/child/{slug}/devices/{device_id}/delete")
def delete_device(request: Request, slug: str, device_id: int):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        device = db.query(Device).filter_by(id=device_id, child_id=child.id).first()
        if device:
            audit(db, actor=config.ADMIN_USER, action="DEVICE_DELETE", child_slug=slug, details=device.name)
            db.delete(device)
            db.commit()
        request.session["flash"] = "Gerät entfernt."
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.post("/ui/child/{slug}/devices/{device_id}/ssh")
async def save_device_ssh(request: Request, slug: str, device_id: int):
    denied = require_admin(request)
    if denied:
        return denied
    form = await request.form()
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        device = db.query(Device).filter_by(id=device_id, child_id=child.id).first()
        if not device:
            return HTMLResponse("Gerät nicht gefunden", status_code=404)
        device.ssh_enabled = str(form.get("ssh_enabled") or "0") == "1"
        device.ssh_host = str(form.get("ssh_host") or "").strip() or None
        device.ssh_user = str(form.get("ssh_user") or "").strip() or None
        device.ssh_key_path = str(form.get("ssh_key_path") or "").strip() or None
        try:
            device.ssh_port = max(1, min(65535, int(form.get("ssh_port") or 22)))
        except ValueError:
            device.ssh_port = 22
        audit(db, actor=config.ADMIN_USER, action="DEVICE_SSH", child_slug=slug, details=device.name)
        db.commit()
        request.session["flash"] = f"SSH-Einstellungen für {device.name} gespeichert."
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.post("/ui/child/{slug}/devices/{device_id}/ssh-test")
def test_device_ssh(request: Request, slug: str, device_id: int):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        device = db.query(Device).filter_by(id=device_id, child_id=child.id).first() if child else None
        if not device:
            return HTMLResponse("Gerät nicht gefunden", status_code=404)
        try:
            code, text = run_ssh(device, "echo kidscontrol-ok && uname -a", timeout=20)
        except Exception as exc:
            request.session["flash"] = f"SSH-Test fehlgeschlagen: {exc}"
            return RedirectResponse(f"/ui/child/{slug}", status_code=302)
        if code == 0 and "kidscontrol-ok" in text:
            request.session["flash"] = f"SSH ok ({device.name}): {text.splitlines()[-1][:180]}"
        else:
            request.session["flash"] = f"SSH-Test Code {code}: {text[:240]}"
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.post("/ui/child/{slug}/watches/add")
def add_watch(request: Request, slug: str, package_name: str = Form(...), label: str = Form("")):
    denied = require_admin(request)
    if denied:
        return denied
    name = package_name.strip()
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        if not name:
            request.session["flash"] = "Paketname fehlt."
            return RedirectResponse(f"/ui/child/{slug}", status_code=302)
        existing = db.query(SoftwareWatch).filter_by(child_id=child.id, package_name=name).first()
        if not existing:
            db.add(SoftwareWatch(child_id=child.id, package_name=name, label=(label or name).strip()))
            audit(db, actor=config.ADMIN_USER, action="WATCH_ADD", child_slug=slug, details=name)
            db.commit()
        request.session["flash"] = f"Software „{name}“ wird beobachtet."
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.post("/ui/child/{slug}/watches/{watch_id}/delete")
def delete_watch(request: Request, slug: str, watch_id: int):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        row = db.query(SoftwareWatch).filter_by(id=watch_id, child_id=child.id).first()
        if row:
            db.delete(row)
            audit(db, actor=config.ADMIN_USER, action="WATCH_DELETE", child_slug=slug, details=row.package_name)
            db.commit()
        request.session["flash"] = "Beobachtung entfernt."
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


def _queue_or_ssh_update(db, device: Device, *, package_name: str | None, actor: str, child_slug: str) -> str:
    kind = "update_one" if package_name else "update_all"
    if device.ssh_enabled and device.os_family == "linux":
        cmd = DeviceCommand(
            device_id=device.id,
            kind=kind,
            package_name=package_name,
            status="running",
            via="ssh",
        )
        db.add(cmd)
        db.flush()
        try:
            code, text = run_ssh(device, remote_update_script(package_name))
            cmd.status = "done" if code == 0 else "failed"
            cmd.output = text
            cmd.finished_at = utcnow()
        except Exception as exc:
            cmd.status = "failed"
            cmd.output = str(exc)
            cmd.finished_at = utcnow()
        audit(db, actor=actor, action="REMOTE_UPDATE_SSH", child_slug=child_slug, details=package_name or "all")
        return f"SSH-Update {cmd.status}: {(cmd.output or '')[:180]}"

    db.add(
        DeviceCommand(
            device_id=device.id,
            kind=kind,
            package_name=package_name,
            status="pending",
            via="agent",
        )
    )
    audit(db, actor=actor, action="REMOTE_UPDATE_QUEUE", child_slug=child_slug, details=package_name or "all")
    return "Update in die Agenten-Warteschlange gelegt. Der Agent führt es beim nächsten Abruf aus."


@app.post("/ui/child/{slug}/devices/{device_id}/update")
def queue_update(
    request: Request,
    slug: str,
    device_id: int,
    package_name: str = Form(""),
):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        device = db.query(Device).filter_by(id=device_id, child_id=child.id).first() if child else None
        if not device:
            return HTMLResponse("Gerät nicht gefunden", status_code=404)
        pkg = package_name.strip() or None
        msg = _queue_or_ssh_update(db, device, package_name=pkg, actor=config.ADMIN_USER, child_slug=slug)
        db.commit()
        request.session["flash"] = msg
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.post("/ui/grant/{slug}/hour")
def grant_hour(request: Request, slug: str):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        now = datetime.now(timezone.utc)
        last = (
            db.query(Override)
            .filter(Override.child_id == child.id, Override.grant_type == "HOUR")
            .order_by(Override.grant_until.desc())
            .first()
        )
        base = now
        if last and last.grant_until:
            until = last.grant_until
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until > now:
                base = until
        db.add(
            Override(
                child_id=child.id,
                grant_until=base + timedelta(hours=1),
                grant_type="HOUR",
                created_by=config.ADMIN_USER,
            )
        )
        audit(db, actor=config.ADMIN_USER, action="GRANT_HOUR", child_slug=slug)
        db.commit()
        request.session["flash"] = f"+1 Stunde für {child.display_name}."
        return RedirectResponse("/dashboard", status_code=302)
    finally:
        db.close()


@app.post("/ui/grant/{slug}/day")
def grant_day(request: Request, slug: str):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        day = now_local().date().isoformat()
        row = db.query(DayOverride).filter_by(child_id=child.id, day=day).first()
        if row and row.enabled:
            row.enabled = False
            row.updated_at = utcnow()
            action = "GRANT_DAY_OFF"
            msg = f"Unbegrenzt aus für {child.display_name}."
        else:
            if not row:
                row = DayOverride(child_id=child.id, day=day, enabled=True)
                db.add(row)
            else:
                row.enabled = True
                row.updated_at = utcnow()
            action = "GRANT_DAY_ON"
            msg = f"Heute unbegrenzt für {child.display_name}."
        audit(db, actor=config.ADMIN_USER, action=action, child_slug=slug, details=day)
        db.commit()
        request.session["flash"] = msg
        return RedirectResponse("/dashboard", status_code=302)
    finally:
        db.close()


@app.get("/ui/audit")
def audit_page(request: Request):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).order_by(AuditLog.at.desc()).limit(200).all()
        entries = [
            {
                "at": r.at.isoformat() if r.at else "",
                "actor": r.actor,
                "child_slug": r.child_slug,
                "action": r.action,
                "details": r.details,
            }
            for r in rows
        ]
        return HTMLResponse(render_audit(entries))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Agent API (cross-platform clients)
# ---------------------------------------------------------------------------


@app.post("/api/v1/agent/sync")
async def agent_sync(request: Request):
    """Heartbeat + policy pull for the OS agent."""
    device_key = request.headers.get("X-Device-Key") or request.headers.get("x-device-key")
    if not device_key:
        return JSONResponse({"error": "missing_device_key"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    db = SessionLocal()
    try:
        device = db.query(Device).filter_by(device_key=device_key).first()
        if not device:
            return JSONResponse({"error": "unknown_device"}, status_code=401)

        child = db.query(Child).filter_by(id=device.child_id).first()
        if not child:
            return JSONResponse({"error": "unknown_child"}, status_code=404)

        active = bool(body.get("active", True))
        hostname = (body.get("hostname") or "").strip() or None
        os_family = (body.get("os") or body.get("os_family") or "").strip().lower()
        if os_family in {"linux", "windows", "macos", "darwin"}:
            if os_family == "darwin":
                os_family = "macos"
            device.os_family = os_family
        if hostname:
            device.hostname = hostname
        device.last_seen_at = utcnow()

        inventory = body.get("inventory") or []
        if isinstance(inventory, list):
            _store_inventory(db, device, inventory)

        # Count usage only while the agent reports an active interactive session.
        policy = build_agent_policy(db, child, tick_usage=bool(active))
        watches = [w.package_name for w in child.watches]
        pending = (
            db.query(DeviceCommand)
            .filter_by(device_id=device.id, status="pending", via="agent")
            .order_by(DeviceCommand.id.asc())
            .all()
        )
        for cmd in pending:
            cmd.status = "running"
        commands = [
            {"id": c.id, "kind": c.kind, "package_name": c.package_name}
            for c in pending
        ]
        db.commit()

        return JSONResponse(
            {
                **policy,
                "server_time": now_local().isoformat(timespec="seconds"),
                "poll_interval_seconds": config.AGENT_POLL_SECONDS,
                "device": {
                    "id": device.id,
                    "name": device.name,
                    "os_family": device.os_family,
                },
                "reason_labels": REASON_LABELS_DE,
                "watch_packages": watches,
                "commands": commands,
            }
        )
    finally:
        db.close()


@app.post("/api/v1/agent/commands/{command_id}/result")
async def agent_command_result(request: Request, command_id: int):
    device_key = request.headers.get("X-Device-Key") or request.headers.get("x-device-key")
    if not device_key:
        return JSONResponse({"error": "missing_device_key"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    db = SessionLocal()
    try:
        device = db.query(Device).filter_by(device_key=device_key).first()
        if not device:
            return JSONResponse({"error": "unknown_device"}, status_code=401)
        cmd = db.query(DeviceCommand).filter_by(id=command_id, device_id=device.id).first()
        if not cmd:
            return JSONResponse({"error": "unknown_command"}, status_code=404)
        status = str(body.get("status") or "failed")
        if status not in {"done", "failed"}:
            status = "failed"
        cmd.status = status
        cmd.output = str(body.get("output") or "")[-4000:]
        cmd.finished_at = utcnow()
        db.commit()
        return JSONResponse({"ok": True, "id": cmd.id, "status": cmd.status})
    finally:
        db.close()


@app.get("/api/v1/agent/policy")
def agent_policy_get(request: Request):
    """Read-only policy fetch (no usage tick)."""
    device_key = request.headers.get("X-Device-Key") or request.query_params.get("device_key")
    if not device_key:
        return JSONResponse({"error": "missing_device_key"}, status_code=401)
    db = SessionLocal()
    try:
        device = db.query(Device).filter_by(device_key=device_key).first()
        if not device:
            return JSONResponse({"error": "unknown_device"}, status_code=401)
        child = db.query(Child).filter_by(id=device.child_id).first()
        if not child:
            return JSONResponse({"error": "unknown_child"}, status_code=404)
        policy = build_agent_policy(db, child, tick_usage=False)
        return JSONResponse(
            {
                **policy,
                "server_time": now_local().isoformat(timespec="seconds"),
                "poll_interval_seconds": config.AGENT_POLL_SECONDS,
            }
        )
    finally:
        db.close()
