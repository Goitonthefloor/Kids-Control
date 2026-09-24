"""Browser entry point: choose the child, then watch the PC enroll."""

from __future__ import annotations

import json
from html import escape

from app.i18n import t
from app.ui import css

PROGRESS_CODES = {
    "installer_opened",
    "python_install",
    "python_ok",
    "agent_downloaded",
    "identity_sent",
    "service_started",
    "finished",
    "failed",
}

PLATFORMS = ("linux", "macos", "windows")
INSTALLER_NAMES = {
    "linux": "kidscontrol-setup.sh",
    "macos": "kidscontrol-setup.command",
    "windows": "kidscontrol-setup.cmd",
}


def platform_from_user_agent(user_agent: str, client_hint: str = "") -> str | None:
    """Map a browser user agent to linux, macos, or windows. Phones stay unset."""
    hint = (client_hint or "").strip().strip('"').lower()
    if hint in {"windows", "win"}:
        return "windows"
    if hint in {"macos", "mac", "macosx"}:
        return "macos"
    if hint == "linux":
        return "linux"
    ua = (user_agent or "").lower()
    if any(mark in ua for mark in ("android", "iphone", "ipad", "cros")):
        return None
    if "windows" in ua or "win64" in ua or "win32" in ua:
        return "windows"
    if "mac os x" in ua or "macintosh" in ua:
        return "macos"
    if "linux" in ua or "x11" in ua:
        return "linux"
    return None


def wants_install_page(accept: str, user_agent: str) -> bool:
    """True when the client is a browser that should see the install page."""
    header = (accept or "").lower()
    if "text/html" in header:
        return True
    ua = (user_agent or "").lower()
    if header in {"", "*/*"} and any(mark in ua for mark in ("mozilla", "chrome", "safari", "edg/")):
        return True
    return False


def browser_only_message(url: str) -> str:
    return (
        "Öffne diese Adresse im Browser. Dort wählst du, welchem Kind der PC gehört.\n"
        f"{url}\n"
    )


def progress_line(lang: str, code: str, *, child: str, device: str, detail: str = "") -> str:
    if code == "device_created":
        return t(lang, "progress_device_created", child=child, device=device)
    if code == "failed":
        if detail:
            return t(lang, "progress_failed_detail", detail=detail)
        return t(lang, "progress_failed")
    key = f"progress_{code}"
    text = t(lang, key)
    if text == key:
        return t(lang, "progress_unknown")
    return text


def render_install_form(
    *,
    lang: str,
    token: str,
    children: list[dict],
    platform: str | None,
    error: str = "",
) -> str:
    """Ask which child this PC belongs to. Submitting creates the device row."""
    safe_token = escape(token)
    nav = (
        f'<a href="/install/{safe_token}?lang=de">DE</a>'
        f'<a href="/install/{safe_token}?lang=en">EN</a>'
    )
    if platform in PLATFORMS:
        detected = f'<p>{escape(t(lang, "install_detected", platform=t(lang, f"platform_{platform}")))}</p>'
    else:
        detected = f'<p>{escape(t(lang, "install_unknown"))}</p>'
    error_html = f'<div class="flash err">{escape(error)}</div>' if error else ""
    if not children:
        choices = f'<p>{escape(t(lang, "install_no_children"))}</p>'
        button = ""
    else:
        radios = []
        for child in children:
            checked = " checked" if len(children) == 1 else ""
            radios.append(
                f'<label class="choice"><input type="radio" name="child_slug" value="{escape(child["slug"])}" '
                f'required{checked}/> <span>{escape(child["display_name"])}</span></label>'
            )
        choices = "".join(radios)
        button = f'<p style="margin-top:14px"><button class="btn" type="submit">{escape(t(lang, "install_assign"))}</button></p>'
    name_field = ""
    if children:
        name_field = f"""
      <div style="margin-top:14px">
        <div class="small">{escape(t(lang, "install_device_name"))}</div>
        <input name="device_name" maxlength="80" required placeholder="{escape(t(lang, "install_device_ph"))}"/>
      </div>"""
    body = f"""
<div class="grid" style="max-width:760px">
  <div class="card">
    <h2 style="margin:0 0 8px 0;font-size:18px">{escape(t(lang, "install_pick_title"))}</h2>
    <p class="small">{escape(t(lang, "install_pick_intro"))}</p>
    <div class="notice">{escape(t(lang, "install_notice"))}</div>
    {detected}
    {error_html}
    <form method="post" action="/install/{safe_token}" style="margin-top:12px">
      <div class="small">{escape(t(lang, "install_pick_title"))}</div>
      {choices}
      {name_field}
      {button}
    </form>
    <p class="small" style="margin-top:16px">{escape(t(lang, "install_once"))}</p>
  </div>
</div>"""
    return _install_shell(t(lang, "install_pick_title"), body, nav=nav, lang=lang)


