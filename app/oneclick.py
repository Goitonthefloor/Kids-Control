"""One-click installers for the server host and for child PCs."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

CLIENT_PACKAGE = Path(__file__).resolve().parent.parent / "client" / "kidscontrol_agent"
ADMIN_NOTICE = (
    "Das Kinderkonto darf kein Administrator sein. "
    "Mit sudo oder Windows-Adminrechten kann es den Dienst trotzdem stoppen."
)


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


def _safe_server(server: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(server.strip())
    host = parsed.hostname or ""
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("unsafe server")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("unsafe server")
    if any(char in host for char in "\"'$`\\ \n\r;&|<>"):
        raise ValueError("unsafe server")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}"


def client_installer(platform: str, *, server: str, token: str = "", ticket: str = "") -> tuple[str, str, str]:
    """Return (filename, media_type, body) for a one-click client installer."""
    server = _safe_server(server)
    if ticket:
        ticket = _safe_token(ticket)
        if platform == "linux":
            return "kidscontrol-setup.sh", "text/x-shellscript", _linux_ticket_script(server, ticket, systemd=True)
        if platform == "macos":
            return "kidscontrol-setup.command", "text/x-shellscript", _linux_ticket_script(server, ticket, systemd=False)
        if platform == "windows":
            return "kidscontrol-setup.cmd", "application/octet-stream", _windows_ticket_script(server, ticket)
        raise ValueError("unknown platform")
    token = _safe_token(token)
    if platform == "linux":
        return "kidscontrol-setup.sh", "text/x-shellscript", _linux_script(server, token, systemd=True)
    if platform == "macos":
        return "kidscontrol-setup.command", "text/x-shellscript", _linux_script(server, token, systemd=False)
    if platform == "windows":
        return "kidscontrol-setup.cmd", "application/octet-stream", _windows_script(server, token)
    raise ValueError("unknown platform")


def _linux_script(server: str, token: str, *, systemd: bool) -> str:
    # systemd is kept for callers; the service itself is installed by kidscontrol_agent.setup as root.
    del systemd
    return f"""#!/usr/bin/env bash
# KidsControl one-click client setup. Installs a root system service, not a child-user process.
set -euo pipefail
notice() {{
  echo
  echo "============================================================"
  echo "HINWEIS"
  echo "{ADMIN_NOTICE}"
  echo "============================================================"
  echo
}}
notice
if [[ -t 0 ]]; then
  read -r -p "Enter drücken, um die Installation fortzusetzen... " _
fi
if [[ "$(id -u)" -ne 0 ]]; then
  echo "KidsControl wird als Systemdienst installiert und braucht Administratorrechte."
  exec sudo bash "$0" "$@"
fi
notice
SERVER="{server}"
TOKEN="{token}"
INSTALL_DIR="/opt/kidscontrol-client"
OUT="/etc/kidscontrol/client.env"
mkdir -p "$INSTALL_DIR" /etc/kidscontrol
chmod 755 "$INSTALL_DIR"
chmod 700 /etc/kidscontrol

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 fehlt, Installation läuft …"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update && apt-get install -y python3
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3
  elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm python
  else
    echo "Bitte Python 3.10+ installieren und das Skript erneut starten." >&2
    exit 1
  fi
fi
curl -fsSL "$SERVER/setup/agent.tgz" | tar -xz -C "$INSTALL_DIR"
export PYTHONPATH="$INSTALL_DIR"
python3 -m kidscontrol_agent.setup --server "$SERVER" --token "$TOKEN" --out "$OUT"
echo "KidsControl läuft als Systemdienst (root), nicht unter dem Kinderkonto."
notice
"""


def _windows_script(server: str, token: str) -> str:
    return f"""@echo off
setlocal
chcp 65001 >nul
echo.
echo ============================================================
echo HINWEIS
echo {ADMIN_NOTICE}
echo ============================================================
echo.
pause
net session >nul 2>&1
if errorlevel 1 (
  echo KidsControl wird als SYSTEM-Dienst installiert und braucht Administratorrechte.
  powershell -NoProfile -Command "Start-Process -FilePath cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
  exit /b
)
echo.
echo ============================================================
echo HINWEIS
echo {ADMIN_NOTICE}
echo ============================================================
echo.
set SERVER={server}
set TOKEN={token}
set INSTALL=%ProgramData%\\KidsControl
mkdir "%INSTALL%" 2>nul
where py >nul 2>&1 && set PY=py -3
if not defined PY where python >nul 2>&1 && set PY=python
if not defined PY (
  echo Python 3.10+ fehlt. Bitte fuer alle Benutzer von https://www.python.org/downloads/ installieren.
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
echo KidsControl laeuft als SYSTEM, nicht unter dem Kinderkonto.
echo.
echo ============================================================
echo HINWEIS
echo {ADMIN_NOTICE}
echo ============================================================
echo.
pause
""".replace("\n", "\r\n")


def _linux_ticket_script(server: str, ticket: str, *, systemd: bool) -> str:
    del systemd
    return f"""#!/usr/bin/env bash
# KidsControl setup. The child was chosen in the browser. This file finishes the PC.
set -euo pipefail
SERVER="{server}"
TICKET="{ticket}"
say() {{
  local code="$1"
  local text="Meldung: $code"
  case "$code" in
    installer_opened) text="Der Installer auf diesem PC wurde gestartet." ;;
    python_install) text="Python 3 fehlt und wird installiert." ;;
    python_ok) text="Python 3 ist bereit." ;;
    agent_downloaded) text="Der Agent wurde vom Server geladen." ;;
    failed) text="Die Einrichtung ist fehlgeschlagen." ;;
  esac
  echo
  echo "------------------------------------------------------------"
  echo "$text"
  echo "------------------------------------------------------------"
  curl -fsS -X POST "$SERVER/api/v1/setup/progress" \\
    -H "Content-Type: application/json" \\
    --data "{{\\"ticket\\":\\"$TICKET\\",\\"code\\":\\"$code\\"}}" >/dev/null \\
    || echo "Hinweis: die Meldung konnte nicht an den Server geschickt werden."
}}
notice() {{
  echo
  echo "============================================================"
  echo "HINWEIS"
  echo "{ADMIN_NOTICE}"
  echo "============================================================"
  echo
}}
notice
if [[ "$(id -u)" -ne 0 ]]; then
  echo "KidsControl wird als Systemdienst installiert und braucht Administratorrechte."
  exec sudo bash "$0" "$@"
