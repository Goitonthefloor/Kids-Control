# KidsControl – Server Setup

Version: v1.2.0

## Voraussetzungen

Siehe README, Abschnitt Systemvoraussetzungen.

- Python 3.10+
- Port 8000 (oder ein anderer freier TCP-Port) im Heimnetz erreichbar

Für einen Dauerbetrieb sind auch Docker Compose und ein unprivilegierter Debian/Ubuntu-LXC möglich. Die vollständige Einschätzung, Persistenz-Hinweise und die Containerbefehle stehen in `docs/DEPLOYMENT.md`.

## Repo holen

```bash
curl -fsSL -o kidscontrol.tar.gz https://github.com/Goitonthefloor/Kids-Control/archive/refs/heads/main.tar.gz
tar -xzf kidscontrol.tar.gz
cd Kids-Control-main
```

Mit Git: `git clone https://github.com/Goitonthefloor/Kids-Control.git` und `cd Kids-Control`.

## One-Click

Linux und macOS: `./setup-server.sh`. macOS zusätzlich: `setup-server.command` doppelklicken. Windows: `setup-server.cmd` doppelklicken.

Das Skript erzeugt `.venv`, installiert `requirements.txt`, startet uvicorn auf Port 8000 und öffnet den Browser. Die erste Seite ist `/setup`. Nach dem Speichern den Prozess neu starten.

## Einrichtung

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.setup
```

`python -m app.setup` fragt ab:

- Eltern-Benutzername und Eltern-Passwort (Web-Login)
- Client-Setup-Passwort (Haus-Passwort, einmal für den Server)

Beide Passwörter mindestens 8 Zeichen und nicht gleich. Die Datei `data/server.env` wird mit Rechten `0600` geschrieben. Die beiden Passwörter stehen dort als **Argon2id-Hash**, nicht im Klartext. Ein älterer Klartext in dieser Datei wird beim nächsten Start des Hubs gehasht und nicht wieder im Klartext zurückgeschrieben. Ein explizit gesetzter Umgebungsvariablen-Wert, der von der Datei abweicht, bleibt für diesen Prozess gültig.

Das Client-Setup-Passwort ist **nicht** der Code für den Kinder-PC. Die Übersicht zeigt eine Adresse (`/install/…`). Die auf dem Kinder-PC im Browser öffnen, das Kind wählen und den Installer starten. Die Seite legt den Geräteeintrag an und zeigt die Rückmeldungen. Dieselbe Adresse gilt 4 Stunden und kann in der Zeit mehrere PCs einrichten. Danach erzeugt die Eltern-Seite eine neue; die alte wird abgelehnt. Schlägt die Einrichtung fehl, endet die Fortschrittsseite mit einer Fehlermeldung statt weiter zu pollen. Der One-Click-Download bleibt der Notweg, wenn du die Datei am Eltern-Rechner speichern willst. Das Client-Setup-Passwort brauchst du nur, wenn der Kind-Code fehlt: `python -m kidscontrol_agent.setup --server … --setup-password … --child kurz-id`.

Nicht-interaktiv:

```bash
python -m app.setup \
  --admin-user admin \
  --admin-password 'eltern-geheim' \
  --setup-password 'client-geheim'
```

Zum Überschreiben: `--force`.

Alternativ richtet der erste Browser-Aufruf denselben Schritt ein (`/setup`). Danach den Prozess neu starten.

## Start

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

systemd lädt dieselbe Datei, siehe `systemd/kids-control.service`.

## Danach in der UI

1. Mit dem Eltern-Passwort anmelden
2. Kind anlegen
3. Zeitplan, App-Sperren, beobachtete Software setzen
4. Kinder-PCs mit dem Einrichtungscode der Kind-Seite einrichten (`docs/CLIENT.md`)

## Healthcheck

`GET /healthz` → `{"ok": true, "configured": true, ...}`