def render_install_progress(
    *,
    lang: str,
    token: str,
    ticket: str,
    child_name: str,
    device_name: str,
    platform: str | None,
    messages: list[str],
    done: bool,
    ok: bool,
) -> str:
    """Show the created entry and each confirmation the PC sends back."""
    safe_token = escape(token)
    safe_ticket = escape(ticket)
    nav = (
        f'<a href="/install/{safe_token}/go/{safe_ticket}?lang=de">DE</a>'
        f'<a href="/install/{safe_token}/go/{safe_ticket}?lang=en">EN</a>'
    )
    items = "".join(f"<li>{escape(line)}</li>" for line in messages)
    done_class = "" if done else " hidden"
    if done and ok:
        banner = t(lang, "install_success", device=device_name, child=child_name)
    elif done:
        banner = t(lang, "install_failure")
    else:
        banner = ""
    if platform in PLATFORMS:
        filename = INSTALLER_NAMES[platform]
        primary = (
            f'<p style="margin-top:14px"><a class="btn" id="kc-install" '
            f'href="/install/{safe_token}/{platform}?ticket={safe_ticket}" download="{escape(filename)}">'
            f'{escape(t(lang, "install_download", platform=t(lang, f"platform_{platform}")))}</a></p>'
            f'<p class="small">{escape(t(lang, f"install_steps_{platform}"))}</p>'
        )
        script_click = '<script>document.getElementById("kc-install").click();</script>'
    else:
        primary = f'<p>{escape(t(lang, "install_unknown"))}</p>'
        script_click = ""
    others = []
    for name in PLATFORMS:
        if name == platform:
            continue
        filename = INSTALLER_NAMES[name]
        others.append(
            f'<a class="link" href="/install/{safe_token}/{name}?ticket={safe_ticket}" download="{escape(filename)}">'
            f'{escape(t(lang, f"platform_{name}"))}</a>'
        )
    status_url = json.dumps(f"/install/{token}/status/{ticket}")
    body = f"""
<div class="grid" style="max-width:760px">
  <div class="card">
    <h2 style="margin:0 0 8px 0;font-size:18px">{escape(t(lang, "install_progress_title"))}</h2>
    <p class="small">{escape(t(lang, "install_progress_sub", device=device_name, child=child_name))}</p>
    <div class="notice">{escape(t(lang, "install_notice"))}</div>
    <div id="kc-done" class="flash{done_class}">{escape(banner)}</div>
    <ol class="steps" id="kc-log">{items}</ol>
    <p class="small" style="margin-top:12px">{escape(t(lang, "install_progress_help"))}</p>
    {primary}
    <p class="small" style="margin-top:16px">{escape(t(lang, "install_other"))}</p>
    <div class="actions" style="justify-content:flex-start">{"".join(others)}</div>
  </div>
</div>
<script>
(function () {{
  var url = {status_url};
  var log = document.getElementById("kc-log");
  var box = document.getElementById("kc-done");
  function render(data) {{
    while (log.firstChild) log.removeChild(log.firstChild);
    (data.messages || []).forEach(function (line) {{
      var item = document.createElement("li");
      item.textContent = line;
      log.appendChild(item);
    }});
    if (data.done) {{
      box.className = "flash";
      box.textContent = data.ok ? data.success : data.failure;
    }}
  }}
  function poll() {{
    fetch(url, {{headers: {{"Accept": "application/json"}}}}).then(function (response) {{
      return response.json();
    }}).then(function (data) {{
      render(data);
      if (!data.done) setTimeout(poll, 2000);
    }}).catch(function () {{
      setTimeout(poll, 4000);
    }});
  }}
  poll();
}})();
</script>
{script_click}"""
    return _install_shell(t(lang, "install_progress_title"), body, nav=nav, lang=lang)


def render_install_message(lang: str, message: str) -> str:
    body = f"""
<div class="grid" style="max-width:760px">
  <div class="card">
    <h2 style="margin:0 0 8px 0;font-size:18px">{escape(t(lang, "install_page_title"))}</h2>
    <p>{escape(message)}</p>
  </div>
</div>"""
    return _install_shell(t(lang, "install_page_title"), body, lang=lang)


def _install_shell(title: str, body: str, *, nav: str = "", lang: str = "de") -> str:
    return f"""<!doctype html>
<html lang="{escape(lang)}">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="referrer" content="no-referrer"/>
  <title>{escape(title)} – KidsControl</title>
  <style>{css()}
label.choice{{display:flex;gap:10px;align-items:center;padding:10px 12px;border:1px solid var(--border);border-radius:12px;margin-top:8px;background:rgba(0,0,0,.18)}}
label.choice input{{width:auto}}
ol.steps{{margin:12px 0 0 0;padding-left:22px}}
ol.steps li{{margin:8px 0}}
.hidden{{display:none}}
</style>
</head>
<body>
  <div class="wrap">
    <div class="container">
      <div class="topbar">
        <div class="title"><h1>KidsControl</h1><small>{escape(title)}</small></div>
        <div class="nav">{nav}</div>
      </div>
      {body}
    </div>
  </div>
</body>
</html>"""
