"""UI rendering helpers (pure HTML/CSS)

Exports used by main.py:
- CSS: str  -> the full CSS stylesheet
- css_block(): str -> same as CSS (compat helper)
- render_login_page(css: str, admin_user: str) -> str
- render_dashboard(css: str, now_iso: str, kids: list[dict]) -> str
- render_trace(css: str, user: str, display_name: str, data: dict) -> str
- render_schedule_editor(css: str, user: str, display_name: str, schedules: dict, presets: dict, profiles: list[str]) -> str
- render_child_view(css: str, user: str, display_name: str, data: dict) -> str
"""

from __future__ import annotations

from html import escape

REASON_MAP_DE = {
    "override": "Sonderfreigabe (+1 Stunde)",
    "override-day": "Heute unbegrenzt",
    "schedule": "Zeitplan",
    "outside-time": "Außerhalb der Zeit",
    "no-schedule": "Kein Zeitplan",
    "unknown-user": "Unbekannter Benutzer",
    "daily-limit-reached": "Tageslimit erreicht",
    "no-daily-minutes": "Kein Zugriff (0 Minuten)",
}

WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def css() -> str:
    return r"""
:root{
  --bg:#0f1214;
  --panel:#151a1d;
  --panel2:#111518;
  --text:#e7ecef;
  --muted:#a9b4bb;
  --border:#2a3338;
  --mint:#0f7f66;
  --mint2:#10a37f;
  --shadow: 0 18px 50px rgba(0,0,0,.45);
  --r:16px;
}
*{ box-sizing:border-box; }
body{
  margin:0;
  font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  background:
    radial-gradient(1200px 600px at 30% 10%, rgba(16,163,127,.10), transparent 60%),
    radial-gradient(900px 600px at 70% 20%, rgba(15,127,102,.08), transparent 55%),
    var(--bg);
  color:var(--text);
}
.wrap{ padding: clamp(18px, 3vw, 42px); }
.container{ width:min(1400px, 100%); margin:0 auto; }
.topbar{
  display:flex; align-items:center; justify-content:space-between; gap:12px;
  padding: 14px 16px;
  border:1px solid var(--border);
  border-radius: var(--r);
  background: linear-gradient(180deg, rgba(16,163,127,.08), rgba(0,0,0,0)), var(--panel2);
  box-shadow: var(--shadow);
}
.title{ display:flex; flex-direction:column; gap:4px; }
.title h1{ margin:0; font-size:20px; letter-spacing:.2px; }
.title small{ color:var(--muted); }
.nav{ display:flex; gap:10px; align-items:center; flex-wrap:wrap;}
.nav a{
  color:var(--text); text-decoration:none;
  padding: 10px 12px; border-radius: 12px;
  border:1px solid var(--border);
  background: rgba(255,255,255,.02);
}
.nav a:hover{ border-color: rgba(16,163,127,.55); }
.grid{ margin-top: 14px; display:grid; gap: 12px; }
.card{
  border-radius: var(--r);
  border:1px solid var(--border);
  background: var(--panel);
  box-shadow: 0 10px 30px rgba(0,0,0,.25);
  padding: 14px 16px;
}
.rowcard{
  display:grid;
  grid-template-columns: 260px 1fr 480px;
  gap: 14px;
  padding: 14px 16px;
  border-radius: var(--r);
  border:1px solid var(--border);
  background: var(--panel);
  box-shadow: 0 10px 30px rgba(0,0,0,.25);
}
@media (max-width: 1200px){
  .rowcard{ grid-template-columns: 1fr; }
  .actions{ justify-content:flex-start; flex-wrap:wrap; }
}
.kidname{ font-weight: 800; font-size: 16px; }
.kiduser{ color:var(--muted); font-size: 12px; margin-top: 4px; }
.big{ font-size: 22px; }
.meta{ margin-top: 8px; display:flex; gap:8px; flex-wrap:wrap; }
.pill{
  display:inline-flex; align-items:center;
  padding: 6px 10px;
  border-radius: 999px;
  border:1px solid var(--border);
  color: var(--muted);
  font-size: 12px;
  background: rgba(0,0,0,.18);
}
.pill.mint{
  border-color: rgba(16,163,127,.45);
  color: var(--text);
  background: rgba(16,163,127,.10);
}
.actions{ display:flex; gap:10px; align-items:center; justify-content:flex-end; }
form{ margin:0; }
.btn{
  cursor:pointer;
  padding: 10px 12px;
  border-radius: 12px;
  border:1px solid rgba(16,163,127,.45);
  background: linear-gradient(180deg, rgba(16,163,127,.22), rgba(16,163,127,.12));
  color: var(--text);
  font-weight: 700;
}
.btn:hover{ border-color: rgba(16,163,127,.75); }
.btn.ghost{
  border-color: var(--border);
  background: rgba(255,255,255,.03);
  color: var(--text);
}
.btn.ghost:hover{ border-color: rgba(16,163,127,.55); }
.btn:disabled{ opacity:.55; cursor:not-allowed; }
.link{
  color: var(--mint2);
  text-decoration:none;
  padding: 10px 10px;
  border-radius: 12px;
  border:1px solid var(--border);
  background: rgba(0,0,0,.10);
}
.link:hover{ border-color: rgba(16,163,127,.55); }
table{ width:100%; border-collapse: collapse; }
th, td{ padding: 10px 8px; border-bottom:1px solid rgba(255,255,255,.06); text-align:left; }
th{ color: var(--muted); font-weight: 700; font-size: 12px; letter-spacing:.4px; text-transform: uppercase;}
input, select{
  width:100%;
  padding: 10px 10px;
  border-radius: 12px;
  border:1px solid var(--border);
  background: #0d1012;
  color: var(--text);
  outline:none;
}
input:focus, select:focus{ border-color: rgba(16,163,127,.65); box-shadow: 0 0 0 4px rgba(16,163,127,.12); }
details{ border:1px solid var(--border); border-radius: 12px; padding: 10px 12px; background: rgba(0,0,0,.14); }
summary{ cursor:pointer; color: var(--mint2); font-weight: 700; }
.small{ color: var(--muted); font-size: 12px; }
"""


