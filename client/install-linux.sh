#!/usr/bin/env bash
# Minimal Linux installer for the KidsControl agent
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo/root ausführen."
  exit 1
fi

INSTALL_DIR=/opt/kidscontrol-client
CONF_DIR=/etc/kidscontrol
REPO_CLIENT_DIR="$(cd "$(dirname "$0")/../.." && pwd)/client"

mkdir -p "$INSTALL_DIR" "$CONF_DIR"
cp -a "$REPO_CLIENT_DIR/kidscontrol_agent" "$INSTALL_DIR/"
if [[ ! -f "$CONF_DIR/client.env" ]]; then
  cp "$REPO_CLIENT_DIR/client.env.example" "$CONF_DIR/client.env"
  echo "Bitte $CONF_DIR/client.env editieren (SERVER + DEVICE_KEY)."
fi

cat > /etc/systemd/system/kidscontrol-agent.service <<EOF
[Unit]
Description=KidsControl Client Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=-$CONF_DIR/client.env
ExecStart=/usr/bin/python3 -m kidscontrol_agent --env $CONF_DIR/client.env
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Make package importable
echo "$INSTALL_DIR" > /etc/kidscontrol/agent.pth 2>/dev/null || true
export PYTHONPATH="$INSTALL_DIR:${PYTHONPATH:-}"

systemctl daemon-reload
echo "Konfiguration prüfen, dann: systemctl enable --now kidscontrol-agent"
echo "PYTHONPATH für manuelle Tests: export PYTHONPATH=$INSTALL_DIR"
