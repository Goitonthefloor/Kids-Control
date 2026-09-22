#!/usr/bin/env bash
# Installiert den KidsControl-Agenten unter Linux und zeigt den Setup-Schritt.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo/root ausführen."
  exit 1
fi

INSTALL_DIR=/opt/kidscontrol-client
CONF_DIR=/etc/kidscontrol
REPO_CLIENT_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$INSTALL_DIR" "$CONF_DIR"
rm -rf "$INSTALL_DIR/kidscontrol_agent"
cp -a "$REPO_CLIENT_DIR/kidscontrol_agent" "$INSTALL_DIR/"

cat > /etc/systemd/system/kidscontrol-agent.service <<EOF
[Unit]
Description=KidsControl Client Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
EnvironmentFile=-$CONF_DIR/client.env
ExecStart=/usr/bin/python3 -m kidscontrol_agent --env $CONF_DIR/client.env
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo "Agent installiert nach $INSTALL_DIR"
echo "Einrichten (Server-Adresse und Client-Setup-Passwort werden abgefragt):"
echo "  PYTHONPATH=$INSTALL_DIR python3 -m kidscontrol_agent.setup --out $CONF_DIR/client.env"
echo "Danach: systemctl enable --now kidscontrol-agent"
