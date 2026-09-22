"""Server-rendered parent UI (German and English)."""

from __future__ import annotations

from html import escape

from app.i18n import preset_label, reason_label, t, weekday


def css() -> str:
    return r"""
:root{
  --bg:#0f1214; --panel:#151a1d; --panel2:#111518; --text:#e7ecef;
  --muted:#a9b4bb; --border:#2a3338; --mint:#0f7f66; --mint2:#10a37f;
  --danger:#b33a3a; --shadow:0 18px 50px rgba(0,0,0,.45); --r:16px;
}
*{box-sizing:border-box}
body{
  margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif; color:var(--text);
  background:
    radial-gradient(1200px 600px at 30% 10%, rgba(16,163,127,.10), transparent 60%),
    radial-gradient(900px 600px at 70% 20%, rgba(15,127,102,.08), transparent 55%),
    var(--bg);
}
.wrap{padding:clamp(18px,3vw,42px)}
.container{width:min(1280px,100%); margin:0 auto}
.topbar{
  display:flex; align-items:center; justify-content:space-between; gap:12px;
  padding:14px 16px; border:1px solid var(--border); border-radius:var(--r);
  background:linear-gradient(180deg,rgba(16,163,127,.08),transparent), var(--panel2);
  box-shadow:var(--shadow);
}
.title h1{margin:0; font-size:20px}
.title small{color:var(--muted)}
.nav{display:flex; gap:8px; flex-wrap:wrap; align-items:center}
.nav a,.link{
  color:var(--text); text-decoration:none; padding:10px 12px; border-radius:12px;
  border:1px solid var(--border); background:rgba(255,255,255,.02)
}
.nav a:hover,.link:hover{border-color:rgba(16,163,127,.55)}
.grid{margin-top:14px; display:grid; gap:12px}
.card{
  border-radius:var(--r); border:1px solid var(--border); background:var(--panel);
  box-shadow:0 10px 30px rgba(0,0,0,.25); padding:14px 16px
}
.rowcard{
  display:grid; grid-template-columns:220px 1fr auto; gap:14px; align-items:center;
  border-radius:var(--r); border:1px solid var(--border); background:var(--panel);
  box-shadow:0 10px 30px rgba(0,0,0,.25); padding:14px 16px
}
@media (max-width:1000px){.rowcard{grid-template-columns:1fr}}
.kidname{font-weight:800; font-size:16px}
.kiduser{color:var(--muted); font-size:12px; margin-top:4px}
.big{font-size:22px}
.meta{margin-top:8px; display:flex; gap:8px; flex-wrap:wrap}
.pill{
  display:inline-flex; align-items:center; padding:6px 10px; border-radius:999px;
  border:1px solid var(--border); color:var(--muted); font-size:12px; background:rgba(0,0,0,.18)
}
.pill.mint{border-color:rgba(16,163,127,.45); color:var(--text); background:rgba(16,163,127,.10)}
.pill.danger{border-color:rgba(179,58,58,.55); color:#ffd7d7; background:rgba(179,58,58,.15)}
.actions{display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end}
form{margin:0}
.btn{
  cursor:pointer; padding:10px 12px; border-radius:12px;
  border:1px solid rgba(16,163,127,.45);
  background:linear-gradient(180deg,rgba(16,163,127,.22),rgba(16,163,127,.12));
  color:var(--text); font-weight:700
}
.btn:hover{border-color:rgba(16,163,127,.75)}
.btn.ghost{border-color:var(--border); background:rgba(255,255,255,.03)}
.btn.danger{border-color:rgba(179,58,58,.55); background:rgba(179,58,58,.18)}
.btn:disabled{opacity:.55; cursor:not-allowed}
.small{color:var(--muted); font-size:12px}
table{width:100%; border-collapse:collapse}
th,td{padding:10px 8px; border-bottom:1px solid rgba(255,255,255,.06); text-align:left; vertical-align:middle}
th{color:var(--muted); font-weight:700; font-size:12px; letter-spacing:.4px; text-transform:uppercase}
input,select{
  width:100%; padding:10px; border-radius:12px; border:1px solid var(--border);
  background:#0d1012; color:var(--text); outline:none
}
input:focus,select:focus{border-color:rgba(16,163,127,.65); box-shadow:0 0 0 4px rgba(16,163,127,.12)}
.flash{padding:10px 12px; border-radius:12px; border:1px solid rgba(16,163,127,.45); background:rgba(16,163,127,.12); margin-top:12px}
.flash.err{border-color:rgba(179,58,58,.55); background:rgba(179,58,58,.12)}
.notice{padding:12px 14px; border-radius:12px; border:1px solid rgba(196,140,40,.75); background:rgba(196,140,40,.16); margin:12px 0; font-weight:650}
.tabs{display:flex; gap:8px; flex-wrap:wrap; margin-top:12px}
.tabs a.active{border-color:rgba(16,163,127,.75); background:rgba(16,163,127,.12)}
.two{display:grid; grid-template-columns:1fr 1fr; gap:12px}
@media (max-width:800px){.two{grid-template-columns:1fr}}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12px}
"""