# Back-compat exports expected by main.py
CSS: str = css()


def css_block() -> str:
    """Compatibility helper: some code imports css_block() instead of CSS."""
    return CSS


def _pill(label: str, value: str, mint: bool = False) -> str:
    cls = "pill mint" if mint else "pill"
    return f'<span class="{cls}"><b>{escape(label)}:</b>&nbsp;{escape(value)}</span>'


def render_login_page(css: str, admin_user: str) -> str:
    return f"""
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>KidsControl – Login</title>
  <style>{css}</style>
</head>
<body>
  <div class="wrap">
    <div class="container" style="max-width:1100px;">
      <div class="card" style="display:grid;grid-template-columns: 1.2fr .8fr; gap:14px;">
        <div>
          <h1 style="margin:0 0 10px 0;">🧒 KidsControl</h1>
          <p class="small">Eltern-Dashboard für Zeitfenster, Tages-Minuten und Overrides.</p>
          <div class="pill mint" style="width:fit-content;margin-top:10px;">Admin-Login • Passwort aktiv</div>
        </div>
        <div>
          <h2 style="margin:0 0 8px 0;font-size:18px;">Login</h2>
          <form method="post" action="/login">
            <label class="small">Benutzername</label>
            <input name="username" value="{escape(admin_user)}" required />
            <label class="small" style="margin-top:10px;">Passwort</label>
            <input name="password" type="password" placeholder="••••••••" required />
            <div style="margin-top:12px;">
              <button class="btn" type="submit">Anmelden</button>
            </div>
          </form>
          <div class="small" style="margin-top:10px;">Passwort kommt aus <code>KIDSCONTROL_ADMIN_PASSWORD</code>.</div>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""


def render_dashboard(css: str, now_iso: str, kids: list[dict]) -> str:
    rows_html = ""
    for k in kids:
        u = k["username"]
        dn = k["display_name"]
        st = k.get("state") or {}
        allow = bool(st.get("allow"))
        reason = st.get("reason", "")
        reason_de = REASON_MAP_DE.get(reason, reason)
        warn = bool(st.get("warn", False))

        status_icon = "✅" if allow else "⛔"
        warn_icon = "⚠️" if warn else ""

        pills = [_pill("Grund", reason_de, mint=True)]

        if reason == "override-day":
            pills.append(_pill("Sonderfreigabe", "Heute unbegrenzt", mint=True))
        elif reason == "override":
            pills.append(_pill("Sonderfreigabe", str(st.get("override_text") or "aktiv"), mint=True))

        if st.get("minutes_left_window") is not None:
            pills.append(_pill("Zeitfenster", f'noch {st.get("minutes_left_window")} Min', mint=False))
        if st.get("daily_remaining") is not None and st.get("daily_limit") is not None:
            pills.append(_pill("Tagesbudget", f'{st.get("daily_remaining")}/{st.get("daily_limit")} Min', mint=True))

        pills_html = "".join(pills)

        day_override_active = (reason == "override-day")
        hour_disabled = "disabled" if day_override_active else ""

        rows_html += f"""
