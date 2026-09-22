"""Server-rendered parent UI (German)."""

from __future__ import annotations

from html import escape

from app.policy import REASON_LABELS_DE

WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


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


def _shell(title: str, subtitle: str, body: str, *, nav: str = "", flash: str | None = None) -> str:
    flash_html = ""
    if flash:
        flash_html = f'<div class="flash">{escape(flash)}</div>'
    return f"""<!doctype html>
<html lang="de">
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
        <div class="nav">{nav}</div>
      </div>
      {flash_html}
      {body}
    </div>
  </div>
</body>
</html>"""


def render_login(admin_user: str, error: str | None = None) -> str:
    err = f'<div class="flash err">{escape(error)}</div>' if error else ""
    body = f"""
<div class="grid" style="max-width:720px;margin-top:14px">
  <div class="card">
    <h2 style="margin:0 0 8px 0;font-size:18px">Eltern-Login</h2>
    <p class="small">Zentraler Hub für Nutzungszeit und App-Sperren – unabhängig vom Betriebssystem der Kinder-PCs.</p>
    {err}
    <form method="post" action="/login" style="margin-top:12px;display:grid;gap:10px">
      <div>
        <div class="small">Benutzername</div>
        <input name="username" value="{escape(admin_user)}" required/>
      </div>
      <div>
        <div class="small">Passwort</div>
        <input name="password" type="password" required/>
      </div>
      <button class="btn" type="submit">Anmelden</button>
    </form>
  </div>
</div>"""
    return _shell("KidsControl", "Anmelden", body, nav="")


def render_dashboard(now_iso: str, kids: list[dict], flash: str | None = None) -> str:
    rows = ""
    for k in kids:
        st = k.get("state") or {}
        allow = bool(st.get("allow"))
        reason = st.get("reason", "")
        reason_de = REASON_LABELS_DE.get(reason, reason)
        pills = [_pill("Grund", reason_de, mint=True)]
        if st.get("remaining_minutes") is not None:
            pills.append(_pill("Rest", f'{st["remaining_minutes"]} Min', mint=True))
        if st.get("daily_remaining") is not None and st.get("daily_limit") is not None:
            pills.append(_pill("Tagesbudget", f'{st["daily_remaining"]}/{st["daily_limit"]} Min'))
        blocked_n = int(k.get("blocked_app_count") or 0)
        if blocked_n:
            pills.append(_pill("App-Sperren", str(blocked_n), danger=True))
        devices = k.get("devices") or []
        if devices:
            pills.append(_pill("Geräte", ", ".join(d["name"] for d in devices)))
        else:
            pills.append(_pill("Geräte", "keines", danger=True))

        slug = escape(k["slug"])
        day_on = reason == "override-day"
        rows += f"""
<div class="rowcard">
  <div>
    <div class="kidname">{escape(k["display_name"])}</div>
    <div class="kiduser">{slug}</div>
  </div>
  <div>
    <div class="big">{"✅ Erlaubt" if allow else "⛔ Gesperrt"}{" ⚠️" if st.get("warn") else ""}</div>
    <div class="meta">{"".join(pills)}</div>
  </div>
  <div class="actions">
    <a class="link" href="/ui/child/{slug}">Verwalten</a>
    <form method="post" action="/ui/grant/{slug}/hour"><button class="btn" {"disabled" if day_on else ""}>+1h</button></form>
    <form method="post" action="/ui/grant/{slug}/day"><button class="btn">{"Unbegrenzt aus" if day_on else "Heute unbegrenzt"}</button></form>
  </div>
</div>"""

    if not rows:
        rows = '<div class="card"><p class="small">Noch keine Kinder angelegt.</p></div>'

    add_form = """
<div class="card">
  <h2 style="margin:0 0 10px 0;font-size:16px">Kind hinzufügen</h2>
  <form method="post" action="/ui/children/add" class="two">
    <div><div class="small">Anzeigename</div><input name="display_name" placeholder="z.B. Mia" required/></div>
    <div><div class="small">Kurz-ID (slug)</div><input name="slug" placeholder="z.B. mia" required pattern="[a-z0-9_\\-]{2,32}"/></div>
    <div style="grid-column:1/-1"><button class="btn" type="submit">Anlegen</button></div>
  </form>
  <p class="small" style="margin-top:10px">Die Kurz-ID erscheint in der Agent-Konfiguration und darf später nicht geändert werden.</p>
</div>"""

    nav = '<a href="/dashboard">Dashboard</a><a href="/ui/audit">Protokoll</a><a href="/logout">Logout</a>'
    body = f'<div class="grid">{rows}{add_form}</div><p class="small" style="margin-top:12px">Entscheidungsreihenfolge: Tages-Override → Stunden-Override → Zeitfenster → Tagesbudget. App-Sperren gelten zusätzlich während erlaubter Zeit.</p>'
    return _shell("KidsControl", f"Serverzeit {now_iso}", body, nav=nav, flash=flash)