def _pill(label: str, value: str, *, mint: bool = False, danger: bool = False) -> str:
    cls = "pill"
    if mint:
        cls += " mint"
    if danger:
        cls += " danger"
    return f'<span class="{cls}"><b>{escape(label)}:</b>&nbsp;{escape(value)}</span>'


def _shell(title: str, subtitle: str, body: str, *, nav: str = "", flash: str | None = None, lang: str = "de") -> str:
    flash_html = ""
    if flash:
        flash_html = f'<div class="flash">{escape(flash)}</div>'
    langs = '<a href="/lang/de">DE</a><a href="/lang/en">EN</a>'
    return f"""<!doctype html>
<html lang="{escape(lang)}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{escape(title)} – KidsControl</title>
  <style>{css()}</style>
</head>
<body>
  <div class="wrap">
    <div class="container">
      <div class="topbar">
        <div class="title">
          <h1>{escape(title)}</h1>
          <small>{escape(subtitle)}</small>
        </div>
        <div class="nav">{langs}{nav}</div>
      </div>
      {flash_html}
      {body}
    </div>
  </div>
</body>
</html>"""


def render_setup(error: str | None = None, lang: str = "de") -> str:
    err = f'<div class="flash err">{escape(error)}</div>' if error else ""
    body = f"""
<div class="grid" style="max-width:760px;margin-top:14px">
  <div class="card">
    <h2 style="margin:0 0 8px 0;font-size:18px">{escape(t(lang, "setup_title"))}</h2>
    <p class="small">{escape(t(lang, "setup_intro"))}</p>
    {err}
    <form method="post" action="/setup" style="margin-top:12px;display:grid;gap:10px">
      <div>
        <div class="small">{escape(t(lang, "admin_user"))}</div>
        <input name="admin_user" value="admin" required autocomplete="username"/>
      </div>
      <div>
        <div class="small">{escape(t(lang, "admin_password"))}</div>
        <input name="admin_password" type="password" required autocomplete="new-password"/>
      </div>
      <div>
        <div class="small">{escape(t(lang, "admin_password_repeat"))}</div>
        <input name="admin_password_repeat" type="password" required autocomplete="new-password"/>
      </div>
      <div>
        <div class="small">{escape(t(lang, "setup_password"))}</div>
        <input name="setup_password" type="password" required autocomplete="new-password"/>
        <p class="small" style="margin:6px 0 0 0">{escape(t(lang, "setup_password_hint"))}</p>
      </div>
      <div>
        <div class="small">{escape(t(lang, "setup_password_repeat"))}</div>
        <input name="setup_password_repeat" type="password" required autocomplete="new-password"/>
      </div>
      <div>
        <div class="small">{escape(t(lang, "timezone"))}</div>
        <input name="timezone" value="Europe/Berlin"/>
      </div>
      <button class="btn" type="submit">{escape(t(lang, "setup_submit"))}</button>
    </form>
  </div>
</div>"""
    return _shell("KidsControl", t(lang, "setup_sub"), body, nav="", lang=lang)


def render_setup_done(lang: str = "de") -> str:
    body = f"""
<div class="grid" style="max-width:760px;margin-top:14px">
  <div class="card">
    <h2 style="margin:0 0 8px 0;font-size:18px">{escape(t(lang, "setup_done_title"))}</h2>
    <p>{escape(t(lang, "setup_done_body"))}</p>
    <p class="small">{escape(t(lang, "setup_done_hint"))}</p>
  </div>
</div>"""
    return _shell("KidsControl", t(lang, "setup_done_sub"), body, nav="", lang=lang)