<div class="rowcard">
  <div class="kid">
    <div class="kidname">{escape(dn)}</div>
    <div class="kiduser">{escape(u)}</div>
  </div>

  <div class="state">
    <div class="big">{status_icon} {warn_icon}</div>
    <div class="meta">{pills_html}</div>
  </div>

  <div class="actions">
    <a class="link" href="/ui/schedule/{escape(u)}">Zeitplan</a>
    <form method="post" action="/grant/{escape(u)}/hour">
      <button class="btn" {hour_disabled}>+1h</button>
    </form>
    <form method="post" action="/grant/{escape(u)}/day">
      <button class="btn">{'Unbegrenzt aus' if day_override_active else 'Heute unbegrenzt'}</button>
    </form>
    <form method="post" action="/ui/reset-daily/{escape(u)}">
      <button class="btn ghost">Tag zurücksetzen</button>
    </form>
    <a class="link" href="/trace/{escape(u)}">Log</a>
  </div>
</div>
"""

    return f"""
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>KidsControl – Dashboard</title>
  <style>{css}</style>
</head>
<body>
  <div class="wrap">
    <div class="container">
      <div class="topbar">
        <div class="title">
          <h1>🧒 KidsControl</h1>
          <small>Serverzeit: {escape(now_iso)}</small>
        </div>
        <div class="nav">
          <a href="/healthz" target="_blank">Health</a>
          <a href="/logout">Logout</a>
        </div>
      </div>

      <div class="grid">
        {rows_html}
      </div>

      <div class="small" style="margin-top:12px;">
        Entscheidungsreihenfolge: Override → Zeitplan → Tagesbudget → Vorwarnung.
      </div>
    </div>
  </div>
</body>
</html>
"""


def render_trace(css: str, user: str, display_name: str, data: dict) -> str:
    allow = bool(data.get("allow"))
    erlaubnis = "Erlaubt" if allow else "Gesperrt"
    reason = data.get("reason", "")
    reason_de = REASON_MAP_DE.get(reason, reason)

    pills = [_pill("Ergebnis", erlaubnis, mint=allow), _pill("Grund", reason_de, mint=True)]
    if data.get("override_text"):
        pills.append(_pill("Sonderfreigabe", str(data["override_text"]), mint=True))
    if data.get("daily_remaining") is not None and data.get("daily_limit") is not None:
        pills.append(_pill("Tagesbudget", f'{data["daily_remaining"]}/{data["daily_limit"]} Min', mint=True))
    if data.get("minutes_left_window") is not None:
        pills.append(_pill("Zeitfenster", f'noch {data["minutes_left_window"]} Min', mint=False))

    pills_html = "".join(pills)

    def row(k, v):
        return f"<tr><td class='small'>{escape(k)}</td><td><code>{escape(str(v))}</code></td></tr>"

    details = ""
    for k in ["reason", "override_text", "minutes_left_window", "window_end_hm", "daily_used", "daily_remaining", "daily_limit", "warn"]:
        if k in data and data[k] not in (None, ""):
            details += row(k, data[k])
    if not details:
        details = "<tr><td colspan='2' class='small'>Keine Details.</td></tr>"

    dbg = data.get("debug") or {}
    dbg_rows = ""
    for k in sorted(dbg.keys()):
        dbg_rows += row(k, dbg[k])
    if not dbg_rows:
        dbg_rows = "<tr><td colspan='2' class='small'>Kein Debug.</td></tr>"

    expl = "Erlaubt, weil " if allow else "Gesperrt, weil "
    expl += reason_de.lower()

    return f"""
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>KidsControl – Log: {escape(user)}</title>
  <style>{css}</style>
</head>
<body>
  <div class="wrap">
    <div class="container">
      <div class="topbar">
        <div class="title">
          <h1>🔎 Log: {escape(display_name)}</h1>
          <small>{escape(user)} • Erklärbarkeit statt Blackbox</small>
        </div>
        <div class="nav">
          <a href="/dashboard">← Dashboard</a>
          <a href="/logout">Logout</a>
        </div>
      </div>

      <div class="grid">
        <div class="card">
          <div class="small" style="margin-bottom:10px;">{escape(expl)}.</div>
          <div class="meta">{pills_html}</div>
          <table style="margin-top:12px;">
            {details}
          </table>
        </div>

        <details>
          <summary>Debug (Rohdaten)</summary>
          <div style="margin-top:10px;">
            <table>
              {dbg_rows}
            </table>
          </div>
        </details>
      </div>
    </div>
  </div>
</body>
</html>
"""


def render_schedule_editor(css: str, user: str, display_name: str, schedules: dict, presets: dict, profiles: list[str]) -> str:
    def hm(mins: int):
        h = mins // 60
        m = mins % 60
        return h, m

    preset_opts = "".join([f"<option value='{escape(name)}'>{escape(name)}</option>" for name in presets.keys()])
    profile_opts = "".join([f"<option value='{escape(name)}'>{escape(name)}</option>" for name in profiles])

    rows = ""
    for wd in range(7):
        s = schedules.get(wd) or {"start_min": 900, "end_min": 1110, "daily_minutes": 120}
        sh, sm = hm(int(s["start_min"]))
        eh, em = hm(int(s["end_min"]))
        dm = int(s["daily_minutes"])
        rows += f"""
