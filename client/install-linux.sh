#!/usr/bin/env bash
# Installiert den KidsControl-Agenten unter Linux und zeigt den Setup-Schritt.
set -euo pipefail

echo
echo "============================================================"
echo "HINWEIS"
echo "Das Kinderkonto darf kein Administrator sein. Mit sudo oder Windows-Adminrechten kann es den Dienst trotzdem stoppen."
echo "============================================================"
echo
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

chmod 755 "$INSTALL_DIR"
chmod 700 "$CONF_DIR"
echo "Agent installiert nach $INSTALL_DIR"
echo "Einrichten startet den Systemdienst als root, nicht als Kinderkonto:"
echo "  PYTHONPATH=$INSTALL_DIR python3 -m kidscontrol_agent.setup --out $CONF_DIR/client.env"
echo "Das Kinderkonto darf kein Administrator sein."