def render_login(admin_user: str, error: str | None = None, lang: str = "de") -> str:
    err = f'<div class="flash err">{escape(error)}</div>' if error else ""
    body = f"""
<div class="grid" style="max-width:720px;margin-top:14px">
  <div class="card">
    <h2 style="margin:0 0 8px 0;font-size:18px">{escape(t(lang, "login_title"))}</h2>
    <p class="small">{escape(t(lang, "login_intro"))}</p>
    {err}
    <form method="post" action="/login" style="margin-top:12px;display:grid;gap:10px">
      <div>
        <div class="small">{escape(t(lang, "username"))}</div>
        <input name="username" value="{escape(admin_user)}" required/>
      </div>
      <div>
        <div class="small">{escape(t(lang, "password"))}</div>
        <input name="password" type="password" required/>
      </div>
      <button class="btn" type="submit">{escape(t(lang, "sign_in"))}</button>
    </form>
  </div>
</div>"""
    return _shell("KidsControl", t(lang, "login_sub"), body, nav="", lang=lang)


def render_dashboard(now_iso: str, kids: list[dict], flash: str | None = None, lang: str = "de") -> str:
    rows = ""
    for k in kids:
        st = k.get("state") or {}
        allow = bool(st.get("allow"))
        reason = st.get("reason", "")
        pills = [_pill(t(lang, "reason"), reason_label(lang, reason), mint=True)]
        if st.get("remaining_minutes") is not None:
            pills.append(_pill(t(lang, "remaining"), t(lang, "minutes", n=st["remaining_minutes"]), mint=True))
        if st.get("daily_remaining") is not None and st.get("daily_limit") is not None:
            pills.append(_pill(t(lang, "daily_budget"), f'{st["daily_remaining"]}/{st["daily_limit"]}'))
        blocked_n = int(k.get("blocked_app_count") or 0)
        if blocked_n:
            pills.append(_pill(t(lang, "app_blocks"), str(blocked_n), danger=True))
        devices = k.get("devices") or []
        if devices:
            pills.append(_pill(t(lang, "devices"), ", ".join(d["name"] for d in devices)))
        else:
            pills.append(_pill(t(lang, "devices"), t(lang, "none"), danger=True))

        slug = escape(k["slug"])
        day_on = reason == "override-day"
        rows += f"""
<div class="rowcard">
  <div>
    <div class="kidname">{escape(k["display_name"])}</div>
    <div class="kiduser">{slug}</div>
  </div>
  <div>
    <div class="big">{"✅ " + escape(t(lang, "allowed")) if allow else "⛔ " + escape(t(lang, "blocked"))}{" ⚠️" if st.get("warn") else ""}</div>
    <div class="meta">{"".join(pills)}</div>
  </div>
  <div class="actions">
    <a class="link" href="/ui/child/{slug}">{escape(t(lang, "manage"))}</a>
    <form method="post" action="/ui/grant/{slug}/hour"><button class="btn" {"disabled" if day_on else ""}>+1h</button></form>
    <form method="post" action="/ui/grant/{slug}/day"><button class="btn">{escape(t(lang, "unlimited_off") if day_on else t(lang, "unlimited_today"))}</button></form>
  </div>
</div>"""

    if not rows:
        rows = f'<div class="card"><p class="small">{escape(t(lang, "no_children"))}</p></div>'

    add_form = f"""
<div class="card">
  <h2 style="margin:0 0 10px 0;font-size:16px">{escape(t(lang, "add_child"))}</h2>
  <form method="post" action="/ui/children/add">
    <div class="small">{escape(t(lang, "display_name"))}</div>
    <input name="display_name" placeholder="{escape(t(lang, "display_name_ph"))}" required/>
    <div style="margin-top:10px"><button class="btn" type="submit">{escape(t(lang, "create"))}</button></div>
  </form>
  <p class="small" style="margin-top:10px">{escape(t(lang, "add_child_hint"))}</p>
</div>"""

    nav = f'<a href="/dashboard">{escape(t(lang, "dashboard"))}</a><a href="/ui/audit">{escape(t(lang, "audit"))}</a><a href="/logout">{escape(t(lang, "logout"))}</a>'
    body = f'<div class="grid">{rows}{add_form}</div><p class="small" style="margin-top:12px">{escape(t(lang, "decision_order"))}</p>'
    return _shell("KidsControl", t(lang, "server_time", time=now_iso), body, nav=nav, flash=flash, lang=lang)


