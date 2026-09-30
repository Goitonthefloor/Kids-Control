#!/usr/bin/env bash
set -euo pipefail

# Run inside a Debian/Ubuntu LXC from the repository directory as root.
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Dieses Skript muss im LXC als root ausgeführt werden." >&2
  exit 1
fi
if [[ ! -f requirements.txt || ! -d app ]]; then
  echo "Bitte aus dem Kids-Control-Repository starten." >&2
  exit 1
fi
if ! command -v apt-get >/dev/null 2>&1; then
  echo "Unterstützt sind Debian/Ubuntu-LXC mit apt-get." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 python3-venv ca-certificates openssh-client

install -d -o root -g root -m 0755 /opt/kids-control
cp -a app client requirements.txt /opt/kids-control/
if ! id kidscontrol >/dev/null 2>&1; then
  useradd --system --home /opt/kids-control --shell /usr/sbin/nologin kidscontrol
fi
chown -R root:root /opt/kids-control/app /opt/kids-control/client /opt/kids-control/requirements.txt
install -d -o kidscontrol -g kidscontrol -m 0700 /opt/kids-control/data
python3 -m venv /opt/kids-control/.venv
/opt/kids-control/.venv/bin/pip install --no-cache-dir -r /opt/kids-control/requirements.txt
chown -R kidscontrol:kidscontrol /opt/kids-control/data
install -m 0644 systemd/kids-control.service /etc/systemd/system/kids-control.service
systemctl daemon-reload
echo "LXC-Installation bereit. Jetzt einmalig ausführen:"
echo "  cd /opt/kids-control"
echo "  runuser -u kidscontrol -- .venv/bin/python -m app.setup"
echo "Danach starten: systemctl enable --now kids-control"
