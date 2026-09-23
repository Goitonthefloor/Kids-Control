"""Browser and curl entry point that picks the installer for this PC."""

from __future__ import annotations

from html import escape

from app.i18n import t
from app.oneclick import _safe_server, _safe_token
from app.ui import css

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


def curl_bootstrap(server: str, token: str) -> str:
    """POSIX script: detect uname, download the matching installer, and run it."""
    server = _safe_server(server)
    token = _safe_token(token)
    return f"""#!/bin/sh
# KidsControl: detect this PC and run the matching installer.
set -eu
SERVER="{server}"
TOKEN="{token}"
case "$(uname -s 2>/dev/null || echo unknown)" in
  Linux) platform=linux ;;
  Darwin) platform=macos ;;
  *)
    echo "Dieses System wird so nicht installiert. Öffne im Browser: $SERVER/install/$TOKEN" >&2
    exit 1
    ;;
esac
tmp="$(mktemp)"
curl -fsSL "$SERVER/install/$TOKEN/$platform" -o "$tmp"
chmod 700 "$tmp"
exec bash "$tmp"
"""


def render_install_page(
    *,
    lang: str,
    child_name: str,
    token: str,
    platform: str | None,
) -> str:
    """Page opened on the child PC. It downloads the installer for the detected system."""
    safe_token = escape(token)
    steps = ""
    primary = ""
    script = ""
    if platform in PLATFORMS:
        filename = INSTALLER_NAMES[platform]
        label = t(lang, f"platform_{platform}")
        intro = f'<p>{escape(t(lang, "install_detected", platform=label))}</p>'
        steps = (
            f'<p class="small">{escape(t(lang, "install_run_hint"))}</p>'
            f'<p class="small">{escape(t(lang, f"install_steps_{platform}"))}</p>'
        )
        primary = (
            f'<p style="margin-top:14px"><a class="btn" id="kc-install" '
            f'href="/install/{safe_token}/{platform}" download="{escape(filename)}">'
            f'{escape(t(lang, "install_download", platform=label))}</a></p>'
        )
        script = '<script>document.getElementById("kc-install").click();</script>'
    else:
        intro = f'<p>{escape(t(lang, "install_unknown"))}</p>'

    others = []
    for name in PLATFORMS:
        if name == platform:
            continue
        filename = INSTALLER_NAMES[name]
        others.append(
            f'<a class="link" href="/install/{safe_token}/{name}" download="{escape(filename)}">'
            f'{escape(t(lang, f"platform_{name}"))}</a>'
        )
    other_block = (
        f'<p class="small" style="margin-top:16px">{escape(t(lang, "install_other"))}</p>'
        f'<div class="actions" style="justify-content:flex-start">{"".join(others)}</div>'
    )
    nav = (
        f'<a href="/install/{safe_token}?lang=de">DE</a>'
        f'<a href="/install/{safe_token}?lang=en">EN</a>'
    )
    body = f"""
<div class="grid" style="max-width:760px">
  <div class="card">
    <h2 style="margin:0 0 8px 0;font-size:18px">{escape(t(lang, "install_page_title"))}</h2>
    <p class="small">{escape(t(lang, "install_page_sub", name=child_name))}</p>
    <div class="notice">{escape(t(lang, "install_notice"))}</div>
    {intro}
    {steps}
    {primary}
    {other_block}
    <p class="small" style="margin-top:16px">{escape(t(lang, "install_once"))}</p>
  </div>
</div>
{script}"""
    return _install_shell(t(lang, "install_page_title"), body, nav=nav, lang=lang)


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
  <style>{css()}</style>
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
