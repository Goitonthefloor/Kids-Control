# KidsControl – Server Setup

Version: v1.2.0

## Voraussetzungen

Siehe README, Abschnitt Systemvoraussetzungen.

- Python 3.10+
- Port 8000 (oder ein anderer freier TCP-Port) im Heimnetz erreichbar

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

Beide Passwörter mindestens 8 Zeichen und nicht gleich. Die Datei `data/server.env` wird mit Rechten `0600` geschrieben.

Das Client-Setup-Passwort ist **nicht** der Code für den Kinder-PC. Jedes Kind bekommt auf der Kind-Seite einen eigenen Einrichtungscode. Damit (oder mit dem One-Click-Download) richtest du den PC ein. Das Client-Setup-Passwort brauchst du nur als Notweg: `python -m kidscontrol_agent.setup --server … --setup-password … --child kurz-id`.

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