def _select(name: str, current: str, options: list[tuple[str, str]]) -> str:
    opts = []
    for value, label in options:
        selected = " selected" if value == current else ""
        opts.append(f'<option value="{escape(value)}"{selected}>{escape(label)}</option>')
    return f'<select name="{escape(name)}">{"".join(opts)}</select>'


def render_child_page(
    child: dict,
    schedules: dict,
    apps: list[dict],
    devices: list[dict],
    presets: list[str],
    flash: str | None = None,
    watches: list[dict] | None = None,
    lang: str = "de",
    setup_command: str = "",
) -> str:
    slug = escape(child["slug"])
    nav = (
        f'<a href="/dashboard">{escape(t(lang, "back_dashboard"))}</a>'
        f'<a href="/ui/child/{slug}">{escape(t(lang, "overview"))}</a>'
        f'<a href="/logout">{escape(t(lang, "logout"))}</a>'
    )
    setup_card = f"""
<div class="card">
  <h2 style="margin:0 0 8px 0;font-size:16px">{escape(t(lang, "client_setup_title"))}</h2>
  <p class="small">{escape(t(lang, "client_setup_intro"))}</p>
  <div class="notice">{escape(t(lang, "install_notice"))}</div>
  <form method="post" action="/ui/child/{slug}/enroll-token" style="margin:0 0 12px 0">
    <button class="btn ghost" type="submit">{escape(t(lang, "new_enroll_code"))}</button>
  </form>
  <div class="small" style="margin-top:8px">{escape(t(lang, "client_setup_cmd_label"))}</div>
  <pre style="white-space:pre-wrap;background:#0d1012;border:1px solid var(--border);border-radius:12px;padding:12px"><code>{escape(setup_command)}</code></pre>
  <p class="small" style="margin-top:10px">{escape(t(lang, "oneclick_hint"))}</p>
  <div class="actions" style="margin-top:10px;justify-content:flex-start">
    <a class="link" href="/ui/child/{slug}/oneclick/linux">{escape(t(lang, "oneclick_linux"))}</a>
    <a class="link" href="/ui/child/{slug}/oneclick/macos">{escape(t(lang, "oneclick_macos"))}</a>
    <a class="link" href="/ui/child/{slug}/oneclick/windows">{escape(t(lang, "oneclick_windows"))}</a>
  </div>
</div>"""

    # schedules table
    rows = ""
    for wd in range(7):
        s = schedules.get(wd) or {"start_min": 900, "end_min": 1110, "daily_minutes": 120}
        sh, sm = divmod(int(s["start_min"]), 60)
        eh, em = divmod(int(s["end_min"]), 60)
        rows += f"""
<tr>
  <td><b>{escape(weekday(lang, wd))}</b></td>
  <td><input name="wd{wd}_start_h" type="number" min="0" max="23" value="{sh}"></td>
  <td><input name="wd{wd}_start_m" type="number" min="0" max="59" value="{sm}"></td>
  <td><input name="wd{wd}_end_h" type="number" min="0" max="23" value="{eh}"></td>
  <td><input name="wd{wd}_end_m" type="number" min="0" max="59" value="{em}"></td>
  <td><input name="wd{wd}_daily" type="number" min="0" max="1440" value="{int(s["daily_minutes"])}"></td>
</tr>"""

    preset_opts = "".join(
        f'<option value="{escape(p)}">{escape(preset_label(lang, p))}</option>' for p in presets
    )

    schedule_card = f"""
<div class="card">
  <h2 style="margin:0 0 8px 0;font-size:16px">{escape(t(lang, "schedule_title"))}</h2>
  <form method="post" action="/ui/child/{slug}/schedule">
    <div class="two" style="margin-bottom:12px">
      <div>
                <div class="small">{escape(t(lang, "preset"))}</div>
        <select name="preset">{preset_opts}</select>
      </div>
      <div style="display:flex;align-items:flex-end;gap:8px;flex-wrap:wrap">
                <button class="btn ghost" name="action" value="apply_preset" type="submit">{escape(t(lang, "apply_preset"))}</button>
                <button class="btn" name="action" value="save" type="submit">{escape(t(lang, "save_schedule"))}</button>
                <button class="btn ghost" name="action" value="reset_daily" type="submit">{escape(t(lang, "reset_daily"))}</button>
      </div>
    </div>
    <table>
                <thead><tr><th>{escape(t(lang, "day"))}</th><th>{escape(t(lang, "start_h"))}</th><th>{escape(t(lang, "start_m"))}</th><th>{escape(t(lang, "end_h"))}</th><th>{escape(t(lang, "end_m"))}</th><th>{escape(t(lang, "min_day"))}</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <p class="small" style="margin-top:8px">{escape(t(lang, "zero_minutes"))}</p>
  </form>
</div>"""

    match_opts = [
        ("contains", t(lang, "contains")),
        ("exact", t(lang, "exact")),
        ("startswith", t(lang, "startswith")),
    ]
    scope_opts = [
        ("always", t(lang, "scope_always")),
        ("when_denied", t(lang, "scope_denied")),
    ]
    enabled_opts = [("1", t(lang, "on")), ("0", t(lang, "off"))]
    app_rows = ""
    for a in apps:
        enabled_val = "1" if a["enabled"] else "0"
        app_rows += f"""
<form method="post" action="/ui/child/{slug}/apps/{a["id"]}" class="two" style="margin-top:10px">
  <div><div class="small">{escape(t(lang, "name"))}</div><input name="label" value="{escape(a["label"] or "")}"/></div>
  <div><div class="small">{escape(t(lang, "pattern"))}</div><input name="pattern" value="{escape(a["pattern"])}" required/></div>
  <div><div class="small">{escape(t(lang, "match"))}</div>{_select("match_mode", a["match_mode"], match_opts)}</div>
  <div><div class="small">{escape(t(lang, "scope"))}</div>{_select("scope", a["scope"], scope_opts)}</div>
  <div><div class="small">{escape(t(lang, "status"))}</div>{_select("enabled", enabled_val, enabled_opts)}</div>
  <div style="display:flex;align-items:flex-end;gap:8px">
    <button class="btn" type="submit">{escape(t(lang, "save"))}</button>
  </div>
</form>
<form method="post" action="/ui/child/{slug}/apps/{a["id"]}/delete" style="margin:0 0 8px 0">
  <button class="btn danger" type="submit">{escape(t(lang, "delete"))}</button>
</form>"""
    if not app_rows:
        app_rows = f'<p class="small">{escape(t(lang, "no_apps"))}</p>'

    apps_card = f"""
<div class="card">
  <h2 style="margin:0 0 8px 0;font-size:16px">{escape(t(lang, "apps_title"))}</h2>
  <p class="small">{escape(t(lang, "apps_intro"))}</p>
  {app_rows}
  <form method="post" action="/ui/child/{slug}/apps/add" style="margin-top:12px;display:grid;gap:10px">
    <div class="two">
      <div>
        <div class="small">{escape(t(lang, "label_optional"))}</div>
        <input name="label" placeholder="Minecraft" autocomplete="off"/>
      </div>
      <div>
        <div class="small">{escape(t(lang, "pattern_required"))}</div>
        <input name="pattern" placeholder="{escape(t(lang, "pattern_ph"))}" required autocomplete="off"/>
      </div>
    </div>
    <div class="two">
      <div>
        <div class="small">{escape(t(lang, "match"))}</div>
        {_select("match_mode", "contains", match_opts)}
      </div>
      <div>
        <div class="small">{escape(t(lang, "scope"))}</div>
        {_select("scope", "always", scope_opts)}
      </div>
    </div>
    <div><button class="btn" type="submit">{escape(t(lang, "add_block"))}</button></div>
  </form>
</div>"""

    device_rows = ""
    for d in devices:
        last = d.get("last_seen_at") or t(lang, "never")
        device_rows += f"""
<tr>
  <td>{escape(d["name"])}</td>
  <td>{escape(d["os_family"])}</td>
  <td><code>{escape(d["hostname"] or "–")}</code></td>
  <td class="small">{escape(str(last))}</td>
  <td><code style="word-break:break-all">{escape(d["device_key"])}</code></td>
  <td>
    <form method="post" action="/ui/child/{slug}/devices/{d["id"]}/delete">
      <button class="btn danger" type="submit">{escape(t(lang, "remove"))}</button>
    </form>
  </td>
</tr>"""
    if not device_rows:
        device_rows = f'<tr><td colspan="6" class="small">{escape(t(lang, "no_devices"))}</td></tr>'

    devices_card = f"""
<div class="card">
  <h2 style="margin:0 0 8px 0;font-size:16px">{escape(t(lang, "devices_title"))}</h2>
  <p class="small">{escape(t(lang, "devices_intro"))}</p>
  <table style="margin-top:10px">
    <thead><tr><th>{escape(t(lang, "name"))}</th><th>{escape(t(lang, "os"))}</th><th>{escape(t(lang, "hostname"))}</th><th>{escape(t(lang, "last_seen"))}</th><th>Device-Key</th><th></th></tr></thead>
    <tbody>{device_rows}</tbody>
  </table>
  <form method="post" action="/ui/child/{slug}/devices/add" class="two" style="margin-top:12px">
    <div><div class="small">{escape(t(lang, "device_name"))}</div><input name="name" placeholder="Laptop" required/></div>
    <div>
      <div class="small">{escape(t(lang, "os_label"))}</div>
      <select name="os_family">
        <option value="linux">Linux</option>
        <option value="windows">Windows</option>
        <option value="macos">macOS</option>
        <option value="unknown">{escape(t(lang, "other"))}</option>
      </select>
    </div>
    <div style="grid-column:1/-1"><button class="btn" type="submit">{escape(t(lang, "add_device"))}</button></div>
  </form>
</div>"""

    warn_card = f"""
<div class="card">
  <h2 style="margin:0 0 8px 0;font-size:16px">{escape(t(lang, "settings"))}</h2>
  <form method="post" action="/ui/child/{slug}/settings" class="two">
    <div><div class="small">{escape(t(lang, "timezone"))}</div><input name="timezone" value="{escape(child["timezone"])}"/></div>
    <div><div class="small">{escape(t(lang, "warn_minutes"))}</div><input name="warn_minutes" type="number" min="0" max="120" value="{int(child["warn_minutes"])}"/></div>
    <div>
      <div class="small">{escape(t(lang, "active"))}</div>
      {_select("active", "1" if child["active"] else "0", [("1", t(lang, "yes")), ("0", t(lang, "no"))])}
    </div>
    <div style="display:flex;align-items:flex-end"><button class="btn" type="submit">{escape(t(lang, "save"))}</button></div>
  </form>
</div>"""

    watches = watches or []
    watch_rows = ""
    for w in watches:
        watch_rows += f"""
<tr>
  <td>{escape(w.get("label") or w["package_name"])}</td>
  <td><code>{escape(w["package_name"])}</code></td>
  <td>
    <form method="post" action="/ui/child/{slug}/watches/{w["id"]}/delete">
      <button class="btn danger" type="submit">{escape(t(lang, "remove"))}</button>
    </form>
  </td>
</tr>"""
    if not watch_rows:
        watch_rows = f'<tr><td colspan="3" class="small">{escape(t(lang, "no_watches"))}</td></tr>'

    version_blocks = ""
    for d in devices:
        rows = ""
        for item in d.get("software") or []:
            rows += f"""
<tr>
  <td><code>{escape(item["package_name"])}</code></td>
  <td>{escape(item["version"] or "–")}</td>
  <td>{escape(item["source"])}</td>
  <td class="small">{escape(item.get("reported_at") or "")}</td>
  <td>
    <form method="post" action="/ui/child/{slug}/devices/{d["id"]}/update">
      <input type="hidden" name="package_name" value="{escape(item["package_name"])}"/>
      <button class="btn" type="submit">{escape(t(lang, "update"))}</button>
    </form>
  </td>
</tr>"""
        if not rows:
            rows = f'<tr><td colspan="5" class="small">{escape(t(lang, "no_versions"))}</td></tr>'
        cmd_bits = ""
        for c in d.get("commands") or []:
            cmd_bits += f'<div class="small">#{c["id"]} {escape(c["kind"])} {escape(c.get("package_name") or t(lang, "all"))} via {escape(c["via"])}: {escape(c["status"])} {escape(c.get("output") or "")}</div>'
        ssh_on = "selected" if d.get("ssh_enabled") else ""
        ssh_off = "" if d.get("ssh_enabled") else "selected"
        version_blocks += f"""
<div class="card">
  <h3 style="margin:0 0 8px 0;font-size:15px">{escape(d["name"])} · {escape(t(lang, "software_title"))}</h3>
  <table>
    <thead><tr><th>{escape(t(lang, "package"))}</th><th>{escape(t(lang, "version"))}</th><th>{escape(t(lang, "source"))}</th><th>{escape(t(lang, "reported"))}</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <form method="post" action="/ui/child/{slug}/devices/{d["id"]}/update" style="margin-top:10px">
    <button class="btn ghost" type="submit">{escape(t(lang, "update_all"))}</button>
  </form>
  <div style="margin-top:8px">{cmd_bits}</div>
  <h3 style="margin:16px 0 8px 0;font-size:15px">{escape(t(lang, "ssh_title"))}</h3>
  <p class="small">{escape(t(lang, "ssh_intro"))}</p>
  <form method="post" action="/ui/child/{slug}/devices/{d["id"]}/ssh" class="two">
    <div>
      <div class="small">{escape(t(lang, "ssh_active"))}</div>
      <select name="ssh_enabled">
        <option value="0" {ssh_off}>{escape(t(lang, "no"))}</option>
        <option value="1" {ssh_on}>{escape(t(lang, "yes"))}</option>
      </select>
    </div>
    <div><div class="small">{escape(t(lang, "host"))}</div><input name="ssh_host" value="{escape(d.get("ssh_host") or d.get("hostname") or "")}" placeholder="192.168.1.20"/></div>
    <div><div class="small">{escape(t(lang, "port"))}</div><input name="ssh_port" type="number" min="1" max="65535" value="{int(d.get("ssh_port") or 22)}"/></div>
    <div><div class="small">{escape(t(lang, "user"))}</div><input name="ssh_user" value="{escape(d.get("ssh_user") or "")}" placeholder="kids"/></div>
    <div style="grid-column:1/-1"><div class="small">{escape(t(lang, "key_path"))}</div><input name="ssh_key_path" value="{escape(d.get("ssh_key_path") or "")}" readonly/></div>
    <div style="grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn" type="submit">{escape(t(lang, "save_ssh"))}</button>
    </div>
  </form>
  <form method="post" action="/ui/child/{slug}/devices/{d["id"]}/ssh-test" style="margin-top:8px">
    <button class="btn ghost" type="submit">{escape(t(lang, "test_ssh"))}</button>
  </form>
</div>"""

    software_card = f"""
<div class="card">
  <h2 style="margin:0 0 8px 0;font-size:16px">{escape(t(lang, "software_title"))}</h2>
  <p class="small">{escape(t(lang, "software_intro"))}</p>
  <table style="margin-top:10px">
    <thead><tr><th>{escape(t(lang, "name"))}</th><th>{escape(t(lang, "package"))}</th><th></th></tr></thead>
    <tbody>{watch_rows}</tbody>
  </table>
  <form method="post" action="/ui/child/{slug}/watches/add" class="two" style="margin-top:12px">
    <div><div class="small">{escape(t(lang, "display_name"))}</div><input name="label" placeholder="Firefox" autocomplete="off"/></div>
    <div><div class="small">{escape(t(lang, "package_name"))}</div><input name="package_name" placeholder="firefox" required autocomplete="off"/></div>
    <div style="grid-column:1/-1"><button class="btn" type="submit">{escape(t(lang, "watch"))}</button></div>
  </form>
</div>
{version_blocks}"""

    body = f'<div class="grid">{setup_card}{warn_card}{schedule_card}{apps_card}{devices_card}{software_card}</div>'
    return _shell(
        f'{child["display_name"]}',
        t(lang, "child_sub", slug=child["slug"]),
        body,
        nav=nav,
        flash=flash,
        lang=lang,
    )


