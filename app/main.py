"""KidsControl – central parental control hub."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.middleware.sessions import SessionMiddleware
from zoneinfo import ZoneInfo

from app import config
from app import __version__
from app.i18n import t
from app.install_web import (
    PROGRESS_CODES,
    browser_only_message,
    platform_from_user_agent,
    progress_line,
    render_install_form,
    render_install_message,
    render_install_progress,
    wants_install_page,
)
from app.oneclick import agent_archive, client_installer
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
    ServerSetting,
    SessionLocal,
    SetupEvent,
    SoftwareItem,
    SoftwareWatch,
    audit,
    init_db,
    utcnow,
)
from app.ssh_control import PACKAGE_NAME_RE, remote_update_script, run_ssh, store_private_key
from app.policy import (
    REASON_LABELS_DE,
    SCHEDULE_PRESETS,
    build_agent_policy,
    compute_session,
    list_blocked_apps,
    program_rows,
    tick_running_apps,
)
from app.guards import clear_failures, is_local_client, record_failure, safe_redirect_target, too_many_failures
from app.setup import SetupError, apply_setup
from app.ui import render_audit, render_child_page, render_dashboard, render_login, render_setup, render_setup_done


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="KidsControl", version=__version__, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET, same_site="lax", https_only=False)


@app.middleware("http")
async def require_setup(request: Request, call_next):
    path = request.url.path
    open_paths = path in {"/healthz", "/setup"} or path.startswith("/lang/")
    if not config.is_configured():
        if path == "/setup" and not is_local_client(request.client.host if request.client else ""):
            return HTMLResponse("Die Ersteinrichtung ist nur direkt auf dem Server unter http://127.0.0.1:8000/setup möglich.", status_code=403)
        if open_paths:
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"error": "server_not_configured"}, status_code=503)
        return RedirectResponse("/setup", status_code=302)
    if path == "/setup":
        return RedirectResponse("/login", status_code=302)
    return await call_next(request)


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(config.TIMEZONE)
    except Exception:
        return ZoneInfo("Europe/Berlin")


def now_local() -> datetime:
    return datetime.now(tz())


def ui_lang(request: Request) -> str:
    saved = request.session.get("lang")
    if saved in {"de", "en"}:
        return saved
    accept = (request.headers.get("accept-language") or "").lower()
    return "en" if accept.startswith("en") else "de"


def say(request: Request, key: str, **kwargs) -> str:
    return t(ui_lang(request), key, **kwargs)


def slugify(name: str) -> str:
    translated = name.strip().lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    slug = re.sub(r"[^a-z0-9]+", "-", translated).strip("-")[:32]
    return slug or "child"


def unique_slug(db, name: str) -> str:
    base = slugify(name)
    slug = base
    n = 2
    while db.query(Child).filter_by(slug=slug).first():
        suffix = f"-{n}"
        slug = f"{base[: 32 - len(suffix)]}{suffix}"
        n += 1
    return slug


def public_base(request: Request) -> str:
    from app.oneclick import _safe_server

    try:
        return _safe_server(str(request.base_url).rstrip("/"))
    except ValueError:
        return f"http://127.0.0.1:{config.port()}"


def form_int(value, default: int, low: int, high: int) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < low or number > high:
        return None
    return number if default is None else number


def setup_command(request: Request, token: str) -> str:
    return f"python -m kidscontrol_agent.setup --server {public_base(request)} --token {token}"


def child_install_url(request: Request, token: str) -> str:
    return f"{public_base(request)}/install/{token}"


_INSTALL_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def install_lang(request: Request) -> str:
    query = (request.query_params.get("lang") or "").lower()
    if query in {"de", "en"}:
        return query
    return ui_lang(request)


def _install_headers(extra: dict | None = None) -> dict[str, str]:
    headers = {
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }
    if extra:
        headers.update(extra)
    return headers


def _install_attempt_key(request: Request) -> str:
    host = request.client.host if request.client else ""
    return f"install:{host}"


def household_install_token(db) -> str:
    row = db.query(ServerSetting).filter_by(key="install_token").one_or_none()
    if row and row.value:
        return row.value
    value = secrets.token_urlsafe(24)
    db.add(ServerSetting(key="install_token", value=value))
    db.commit()
    return value


def _same_secret(left: str, right: str) -> bool:
    if not left or not right or len(left) != len(right):
        return False
    return secrets.compare_digest(left, right)


def _children_for_install_token(db, token: str) -> list[Child] | None:
    if not _INSTALL_TOKEN_RE.fullmatch(token or ""):
        return None
    if _same_secret(token, household_install_token(db)):
        return db.query(Child).filter_by(active=True).order_by(Child.display_name.asc()).all()
    child = db.query(Child).filter_by(enroll_token=token, active=True).first()
    if not child:
        return None
    return [child]


def _install_error(request: Request, status: int, key: str) -> HTMLResponse:
    lang = install_lang(request)
    page = render_install_message(lang, t(lang, key))
    return HTMLResponse(page, status_code=status, headers=_install_headers())


def _gate_install_token(request: Request, token: str) -> HTMLResponse | None:
    attempt_key = _install_attempt_key(request)
    if too_many_failures(attempt_key):
        return _install_error(request, 429, "install_throttled")
    db = SessionLocal()
    try:
        children = _children_for_install_token(db, token)
    finally:
        db.close()
    if children is None:
        record_failure(attempt_key)
        return _install_error(request, 404, "install_invalid")
    clear_failures(attempt_key)
    return None


def _clean_device_name(raw: str) -> str | None:
    name = " ".join((raw or "").split())
    if not name or len(name) > 80:
        return None
    return name


def _safe_progress_detail(raw: str) -> str:
    return " ".join((raw or "").split())[:180]


def _setup_snapshot(db, device: Device, lang: str) -> dict:
    child = db.query(Child).filter_by(id=device.child_id).first()
    child_name = child.display_name if child else ""
    events = db.query(SetupEvent).filter_by(device_id=device.id).order_by(SetupEvent.id.asc()).all()
    messages = [
        progress_line(lang, event.code, child=child_name, device=device.name, detail=event.detail or "")
        for event in events
    ]
    last = next((event.code for event in reversed(events) if event.code in {"finished", "failed"}), None)
    done = last == "finished"
    return {
        "messages": messages,
        "done": done,
        "ok": done,
        "child": child_name,
        "device": device.name,
        "success": t(lang, "install_success", device=device.name, child=child_name),
        "failure": t(lang, "install_failure"),
    }


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
    return {"ok": True, "service": "kidscontrol", "version": __version__, "configured": config.is_configured()}


@app.get("/setup")
def setup_page(request: Request):
    if config.is_configured():
        return RedirectResponse("/login", status_code=302)
    return HTMLResponse(render_setup(lang=ui_lang(request)))


@app.post("/setup")
def setup_submit(
    request: Request,
    admin_user: str = Form(...),
    admin_password: str = Form(...),
    admin_password_repeat: str = Form(...),
    setup_password: str = Form(...),
    setup_password_repeat: str = Form(...),
    timezone_name: str = Form("Europe/Berlin", alias="timezone"),
):
    if config.is_configured():
        return RedirectResponse("/login", status_code=302)
    language = ui_lang(request)
    if admin_password != admin_password_repeat:
        return HTMLResponse(render_setup(t(language, "passwords_mismatch_admin"), lang=language), status_code=400)
    if setup_password != setup_password_repeat:
        return HTMLResponse(render_setup(t(language, "passwords_mismatch_setup"), lang=language), status_code=400)
    try:
        apply_setup(
            admin_user=admin_user,
            admin_password=admin_password,
            setup_password=setup_password,
            timezone_name=timezone_name,
        )
    except SetupError as exc:
        return HTMLResponse(render_setup(t(language, str(exc)), lang=language), status_code=400)
    return HTMLResponse(render_setup_done(lang=language))


def _require_setup_password(given: str):
    if not config.is_configured():
        return JSONResponse({"error": "server_not_configured"}, status_code=503)
    if not config.passwords_match(given or "", config.setup_password()):
        return JSONResponse({"error": "setup_password_rejected"}, status_code=401)
    return None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@app.get("/lang/{code}")
def set_lang(request: Request, code: str):
    request.session["lang"] = "en" if code == "en" else "de"
    target = safe_redirect_target(request.headers.get("referer"))
    return RedirectResponse(target, status_code=302)


@app.get("/login")
def login_page(request: Request):
    return HTMLResponse(render_login(config.ADMIN_USER, lang=ui_lang(request)))


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not config.ADMIN_PASSWORD:
        return HTMLResponse(
            render_login(config.ADMIN_USER, error=say(request, "not_configured"), lang=ui_lang(request)),
            status_code=500,
        )
    client_host = request.client.host if request.client else ""
    attempt_key = f"login:{client_host}:{username}"
    if too_many_failures(attempt_key):
        return HTMLResponse(render_login(config.ADMIN_USER, error=say(request, "login_throttled"), lang=ui_lang(request)), status_code=429)
    user_ok = config.passwords_match(username, config.ADMIN_USER)
    pass_ok = config.passwords_match(password, config.ADMIN_PASSWORD)
    if user_ok and pass_ok:
        clear_failures(attempt_key)
        request.session["user"] = username
        return RedirectResponse("/dashboard", status_code=302)
    record_failure(attempt_key)
    return HTMLResponse(render_login(config.ADMIN_USER, error=say(request, "login_failed"), lang=ui_lang(request)), status_code=401)


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
                    "programs": program_rows(db, child),
                }
            )
        flash = request.session.pop("flash", None)
        install_url = child_install_url(request, household_install_token(db))
        return HTMLResponse(
            render_dashboard(
                now_local().isoformat(timespec="seconds"),
                kids_out,
                flash=flash,
                lang=ui_lang(request),
                install_url=install_url,
            )
        )
    finally:
        db.close()


@app.post("/ui/children/add")
def add_child(
    request: Request,
    display_name: str = Form(...),
    slug: str = Form(""),
):
    denied = require_admin(request)
    if denied:
        return denied
    display_name = display_name.strip()
    db = SessionLocal()
    try:
        slug = slug.strip().lower()
        if slug:
            if db.query(Child).filter_by(slug=slug).first():
                request.session["flash"] = say(request, "slug_exists", slug=slug)
                return RedirectResponse("/dashboard", status_code=302)
        else:
            slug = unique_slug(db, display_name)
        child = Child(
            slug=slug,
            display_name=display_name,
            timezone=config.TIMEZONE,
            enroll_token=secrets.token_urlsafe(18),
        )
        db.add(child)
        db.flush()
        for sched in default_schedules_for(child.id):
            db.add(sched)
        audit(db, actor=config.ADMIN_USER, action="CHILD_CREATE", child_slug=slug, details=display_name)
        db.commit()
        request.session["flash"] = say(request, "child_created", name=display_name)
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
        apps = program_rows(db, child)
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
        if not child.enroll_token:
            child.enroll_token = secrets.token_urlsafe(18)
            db.commit()
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
                lang=ui_lang(request),
                setup_command=setup_command(request, child.enroll_token),
                install_url=child_install_url(request, household_install_token(db)),
            )
        )
    finally:
        db.close()


@app.post("/ui/child/{slug}/enroll-token")
def rotate_enroll_token(request: Request, slug: str):
    denied = require_admin(request)
    if denied:
        return denied
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        child.enroll_token = secrets.token_urlsafe(18)
        audit(db, actor=config.ADMIN_USER, action="ENROLL_TOKEN_ROTATE", child_slug=slug)
        db.commit()
        request.session["flash"] = say(request, "token_rotated")
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.get("/ui/child/{slug}/oneclick/{platform}")
def oneclick_installer(request: Request, slug: str, platform: str):
    denied = require_admin(request)
    if denied:
        return denied
    if platform not in {"linux", "macos", "windows"}:
        return HTMLResponse("Unbekannte Plattform", status_code=404)
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        if not child.enroll_token:
            child.enroll_token = secrets.token_urlsafe(18)
            db.commit()
        token = child.enroll_token
    finally:
        db.close()
    filename, media, body = client_installer(platform, server=public_base(request), token=token)
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _install_platform(request: Request) -> str | None:
    return platform_from_user_agent(
        request.headers.get("user-agent") or "",
        request.headers.get("sec-ch-ua-platform") or "",
    )


def _child_choices(children: list[Child]) -> list[dict]:
    return [{"slug": child.slug, "display_name": child.display_name} for child in children]


@app.get("/install/{token}")
def install_landing(request: Request, token: str):
    """Open on the child PC. The form asks which child this PC belongs to."""
    denied = _gate_install_token(request, token)
    if denied:
        return denied
    user_agent = request.headers.get("user-agent") or ""
    accept = request.headers.get("accept") or ""
    if not wants_install_page(accept, user_agent):
        return Response(
            content=browser_only_message(child_install_url(request, token)),
            media_type="text/plain; charset=utf-8",
            headers=_install_headers(),
        )
    db = SessionLocal()
    try:
        children = _children_for_install_token(db, token) or []
        choices = _child_choices(children)
    finally:
        db.close()
    page = render_install_form(
        lang=install_lang(request),
        token=token,
        children=choices,
        platform=_install_platform(request),
    )
    return HTMLResponse(page, headers=_install_headers())


@app.post("/install/{token}")
def install_assign(request: Request, token: str, child_slug: str = Form(""), device_name: str = Form("")):
    """Create the device row for the child chosen on this PC."""
    denied = _gate_install_token(request, token)
    if denied:
        return denied
    lang = install_lang(request)
    slug = (child_slug or "").strip().lower()
    name = _clean_device_name(device_name)
    db = SessionLocal()
    try:
        children = _children_for_install_token(db, token) or []
        allowed = {child.slug: child for child in children}
        form_error = ""
        if slug not in allowed:
            form_error = t(lang, "install_need_child")
        elif name is None:
            form_error = t(lang, "install_need_name")
        if form_error or name is None:
            page = render_install_form(
                lang=lang,
                token=token,
                children=_child_choices(children),
                platform=_install_platform(request),
                error=form_error or t(lang, "install_need_name"),
            )
            return HTMLResponse(page, status_code=400, headers=_install_headers())
        child = allowed[slug]
        ticket = secrets.token_urlsafe(24)
        device = Device(
            child_id=child.id,
            name=name,
            device_key=secrets.token_urlsafe(24),
            os_family=_install_platform(request) or "unknown",
            setup_ticket=ticket,
        )
        db.add(device)
        db.flush()
        db.add(SetupEvent(device_id=device.id, code="device_created"))
        audit(db, actor="web-install", action="DEVICE_ENROLL", child_slug=child.slug, details=name)
        db.commit()
    finally:
        db.close()
    return RedirectResponse(f"/install/{token}/go/{ticket}", status_code=303)


@app.get("/install/{token}/go/{ticket}")
def install_progress_page(request: Request, token: str, ticket: str):
    denied = _gate_install_token(request, token)
    if denied:
        return denied
    lang = install_lang(request)
    db = SessionLocal()
    try:
        device = _device_for_install(db, token, ticket)
        if not device:
            return _install_error(request, 404, "install_invalid")
        snapshot = _setup_snapshot(db, device, lang)
        child_name = snapshot["child"]
        device_name = snapshot["device"]
    finally:
        db.close()
    page = render_install_progress(
        lang=lang,
        token=token,
        ticket=ticket,
        child_name=child_name,
        device_name=device_name,
        platform=_install_platform(request),
        messages=snapshot["messages"],
        done=bool(snapshot["done"]),
        ok=bool(snapshot["ok"]),
    )
    return HTMLResponse(page, headers=_install_headers())


@app.get("/install/{token}/status/{ticket}")
def install_status(request: Request, token: str, ticket: str):
    denied = _gate_install_token(request, token)
    if denied:
        return denied
    db = SessionLocal()
    try:
        device = _device_for_install(db, token, ticket)
        if not device:
            return _install_error(request, 404, "install_invalid")
        snapshot = _setup_snapshot(db, device, install_lang(request))
    finally:
        db.close()
    return JSONResponse(snapshot, headers=_install_headers())


@app.get("/install/{token}/{platform}")
def install_for_platform(request: Request, token: str, platform: str, ticket: str = ""):
    """Installer for the device created by the form. The ticket ties the file to that entry."""
    denied = _gate_install_token(request, token)
    if denied:
        return denied
    if platform not in {"linux", "macos", "windows"}:
        return _install_error(request, 404, "install_unknown")
    if not ticket:
        return _install_error(request, 400, "install_need_ticket")
    db = SessionLocal()
    try:
        device = _device_for_install(db, token, ticket)
    finally:
        db.close()
    if not device:
        record_failure(_install_attempt_key(request))
        return _install_error(request, 404, "install_invalid")
    return _install_file(request, platform, ticket)


def _device_for_install(db, token: str, ticket: str) -> Device | None:
    if not _INSTALL_TOKEN_RE.fullmatch(ticket or ""):
        return None
    device = db.query(Device).filter_by(setup_ticket=ticket).first()
    if not device:
        return None
    children = _children_for_install_token(db, token) or []
    if not any(child.id == device.child_id for child in children):
        return None
    return device


def _install_file(request: Request, platform: str, ticket: str) -> Response:
    try:
        filename, media, body = client_installer(platform, server=public_base(request), ticket=ticket)
    except ValueError:
        return _install_error(request, 400, "install_invalid")
    return Response(
        content=body,
        media_type=media,
        headers=_install_headers({"Content-Disposition": f'attachment; filename="{filename}"'}),
    )


@app.get("/setup/agent.tgz")
def setup_agent_tgz():
    body = agent_archive("tgz")
    return Response(
        content=body,
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="kidscontrol-agent.tgz"'},
    )


@app.get("/setup/agent.zip")
def setup_agent_zip():
    body = agent_archive("zip")
    return Response(
        content=body,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="kidscontrol-agent.zip"'},
    )


@app.post("/ui/child/{slug}/settings")
async def child_settings(request: Request, slug: str):
    denied = require_admin(request)
    if denied:
        return denied
    form = await request.form()
    timezone_name = str(form.get("timezone") or config.TIMEZONE).strip() or config.TIMEZONE
    warn_minutes = form_int(form.get("warn_minutes") or 10, 10, 0, 120)
    active = form_int(form.get("active") or 1, 1, 0, 1)
    if warn_minutes is None or active is None:
        request.session["flash"] = say(request, "invalid_number")
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
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
        request.session["flash"] = say(request, "settings_saved")
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
            request.session["flash"] = say(request, "daily_reset")
            return RedirectResponse(f"/ui/child/{slug}", status_code=302)

        week: dict[int, dict] = {}
        if action == "apply_preset":
            preset_name = str(form.get("preset") or "")
            preset = SCHEDULE_PRESETS.get(preset_name)
            if not preset:
                request.session["flash"] = say(request, "unknown_preset")
                return RedirectResponse(f"/ui/child/{slug}", status_code=302)
            week = {int(k): dict(v) for k, v in preset.items()}
            audit(db, actor=config.ADMIN_USER, action="APPLY_PRESET", child_slug=slug, details=preset_name)
        else:
            for wd in range(7):
                sh = form_int(form.get(f"wd{wd}_start_h") or 0, 0, 0, 23)
                sm = form_int(form.get(f"wd{wd}_start_m") or 0, 0, 0, 59)
                eh = form_int(form.get(f"wd{wd}_end_h") or 0, 0, 0, 23)
                em = form_int(form.get(f"wd{wd}_end_m") or 0, 0, 0, 59)
                daily = form_int(form.get(f"wd{wd}_daily") or 0, 0, 0, 1440)
                if None in {sh, sm, eh, em, daily}:
                    request.session["flash"] = say(request, "invalid_number")
                    return RedirectResponse(f"/ui/child/{slug}", status_code=302)
                week[wd] = {
                    "start_min": sh * 60 + sm,
                    "end_min": eh * 60 + em,
                    "daily_minutes": daily,
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
        request.session["flash"] = say(request, "schedule_saved")
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


def _quota_minutes(scope: str, raw) -> int | None:
    """Minutes for a quota rule, None when the scope is not a quota, or -1 if invalid."""
    if scope != "quota":
        return None
    minutes = form_int(raw, 30, 1, 1440)
    if minutes is None:
        return -1
    return minutes


@app.post("/ui/child/{slug}/apps/add")
def add_app_rule(
    request: Request,
    slug: str,
    label: str = Form(""),
    pattern: str = Form(...),
    match_mode: str = Form("contains"),
    scope: str = Form("always"),
    daily_minutes: str = Form(""),
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
            request.session["flash"] = say(request, "pattern_empty")
            return RedirectResponse(f"/ui/child/{slug}", status_code=302)
        if match_mode not in {"contains", "exact", "startswith"}:
            match_mode = "contains"
        if scope not in {"always", "when_denied", "quota"}:
            scope = "always"
        minutes = _quota_minutes(scope, daily_minutes)
        if minutes == -1:
            request.session["flash"] = say(request, "quota_invalid")
            return RedirectResponse(f"/ui/child/{slug}", status_code=302)
        db.add(
            AppRule(
                child_id=child.id,
                label=(label or pattern).strip(),
                pattern=pattern,
                match_mode=match_mode,
                scope=scope,
                daily_minutes=minutes,
                enabled=True,
            )
        )
        audit(db, actor=config.ADMIN_USER, action="APP_RULE_ADD", child_slug=slug, details=pattern)
        db.commit()
        request.session["flash"] = say(request, "app_added", pattern=pattern)
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


@app.post("/ui/child/{slug}/apps/{rule_id}")
async def edit_app_rule(request: Request, slug: str, rule_id: int):
    denied = require_admin(request)
    if denied:
        return denied
    form = await request.form()
    db = SessionLocal()
    try:
        child = get_child_by_slug(db, slug)
        if not child:
            return HTMLResponse("Kind nicht gefunden", status_code=404)
        rule = db.query(AppRule).filter_by(id=rule_id, child_id=child.id).first()
        if not rule:
            return HTMLResponse("App-Sperre nicht gefunden", status_code=404)
        pattern = str(form.get("pattern") or "").strip()
        if not pattern:
            request.session["flash"] = say(request, "pattern_empty")
            return RedirectResponse(f"/ui/child/{slug}", status_code=302)
        match_mode = str(form.get("match_mode") or "contains")
        scope = str(form.get("scope") or "always")
        if match_mode not in {"contains", "exact", "startswith"}:
            match_mode = "contains"
        if scope not in {"always", "when_denied", "quota"}:
            scope = "always"
        minutes = _quota_minutes(scope, form.get("daily_minutes"))
        if minutes == -1:
            request.session["flash"] = say(request, "quota_invalid")
            return RedirectResponse(f"/ui/child/{slug}", status_code=302)
        rule.label = (str(form.get("label") or pattern)).strip()
        rule.pattern = pattern
        rule.match_mode = match_mode
        rule.scope = scope
        rule.daily_minutes = minutes
        rule.enabled = str(form.get("enabled") or "1") == "1"
        audit(db, actor=config.ADMIN_USER, action="APP_RULE_EDIT", child_slug=slug, details=pattern)
        db.commit()
        request.session["flash"] = say(request, "app_saved")
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
        request.session["flash"] = say(request, "app_deleted")
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
        request.session["flash"] = say(request, "device_added")
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
        request.session["flash"] = say(request, "device_removed")
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
        request.session["flash"] = say(request, "ssh_saved", name=device.name)
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
            request.session["flash"] = say(request, "ssh_failed", error=exc)
            return RedirectResponse(f"/ui/child/{slug}", status_code=302)
        if code == 0 and "kidscontrol-ok" in text:
            request.session["flash"] = say(request, "ssh_ok", name=device.name, detail=text.splitlines()[-1][:180])
        else:
            request.session["flash"] = say(request, "ssh_code", code=code, detail=text[:240])
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
            request.session["flash"] = say(request, "package_missing")
            return RedirectResponse(f"/ui/child/{slug}", status_code=302)
        existing = db.query(SoftwareWatch).filter_by(child_id=child.id, package_name=name).first()
        if not existing:
            db.add(SoftwareWatch(child_id=child.id, package_name=name, label=(label or name).strip()))
            audit(db, actor=config.ADMIN_USER, action="WATCH_ADD", child_slug=slug, details=name)
            db.commit()
        request.session["flash"] = say(request, "watch_added", name=name)
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
        request.session["flash"] = say(request, "watch_removed")
        return RedirectResponse(f"/ui/child/{slug}", status_code=302)
    finally:
        db.close()


def _queue_or_ssh_update(db, device: Device, *, package_name: str | None, actor: str, child_slug: str, lang: str = "de") -> str:
    if package_name and not PACKAGE_NAME_RE.fullmatch(package_name):
        return t(lang, "package_invalid")
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
        return t(lang, "update_ssh", status=cmd.status, detail=(cmd.output or "")[:180])

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
    return t(lang, "update_queued")


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
        msg = _queue_or_ssh_update(
            db, device, package_name=pkg, actor=config.ADMIN_USER, child_slug=slug, lang=ui_lang(request)
        )
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
        request.session["flash"] = say(request, "grant_hour", name=child.display_name)
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
            msg = say(request, "grant_day_off", name=child.display_name)
        else:
            if not row:
                row = DayOverride(child_id=child.id, day=day, enabled=True)
                db.add(row)
            else:
                row.enabled = True
                row.updated_at = utcnow()
            action = "GRANT_DAY_ON"
            msg = say(request, "grant_day_on", name=child.display_name)
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
        return HTMLResponse(render_audit(entries, lang=ui_lang(request)))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Client enrollment (setup password, not the parent login)
# ---------------------------------------------------------------------------


@app.post("/api/v1/setup/children")
async def setup_children(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    denied = _require_setup_password(str(body.get("setup_password") or ""))
    if denied:
        return denied
    db = SessionLocal()
    try:
        kids = [
            {"slug": c.slug, "display_name": c.display_name}
            for c in db.query(Child).filter_by(active=True).order_by(Child.display_name.asc()).all()
        ]
        return JSONResponse({"children": kids})
    finally:
        db.close()


def _normalize_os(raw: str) -> str:
    os_family = (raw or "unknown").strip().lower()
    if os_family == "darwin":
        os_family = "macos"
    if os_family not in {"linux", "windows", "macos", "unknown"}:
        return "unknown"
    return os_family


def normalize_host_pubkey(raw: str) -> str | None:
    """Return 'type key', '' when absent, or None when the line is not an SSH public key."""
    text = " ".join((raw or "").split())
    if not text:
        return ""
    parts = text.split(" ")
    if len(parts) < 2:
        return None
    kind, material = parts[0], parts[1]
    if not (kind.startswith("ssh-") or kind.startswith("ecdsa-") or kind.startswith("sk-")):
        return None
    alphabet = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    if not material or len(material) > 4096 or any(ch not in alphabet for ch in material):
        return None
    return f"{kind} {material}"


def _release_stale_commands(db, device_id: int) -> None:
    now = utcnow()
    rows = (
        db.query(DeviceCommand)
        .filter_by(device_id=device_id, status="running", via="agent")
        .all()
    )
    for cmd in rows:
        stamp = cmd.started_at or cmd.created_at
        if stamp is None:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if now - stamp > timedelta(minutes=60):
            cmd.status = "pending"
            cmd.started_at = None


def _device_by_ticket(db, ticket: str) -> Device | None:
    if not _INSTALL_TOKEN_RE.fullmatch(ticket or ""):
        return None
    return db.query(Device).filter_by(setup_ticket=ticket).first()


def _setup_is_finished(db, device_id: int) -> bool:
    return (
        db.query(SetupEvent).filter_by(device_id=device_id, code="finished").first() is not None
    )


@app.post("/api/v1/setup/progress")
async def setup_progress(request: Request):
    """Confirmation the child PC shows in the browser while setup runs."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    ticket = str(body.get("ticket") or "").strip()
    code = str(body.get("code") or "").strip()
    attempt_key = f"progress:{request.client.host if request.client else ''}"
    if too_many_failures(attempt_key):
        return JSONResponse({"error": "too_many_attempts"}, status_code=429)
    if code not in PROGRESS_CODES:
        return JSONResponse({"error": "unknown_progress"}, status_code=400)
    db = SessionLocal()
    try:
        device = _device_by_ticket(db, ticket)
        if not device:
            record_failure(attempt_key)
            return JSONResponse({"error": "unknown_ticket"}, status_code=404)
        clear_failures(attempt_key)
        count = db.query(SetupEvent).filter_by(device_id=device.id).count()
        if count >= 40:
            return JSONResponse({"error": "too_many_messages"}, status_code=409)
        if _setup_is_finished(db, device.id):
            return JSONResponse({"error": "setup_finished"}, status_code=409)
        detail = _safe_progress_detail(str(body.get("detail") or "")) if code == "failed" else ""
        db.add(SetupEvent(device_id=device.id, code=code, detail=detail or None))
        db.commit()
        return JSONResponse({"ok": True})
    finally:
        db.close()


