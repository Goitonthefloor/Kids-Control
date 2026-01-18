diff --git a/app/main.py b/app/main.py
index 9c49a4a085af94c313c95dab6c4e298553601436..3f9729e14aa9f995998c1eb969c658eea2593d9c 100644
--- a/app/main.py
+++ b/app/main.py
@@ -9,89 +9,120 @@ Umsetzung:
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
+    REASON_MAP_DE,
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
+WIDGET_TOKEN = os.getenv("KIDSCONTROL_WIDGET_TOKEN", "")
 
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
 
 
+def _widget_remaining_minutes(state: dict) -> int | None:
+    candidates = []
+    for key in ("minutes_left_window", "daily_remaining"):
+        value = state.get(key)
+        if isinstance(value, int):
+            candidates.append(value)
+    if not candidates:
+        return None
+    return max(0, min(candidates))
+
+
+def _widget_remaining_label(state: dict) -> str | None:
+    reason = state.get("reason", "")
+    if reason == "override-day":
+        return "Unbegrenzt"
+    if reason == "override":
+        return str(state.get("override_text") or "Sonderfreigabe")
+    remaining = _widget_remaining_minutes(state)
+    if remaining is None:
+        return None
+    return f"Noch {remaining} Min"
+
+
+def _widget_reason_label(reason: str) -> str:
+    if not reason:
+        return ""
+    return REASON_MAP_DE.get(reason, reason)
+
+
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
@@ -148,50 +179,81 @@ def api_admin_usage(request: Request, user: str):
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
 
 
+@app.get("/api/widget/status")
+def api_widget_status(t: str | None = None):
+    if WIDGET_TOKEN and t != WIDGET_TOKEN:
+        return JSONResponse({"error": "unauthorized"}, status_code=401)
+    db = SessionLocal()
+    try:
+        kids = db.query(Child).order_by(Child.username.asc()).all()
+        payload = []
+        for k in kids:
+            state = compute_access(db, user=k.username, tz=TZ, include_debug=False)
+            payload.append(
+                {
+                    "username": k.username,
+                    "display_name": k.display_name or k.username,
+                    "allow": bool(state.get("allow")),
+                    "reason": state.get("reason", ""),
+                    "reason_label": _widget_reason_label(state.get("reason", "")),
+                    "warn": bool(state.get("warn", False)),
+                    "remaining_minutes": _widget_remaining_minutes(state),
+                    "remaining_label": _widget_remaining_label(state),
+                    "daily_remaining": state.get("daily_remaining"),
+                    "daily_limit": state.get("daily_limit"),
+                    "minutes_left_window": state.get("minutes_left_window"),
+                    "override_text": state.get("override_text"),
+                }
+            )
+        return JSONResponse({"server_time": now_local().isoformat(), "kids": payload})
+    finally:
+        db.close()
+
+
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
