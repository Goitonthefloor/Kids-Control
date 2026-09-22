"""One-click installers for the server host and for child PCs."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

CLIENT_PACKAGE = Path(__file__).resolve().parent.parent / "client" / "kidscontrol_agent"


def _safe_token(token: str) -> str:
    if not token or any(ch in token for ch in "\"'\n\r$`\\"):
        raise ValueError("unsafe token")
    return token


def agent_archive(kind: str) -> bytes:
    """Bundle the agent package. kind is 'tgz' or 'zip'."""
    buffer = io.BytesIO()
    files = [
        path
        for path in CLIENT_PACKAGE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".pyc")
    ]
    if kind == "zip":
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, f"kidscontrol_agent/{path.relative_to(CLIENT_PACKAGE).as_posix()}")
        return buffer.getvalue()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in files:
            archive.add(path, arcname=f"kidscontrol_agent/{path.relative_to(CLIENT_PACKAGE).as_posix()}")
    return buffer.getvalue()


def client_installer(platform: str, *, server: str, token: str) -> tuple[str, str, str]:
    """Return (filename, media_type, body) for a one-click client installer."""
    token = _safe_token(token)
    server = server.rstrip("/")
    if platform == "linux":
        return "kidscontrol-setup.sh", "text/x-shellscript", _linux_script(server, token, systemd=True)
    if platform == "macos":
        return "kidscontrol-setup.command", "text/x-shellscript", _linux_script(server, token, systemd=False)
    if platform == "windows":
        return "kidscontrol-setup.cmd", "application/octet-stream", _windows_script(server, token)
    raise ValueError("unknown platform")


def _linux_script(server: str, token: str, *, systemd: bool) -> str:
    unit = ""
    if systemd:
        unit = r"""
if [[ "$(id -u)" -eq 0 ]] && command -v systemctl >/dev/null 2>&1; then
  cat > /etc/systemd/system/kidscontrol-agent.service <<UNIT
[Unit]
Description=KidsControl Client Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
EnvironmentFile=-$OUT
ExecStart=/usr/bin/python3 -m kidscontrol_agent --env $OUT
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now kidscontrol-agent
  echo "Dienst kidscontrol-agent ist aktiv."
fi
"""
    return f"""#!/usr/bin/env bash
# KidsControl one-click client setup
set -euo pipefail
SERVER="{server}"
TOKEN="{token}"
if [[ "$(id -u)" -eq 0 ]]; then
  INSTALL_DIR="/opt/kidscontrol-client"
  OUT="/etc/kidscontrol/client.env"
  mkdir -p /etc/kidscontrol
else
  INSTALL_DIR="${{HOME}}/.local/share/kidscontrol"
  OUT="${{HOME}}/.config/kidscontrol/client.env"
fi
mkdir -p "$INSTALL_DIR" "$(dirname "$OUT")"

install_python() {{
  if command -v python3 >/dev/null 2>&1; then
    return
  fi
  echo "Python 3 fehlt, Installation läuft …"
  if command -v apt-get >/dev/null 2>&1; then
    run apt-get update && run apt-get install -y python3
  elif command -v dnf >/dev/null 2>&1; then
    run dnf install -y python3
  elif command -v pacman >/dev/null 2>&1; then
    run pacman -Sy --noconfirm python
  else
    echo "Bitte Python 3.10+ installieren und das Skript erneut starten." >&2
    exit 1
  fi
}}
run() {{
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}}
install_python
curl -fsSL "$SERVER/setup/agent.tgz" | tar -xz -C "$INSTALL_DIR"
export PYTHONPATH="$INSTALL_DIR"
python3 -m kidscontrol_agent.setup --server "$SERVER" --token "$TOKEN" --out "$OUT"
{unit}
echo "KidsControl Client ist eingerichtet: $OUT"
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Start: PYTHONPATH=$INSTALL_DIR python3 -m kidscontrol_agent --env $OUT"
fi
"""


def _windows_script(server: str, token: str) -> str:
    return f"""@echo off
setlocal
set SERVER={server}
set TOKEN={token}
set INSTALL=%LOCALAPPDATA%\\KidsControl
mkdir "%INSTALL%" 2>nul
where py >nul 2>&1 && set PY=py -3
if not defined PY where python >nul 2>&1 && set PY=python
if not defined PY (
  echo Python 3.10+ fehlt. Bitte von https://www.python.org/downloads/ installieren und erneut doppelklicken.
  pause
  exit /b 1
)
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%SERVER%/setup/agent.zip' -OutFile '%INSTALL%\\agent.zip'; Expand-Archive -Force '%INSTALL%\\agent.zip' '%INSTALL%'"
if errorlevel 1 (
  echo Download fehlgeschlagen.
  pause
  exit /b 1
)
set PYTHONPATH=%INSTALL%
%PY% -m kidscontrol_agent.setup --server %SERVER% --token %TOKEN% --out "%INSTALL%\\client.env"
echo KidsControl Client ist eingerichtet.
pause
""".replace("\n", "\r\n")