@app.post("/api/v1/setup/claim")
async def setup_claim(request: Request):
    """The installer sends hostname, OS, and the SSH key for the entry the form created."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    ticket = str(body.get("ticket") or "").strip()
    attempt_key = f"claim:{request.client.host if request.client else ''}"
    if too_many_failures(attempt_key):
        return JSONResponse({"error": "too_many_attempts"}, status_code=429)
    os_family = _normalize_os(str(body.get("os") or body.get("os_family") or "unknown"))
    host_name = str(body.get("hostname") or "").strip() or None
    host_pubkey = normalize_host_pubkey(str(body.get("ssh_host_key") or ""))
    if host_pubkey is None:
        return JSONResponse({"error": "invalid_host_key"}, status_code=400)
    db = SessionLocal()
    try:
        device = _device_by_ticket(db, ticket)
        if not device:
            record_failure(attempt_key)
            return JSONResponse({"error": "unknown_ticket"}, status_code=404)
        if _setup_is_finished(db, device.id):
            return JSONResponse({"error": "setup_finished"}, status_code=409)
        clear_failures(attempt_key)
        child = db.query(Child).filter_by(id=device.child_id).first()
        if not child or not child.active:
            return JSONResponse({"error": "unknown_child"}, status_code=404)
        device.os_family = os_family
        device.hostname = host_name
        device.ssh_host_pubkey = host_pubkey or None
        private_key = str(body.get("ssh_private_key") or "")
        ssh_user = str(body.get("ssh_user") or "").strip() or None
        if private_key.strip():
            device.ssh_user = ssh_user
            device.ssh_host = host_name
            device.ssh_port = 22
            device.ssh_enabled = os_family == "linux"
            try:
                path = store_private_key(device.id, private_key)
            except ValueError:
                db.rollback()
                return JSONResponse({"error": "invalid_private_key"}, status_code=400)
            device.ssh_key_path = str(path)
        audit(db, actor="client-setup", action="DEVICE_CLAIM", child_slug=child.slug, details=device.name)
        db.commit()
        return JSONResponse(
            {
                "device_key": device.device_key,
                "device_name": device.name,
                "child": {"slug": child.slug, "display_name": child.display_name},
                "poll_interval_seconds": config.AGENT_POLL_SECONDS,
                "ssh_ready": bool(device.ssh_key_path),
            },
            headers=_install_headers(),
        )
    finally:
        db.close()


@app.post("/api/v1/setup/enroll")
async def setup_enroll(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    token = str(body.get("token") or "").strip()
    os_family = _normalize_os(str(body.get("os") or body.get("os_family") or "unknown"))
    host_name = str(body.get("hostname") or "").strip() or None
    device_name = str(body.get("device_name") or "").strip() or host_name or "PC"
    attempt_key = f"enroll:{request.client.host if request.client else ''}"
    if too_many_failures(attempt_key):
        return JSONResponse({"error": "too_many_attempts"}, status_code=429)
    host_pubkey = normalize_host_pubkey(str(body.get("ssh_host_key") or ""))
    if host_pubkey is None:
        return JSONResponse({"error": "invalid_host_key"}, status_code=400)
    db = SessionLocal()
    try:
        child = None
        used_token = False
        if token:
            child = db.query(Child).filter_by(enroll_token=token, active=True).first()
            if not child:
                record_failure(attempt_key)
                return JSONResponse({"error": "setup_token_rejected"}, status_code=401)
            used_token = True
        else:
            denied = _require_setup_password(str(body.get("setup_password") or ""))
            if denied:
                record_failure(attempt_key)
                return denied
            slug = str(body.get("child_slug") or "").strip().lower()
            if not slug:
                return JSONResponse({"error": "child_slug_and_device_name_required"}, status_code=400)
            child = get_child_by_slug(db, slug)
            if not child or not child.active:
                return JSONResponse({"error": "unknown_child"}, status_code=404)
        key = secrets.token_urlsafe(24)
        device = Device(
            child_id=child.id,
            name=device_name[:80],
            device_key=key,
            os_family=os_family,
            hostname=host_name,
            ssh_host_pubkey=host_pubkey or None,
        )
        private_key = str(body.get("ssh_private_key") or "")
        ssh_user = str(body.get("ssh_user") or "").strip() or None
        if private_key.strip():
            device.ssh_user = ssh_user
            device.ssh_host = host_name
            device.ssh_port = 22
            device.ssh_enabled = os_family == "linux"
        db.add(device)
        db.flush()
        if private_key.strip():
            try:
                path = store_private_key(device.id, private_key)
            except ValueError:
                db.rollback()
                return JSONResponse({"error": "invalid_private_key"}, status_code=400)
            device.ssh_key_path = str(path)
        if used_token:
            child.enroll_token = secrets.token_urlsafe(18)
        clear_failures(attempt_key)
        audit(db, actor="client-setup", action="DEVICE_ENROLL", child_slug=child.slug, details=device.name)
        db.commit()
        return JSONResponse(
            {
                "device_key": key,
                "device_name": device.name,
                "child": {"slug": child.slug, "display_name": child.display_name},
                "poll_interval_seconds": config.AGENT_POLL_SECONDS,
                "ssh_ready": bool(device.ssh_key_path),
            }
        )
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
        tick_running_apps(db, child, body.get("running_apps") or [])

        # Count usage only while the agent reports an active interactive session.
        policy = build_agent_policy(db, child, tick_usage=bool(active))
        watches = [w.package_name for w in child.watches]
        _release_stale_commands(db, device.id)
        db.flush()
        pending = (
            db.query(DeviceCommand)
            .filter_by(device_id=device.id, status="pending", via="agent")
            .order_by(DeviceCommand.id.asc())
            .all()
        )
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
        if status == "running":
            if cmd.status in {"pending", "running"}:
                cmd.status = "running"
                cmd.started_at = cmd.started_at or utcnow()
            db.commit()
            return JSONResponse({"ok": True, "id": cmd.id, "status": cmd.status})
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