<tr>
  <td><b>{WEEKDAYS_DE[wd]}</b></td>
  <td style="width:90px;"><input name="wd{wd}_start_h" type="number" min="0" max="23" value="{sh}"></td>
  <td style="width:90px;"><input name="wd{wd}_start_m" type="number" min="0" max="59" value="{sm}"></td>
  <td style="width:90px;"><input name="wd{wd}_end_h" type="number" min="0" max="23" value="{eh}"></td>
  <td style="width:90px;"><input name="wd{wd}_end_m" type="number" min="0" max="59" value="{em}"></td>
  <td style="width:140px;"><input name="wd{wd}_daily" type="number" min="0" max="1440" value="{dm}"></td>
</tr>
"""

    return f"""
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>KidsControl – Zeitplan: {escape(display_name)}</title>
  <style>{css}</style>
</head>
<body>
  <div class="wrap">
    <div class="container">
      <div class="topbar">
        <div class="title">
          <h1>🗓️ Zeitplan: {escape(display_name)}</h1>
          <small>{escape(user)} • 0 Minuten = kein Zugriff</small>
        </div>
        <div class="nav">
          <a href="/dashboard">← Dashboard</a>
          <a href="/logout">Logout</a>
        </div>
      </div>

      <div class="grid">
        <div class="card">
          <form method="post" action="/ui/schedule/{escape(user)}">
            <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end;">
              <div style="min-width:260px;">
                <div class="small">Preset (Zeitplan)</div>
                <select name="preset">
                  {preset_opts}
                </select>
              </div>
              <div style="display:flex; gap:10px; flex-wrap:wrap;">
                <button class="btn" name="action" value="apply_preset" type="submit">Preset anwenden</button>
                <button class="btn ghost" name="action" value="save_profile" type="submit">Profil sichern</button>
                <button class="btn ghost" name="action" value="load_profile" type="submit">Profil laden</button>
              </div>

              <div style="min-width:280px; flex: 1 1 280px;">
                <div class="small">Profilname (zum Sichern/Laden)</div>
                <input name="profile_name" placeholder="z.B. Schule-Winter" list="profilelist">
                <datalist id="profilelist">{profile_opts}</datalist>
              </div>
            </div>

            <div style="margin-top:14px;">
              <table>
                <thead>
                  <tr>
                    <th>Tag</th><th>Start (h)</th><th>Start (m)</th><th>Ende (h)</th><th>Ende (m)</th><th>Tagesminuten</th>
                  </tr>
                </thead>
                <tbody>{rows}</tbody>
              </table>
            </div>

            <div style="display:flex; gap:10px; margin-top:12px; flex-wrap:wrap;">
              <button class="btn" name="action" value="save_schedule" type="submit">Zeitplan speichern</button>
              <a class="link" href="/trace/{escape(user)}">Log ansehen</a>
            </div>

            <div class="small" style="margin-top:10px;">
              Tagesminuten <b>0</b> sperrt komplett (auch wenn Zeitfenster aktiv wäre).
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""


def render_child_view(css: str, user: str, display_name: str, data: dict) -> str:
    allow = bool(data.get("allow"))
    status = "✅ Du darfst gerade." if allow else "⛔ Gerade nicht."
    reason = REASON_MAP_DE.get(data.get("reason", ""), data.get("reason", ""))
    pills = [_pill("Status", status, mint=allow), _pill("Grund", reason, mint=True)]

    if data.get("reason") == "override-day":
        pills.append(_pill("Heute", "unbegrenzt", mint=True))
    if data.get("override_text"):
        pills.append(_pill("Sonderfreigabe", str(data["override_text"]), mint=True))
    if data.get("daily_remaining") is not None and data.get("daily_limit") is not None:
        pills.append(_pill("Tagesbudget", f'{data["daily_remaining"]}/{data["daily_limit"]} Min', mint=True))
    if data.get("minutes_left_window") is not None:
        pills.append(_pill("Zeitfenster", f'noch {data["minutes_left_window"]} Min', mint=False))

    return f"""
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>KidsControl – {escape(display_name)}</title>
  <style>{css}</style>
</head>
<body>
  <div class="wrap">
    <div class="container" style="max-width:900px;">
      <div class="topbar">
        <div class="title">
          <h1>🧒 {escape(display_name)}</h1>
          <small>Info-Ansicht • {escape(user)}</small>
        </div>
      </div>

      <div class="grid">
        <div class="card">
          <div class="meta">{''.join(pills)}</div>
          <div class="small" style="margin-top:12px;">
            Wenn etwas nicht passt: Eltern fragen.
          </div>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""