def render_child_page(
    child: dict,
    schedules: dict,
    apps: list[dict],
    devices: list[dict],
    presets: list[str],
    flash: str | None = None,
) -> str:
    slug = escape(child["slug"])
    nav = f'<a href="/dashboard">← Dashboard</a><a href="/ui/child/{slug}">Übersicht</a><a href="/logout">Logout</a>'

    # schedules table
    rows = ""
    for wd in range(7):
        s = schedules.get(wd) or {"start_min": 900, "end_min": 1110, "daily_minutes": 120}
        sh, sm = divmod(int(s["start_min"]), 60)
        eh, em = divmod(int(s["end_min"]), 60)
        rows += f"""
<tr>
  <td><b>{WEEKDAYS_DE[wd]}</b></td>
  <td><input name="wd{wd}_start_h" type="number" min="0" max="23" value="{sh}"></td>
  <td><input name="wd{wd}_start_m" type="number" min="0" max="59" value="{sm}"></td>
  <td><input name="wd{wd}_end_h" type="number" min="0" max="23" value="{eh}"></td>
  <td><input name="wd{wd}_end_m" type="number" min="0" max="59" value="{em}"></td>
  <td><input name="wd{wd}_daily" type="number" min="0" max="1440" value="{int(s["daily_minutes"])}"></td>
</tr>"""

    preset_opts = "".join(f'<option value="{escape(p)}">{escape(p)}</option>' for p in presets)

    schedule_card = f"""
<div class="card">
  <h2 style="margin:0 0 8px 0;font-size:16px">Zeitplan & Tagesbudget</h2>
  <form method="post" action="/ui/child/{slug}/schedule">
    <div class="two" style="margin-bottom:12px">
      <div>
        <div class="small">Preset</div>
        <select name="preset">{preset_opts}</select>
      </div>
      <div style="display:flex;align-items:flex-end;gap:8px;flex-wrap:wrap">
        <button class="btn ghost" name="action" value="apply_preset" type="submit">Preset anwenden</button>
        <button class="btn" name="action" value="save" type="submit">Zeitplan speichern</button>
        <button class="btn ghost" name="action" value="reset_daily" type="submit">Tagesnutzung zurücksetzen</button>
      </div>
    </div>
    <table>
      <thead><tr><th>Tag</th><th>Start h</th><th>Start m</th><th>Ende h</th><th>Ende m</th><th>Min/Tag</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <p class="small" style="margin-top:8px">0 Minuten/Tag = kein Zugriff an diesem Wochentag.</p>
  </form>
</div>"""

    app_rows = ""
    for a in apps:
        app_rows += f"""
<tr>
  <td>{escape(a["label"] or a["pattern"])}</td>
  <td><code>{escape(a["pattern"])}</code></td>
  <td>{escape(a["match_mode"])}</td>
  <td>{escape(a["scope"])}</td>
  <td>{"an" if a["enabled"] else "aus"}</td>
  <td>
    <form method="post" action="/ui/child/{slug}/apps/{a["id"]}/delete">
      <button class="btn danger" type="submit">Löschen</button>
    </form>
  </td>
</tr>"""
    if not app_rows:
        app_rows = '<tr><td colspan="6" class="small">Noch keine App-Sperren.</td></tr>'

    apps_card = f"""
<div class="card">
  <h2 style="margin:0 0 8px 0;font-size:16px">App-Sperren</h2>
  <p class="small">Der Agent beendet passende Prozesse auf Windows, macOS und Linux. Muster beziehen sich auf Prozess- bzw. Dateinamen (z.B. <code>minecraft</code>, <code>RobloxPlayerBeta.exe</code>, <code>steam</code>).</p>
  <table style="margin-top:10px">
    <thead><tr><th>Name</th><th>Muster</th><th>Match</th><th>Geltung</th><th>Status</th><th></th></tr></thead>
    <tbody>{app_rows}</tbody>
  </table>
  <form method="post" action="/ui/child/{slug}/apps/add" class="two" style="margin-top:12px">
    <div><div class="small">Anzeigename</div><input name="label" placeholder="Minecraft"/></div>
    <div><div class="small">Prozess-Muster</div><input name="pattern" placeholder="minecraft" required/></div>
    <div>
      <div class="small">Match</div>
      <select name="match_mode">
        <option value="contains">enthält</option>
        <option value="exact">exakt</option>
        <option value="startswith">beginnt mit</option>
      </select>
    </div>
    <div>
      <div class="small">Geltung</div>
      <select name="scope">
        <option value="always">immer sperren</option>
        <option value="when_denied">nur wenn Sitzung gesperrt</option>
      </select>
    </div>
    <div style="grid-column:1/-1"><button class="btn" type="submit">App-Sperre hinzufügen</button></div>
  </form>
</div>"""

    device_rows = ""
    for d in devices:
        last = d.get("last_seen_at") or "noch nie"
        device_rows += f"""
<tr>
  <td>{escape(d["name"])}</td>
  <td>{escape(d["os_family"])}</td>
  <td><code>{escape(d["hostname"] or "–")}</code></td>
  <td class="small">{escape(str(last))}</td>
  <td><code style="word-break:break-all">{escape(d["device_key"])}</code></td>
  <td>
    <form method="post" action="/ui/child/{slug}/devices/{d["id"]}/delete">
      <button class="btn danger" type="submit">Entfernen</button>
    </form>
  </td>
</tr>"""
    if not device_rows:
        device_rows = '<tr><td colspan="6" class="small">Noch kein Gerät. Lege eines an und kopiere den Schlüssel in den Agenten.</td></tr>'

    devices_card = f"""
<div class="card">
  <h2 style="margin:0 0 8px 0;font-size:16px">Geräte (Agenten)</h2>
  <p class="small">Jedes Kinder-PC registriert sich mit einem Geräte-Schlüssel. Der Agent pollt den Server und setzt Zeit- sowie App-Regeln lokal durch.</p>
  <table style="margin-top:10px">
    <thead><tr><th>Name</th><th>OS</th><th>Hostname</th><th>Zuletzt gesehen</th><th>Device-Key</th><th></th></tr></thead>
    <tbody>{device_rows}</tbody>
  </table>
  <form method="post" action="/ui/child/{slug}/devices/add" class="two" style="margin-top:12px">
    <div><div class="small">Gerätename</div><input name="name" placeholder="Laptop Wohnzimmer" required/></div>
    <div>
      <div class="small">Betriebssystem</div>
      <select name="os_family">
        <option value="linux">Linux</option>
        <option value="windows">Windows</option>
        <option value="macos">macOS</option>
        <option value="unknown">Sonstiges</option>
      </select>
    </div>
    <div style="grid-column:1/-1"><button class="btn" type="submit">Gerät anlegen</button></div>
  </form>
</div>"""

    warn_card = f"""
<div class="card">
  <h2 style="margin:0 0 8px 0;font-size:16px">Einstellungen</h2>
  <form method="post" action="/ui/child/{slug}/settings" class="two">
    <div><div class="small">Zeitzone</div><input name="timezone" value="{escape(child["timezone"])}"/></div>
    <div><div class="small">Vorwarnung (Minuten vor Fensterende)</div><input name="warn_minutes" type="number" min="0" max="120" value="{int(child["warn_minutes"])}"/></div>
    <div>
      <div class="small">Aktiv</div>
      <select name="active">
        <option value="1" {"selected" if child["active"] else ""}>ja</option>
        <option value="0" {"selected" if not child["active"] else ""}>nein</option>
      </select>
    </div>
    <div style="display:flex;align-items:flex-end"><button class="btn" type="submit">Speichern</button></div>
  </form>
</div>"""

    body = f'<div class="grid">{warn_card}{schedule_card}{apps_card}{devices_card}</div>'
    return _shell(
        f'{child["display_name"]}',
        f'Kind {child["slug"]}',
        body,
        nav=nav,
        flash=flash,
    )


def render_audit(entries: list[dict], flash: str | None = None) -> str:
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
        rows = '<tr><td colspan="5" class="small">Noch keine Einträge.</td></tr>'
    nav = '<a href="/dashboard">Dashboard</a><a href="/ui/audit">Protokoll</a><a href="/logout">Logout</a>'
    body = f"""
<div class="grid">
  <div class="card">
    <table>
      <thead><tr><th>Zeit</th><th>Akteur</th><th>Kind</th><th>Aktion</th><th>Details</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>"""
    return _shell("Protokoll", "Nachvollziehbare Eltern-Aktionen", body, nav=nav, flash=flash)
