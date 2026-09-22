# KidsControl – Server Setup

Version: v1.1

## Voraussetzungen

Siehe README, Abschnitt Systemvoraussetzungen.

- Python 3.10+
- Port 8000 (oder ein anderer freier TCP-Port) im Heimnetz erreichbar

## Einrichtung

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.setup
```

`python -m app.setup` fragt ab:

- Eltern-Benutzername und Eltern-Passwort (Web-Login)
- Client-Setup-Passwort (nur für `kidscontrol_agent.setup` auf den Kinder-PCs)

Beide Passwörter mindestens 8 Zeichen und nicht gleich. Die Datei `data/server.env` wird mit Rechten `0600` geschrieben.

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
4. Kinder-PCs mit dem Client-Setup-Passwort einrichten (`docs/CLIENT.md`)

## Healthcheck

`GET /healthz` → `{"ok": true, "configured": true, ...}`
