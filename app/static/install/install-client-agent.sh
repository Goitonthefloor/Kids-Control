#!/usr/bin/env bash
set -euo pipefail

# ============================
# KidsControl Client Agent
# Version: v0.5
# ============================

AGENT_USER="root"
INSTALL_DIR="/opt/kidscontrol-client"
CONF_DIR="/etc/kidscontrol"
SERVICE_NAME="kidscontrol-client"
PYTHON_BIN="/usr/bin/python3"

echo "🧒 KidsControl – Client Agent Installer (v0.5)"
echo "============================================="

# --- Checks ---
if [[ $EUID -ne 0 ]]; then
  echo "❌ Bitte als root ausführen (sudo)"
  exit 1
fi

if [[ ! -f "$CONF_DIR/client.env" ]]; then
  echo "❌ $CONF_DIR/client.env nicht gefunden."
  echo "👉 Zuerst join-<distro>.sh ausführen!"
  exit 1
fi

source "$CONF_DIR/client.env"

if [[ -z "${KIDSCONTROL_USER:-}" || -z "${KIDSCONTROL_SERVER:-}" ]]; then
  echo "❌ client.env unvollständig (USER oder SERVER fehlt)"
  exit 1
fi

echo "✔ Benutzer: $KIDSCONTROL_USER"
echo "✔ Server:   $KIDSCONTROL_SERVER"

# --- Dependencies ---
echo "📦 Prüfe Abhängigkeiten …"

if ! command -v python3 >/dev/null; then
  echo "❌ python3 fehlt"
  exit 1
fi

$PYTHON_BIN - <<'PY'
import sys
assert sys.version_info >= (3,10), "Python >= 3.10 erforderlich"
PY

# --- Install directories ---
echo "📁 Lege Verzeichnisse an …"
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONF_DIR"

# --- Agent script ---
echo "🧠 Installiere Agent …"

cat > "$INSTALL_DIR/agent.py" <<'PY'
#!/usr/bin/env python3
import os
import time
import requests
import subprocess
from datetime import datetime

CONF = "/etc/kidscontrol/client.env"
INTERVAL = 30  # Sekunden

def load_env():
    env = {}
    with open(CONF) as f:
        for line in f:
            if "=" in line:
                k,v = line.strip().split("=",1)
                env[k] = v
    return env

def enforce(allow: bool):
    # v0.5: nur Stub (Logging + Platzhalter)
    # v0.6: nftables / user-session lock
    if allow:
        print("✅ Zugriff erlaubt")
    else:
        print("⛔ Zugriff gesperrt")

def main():
    env = load_env()
    user = env["KIDSCONTROL_USER"]
    server = env["KIDSCONTROL_SERVER"].rstrip("/")

    print(f"[{datetime.now()}] KidsControl Agent gestartet für {user}")

    while True:
        try:
            r = requests.get(
                f"{server}/api/check-access",
                params={"user": user},
                timeout=5,
            )
            data = r.json()
            enforce(bool(data.get("allow")))
        except Exception as e:
            print(f"[WARN] Server nicht erreichbar: {e}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
PY

chmod +x "$INSTALL_DIR/agent.py"

# --- systemd service ---
echo "🧷 Installiere systemd Service …"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=KidsControl Client Agent
After=network-online.target

[Service]
Type=simple
ExecStart=$PYTHON_BIN $INSTALL_DIR/agent.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# --- Activate ---
systemctl daemon-reexec
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"

echo
echo "🎉 Installation abgeschlossen!"
echo "👉 Service-Status:"
systemctl --no-pager status "${SERVICE_NAME}.service"
