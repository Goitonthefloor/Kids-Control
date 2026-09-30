# KidsControl – Host-Anforderungen und Containerbetrieb

## Einschätzung für den Eltern-Hub

Der Hub verarbeitet nur Web-Anfragen, Agent-Polls und eine kleine SQLite-Datenbank. Die rechenintensive Durchsetzung (Prozess beenden, Sitzung sperren, lokale Updates) findet auf den Kinder-PCs statt.

| Größe | Mindestwert | Empfehlung für 1 Haushalt |
|---|---:|---:|
| CPU | 1 vCPU | 1–2 vCPU |
| RAM | 256 MB frei | 512 MB |
| Speicher | 1 GB frei | 2 GB, plus Backup-Ziel |
| Netzwerk | TCP 8000 im LAN | Reverse Proxy mit HTTPS bei Zugriff außerhalb des LAN |
| Persistenz | `data/server.env` und SQLite | tägliches Backup von `data/` bzw. dem Container-Volume |

Dies sind Planungswerte, keine gemessenen Mindestanforderungen. Sie gelten für einen kleinen Haushalt bei 30 Sekunden Poll-Intervall; Betriebssystem, Container-Runtime und Backups benötigen zusätzlich Platz und RAM. Image-Größe und tatsächlicher Verbrauch hängen von den installierten Abhängigkeiten ab. Viele Geräte und kurze Poll-Intervalle müssen separat unter Last geprüft werden.

## Docker Compose

Docker ist die bevorzugte Container-Variante. Der Container läuft als unprivilegierter Benutzer, verwirft alle Linux-Capabilities und verwendet ein benanntes Volume für die Daten.

```bash
cp .env.docker.example .env.docker
# KIDSCONTROL_ADMIN_PASSWORD und KIDSCONTROL_SETUP_PASSWORD setzen
docker compose up -d --build
curl http://127.0.0.1:8000/healthz
```

Die Einrichtung wird beim ersten Start automatisch aus den beiden Umgebungsvariablen erzeugt. Danach werden die Argon2id-Hashes aus `/data/server.env` verwendet. Die Passwörter nach der Einrichtung aus `.env.docker` entfernen und mit `docker compose up -d --force-recreate` auch aus der Container-Konfiguration entfernen. Die Datei und Backups vertraulich behandeln. Für einen anderen Host-Port in der aufrufenden Shell `export KIDSCONTROL_BIND=8080` setzen; im Container bleibt der Dienst auf 8000.

Das Volume `kids-control-data` muss gesichert werden. Vor einem Umzug:

```bash
docker compose stop
docker compose run --rm --no-deps --user 0 --entrypoint tar -v "$PWD":/backup kids-control czf /backup/kids-control-data.tgz -C /data .
docker compose start
```

## LXC

LXC ist möglich, wenn der Container eine normale Debian-/Ubuntu-Userspace mit systemd bereitstellt. Einen unprivilegierten Container verwenden; KidsControl benötigt keine privilegierten Rechte, kein Nesting und keine durchgereichten Geräte.

Im Container:

```bash
bash deploy-lxc.sh
cd /opt/kids-control
runuser -u kidscontrol -- .venv/bin/python -m app.setup
systemctl enable --now kids-control
```

Das Skript installiert Python/venv, kopiert die Serverteile nach `/opt/kids-control`, legt den systemd-Dienst an und installiert die Python-Abhängigkeiten. Die Daten liegen unter `/opt/kids-control/data`. Port 8000 muss vom LAN zum LXC weitergeleitet bzw. auf der LXC-IP erreichbar sein.

## Grenzen

Containerisierung betrifft nur den Eltern-Hub. Der Agent auf einem Kinder-PC bleibt ein lokaler Systemdienst und benötigt dort die jeweiligen Rechte für Sitzungs-Sperre und Prozessbeendigung. Ein Docker-/LXC-Container auf dem Eltern-Host kann diese lokalen Kinder-PC-Funktionen nicht ersetzen.