fi
say installer_opened
SERVER="{server}"
TICKET="{ticket}"
INSTALL_DIR="/opt/kidscontrol-client"
OUT="/etc/kidscontrol/client.env"
mkdir -p "$INSTALL_DIR" /etc/kidscontrol
chmod 755 "$INSTALL_DIR"
chmod 700 /etc/kidscontrol
if ! command -v python3 >/dev/null 2>&1; then
  say python_install
  echo "Python 3 fehlt, Installation läuft …"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update && apt-get install -y python3
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3
  elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm python
  else
    say failed
    echo "Bitte Python 3.10+ installieren und das Skript erneut starten." >&2
    exit 1
  fi
fi
say python_ok
curl -fsSL "$SERVER/setup/agent.tgz" | tar -xz -C "$INSTALL_DIR"
say agent_downloaded
export PYTHONPATH="$INSTALL_DIR"
python3 -m kidscontrol_agent.setup --server "$SERVER" --ticket "$TICKET" --out "$OUT"
echo "KidsControl läuft als Systemdienst (root), nicht unter dem Kinderkonto."
notice
"""


def _windows_ticket_script(server: str, ticket: str) -> str:
    return f"""@echo off
setlocal
chcp 65001 >nul
echo.
echo ============================================================
echo HINWEIS
echo {ADMIN_NOTICE}
echo ============================================================
echo.
net session >nul 2>&1
if errorlevel 1 (
  echo KidsControl wird als SYSTEM-Dienst installiert und braucht Administratorrechte.
  powershell -NoProfile -Command "Start-Process -FilePath cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
  exit /b
)
set SERVER={server}
set TICKET={ticket}
call :report installer_opened
set INSTALL=%ProgramData%\\KidsControl
mkdir "%INSTALL%" 2>nul
where py >nul 2>&1 && set PY=py -3
if not defined PY where python >nul 2>&1 && set PY=python
if not defined PY (
  call :report python_install
  echo Python 3.10+ fehlt. Bitte fuer alle Benutzer von https://www.python.org/downloads/ installieren.
  call :report failed
  pause
  exit /b 1
)
call :report python_ok
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%SERVER%/setup/agent.zip' -OutFile '%INSTALL%\\agent.zip'; Expand-Archive -Force '%INSTALL%\\agent.zip' '%INSTALL%'"
if errorlevel 1 (
  echo Download fehlgeschlagen.
  call :report failed
  pause
  exit /b 1
)
call :report agent_downloaded
set PYTHONPATH=%INSTALL%
%PY% -m kidscontrol_agent.setup --server %SERVER% --ticket %TICKET% --out "%INSTALL%\\client.env"
if errorlevel 1 (
  call :report failed
  pause
  exit /b 1
)
echo KidsControl laeuft als SYSTEM, nicht unter dem Kinderkonto.
echo.
echo ============================================================
echo HINWEIS
echo {ADMIN_NOTICE}
echo ============================================================
echo.
pause
exit /b 0

:report
if "%~1"=="installer_opened" echo Der Installer auf diesem PC wurde gestartet.
if "%~1"=="python_install" echo Python 3 fehlt und wird installiert.
if "%~1"=="python_ok" echo Python 3 ist bereit.
if "%~1"=="agent_downloaded" echo Der Agent wurde vom Server geladen.
if "%~1"=="failed" echo Die Einrichtung ist fehlgeschlagen.
echo ------------------------------------------------------------
> "%TEMP%\\kidscontrol-progress.json" echo {{"ticket":"%TICKET%","code":"%~1"}}
powershell -NoProfile -Command "try {{ Invoke-RestMethod -Method Post -Uri '%SERVER%/api/v1/setup/progress' -ContentType 'application/json' -InFile ($env:TEMP + '\\kidscontrol-progress.json') | Out-Null }} catch {{ Write-Host 'Hinweis: die Meldung konnte nicht an den Server geschickt werden.' }}"
exit /b 0
""".replace("\n", "\r\n")