def render_audit(entries: list[dict], flash: str | None = None, lang: str = "de") -> str:
    rows = ""
    for e in entries:
        rows += f"""
<tr>
  <td class="small">{escape(str(e["at"]))}</td>
  <td>{escape(e["actor"])}</td>
  <td>{escape(e.get("child_slug") or "–")}</td>
  <td>{escape(e["action"])}</td>
  <td class="small">{escape(e.get("details") or "")}</td>
</tr>"""
    if not rows:
        rows = f'<tr><td colspan="5" class="small">{escape(t(lang, "no_audit"))}</td></tr>'
    nav = f'<a href="/dashboard">{escape(t(lang, "dashboard"))}</a><a href="/ui/audit">{escape(t(lang, "audit"))}</a><a href="/logout">{escape(t(lang, "logout"))}</a>'
    body = f"""
<div class="grid">
  <div class="card">
    <table>
      <thead><tr><th>{escape(t(lang, "time"))}</th><th>{escape(t(lang, "actor"))}</th><th>{escape(t(lang, "child"))}</th><th>{escape(t(lang, "action"))}</th><th>{escape(t(lang, "details"))}</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>"""
    return _shell(t(lang, "audit_title"), t(lang, "audit_sub"), body, nav=nav, flash=flash, lang=lang)
