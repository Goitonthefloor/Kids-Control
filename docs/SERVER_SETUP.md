# KidsControl – Server Setup

Version: v1.0

## Voraussetzungen

- Python 3.10+
- Netzwerk-Erreichbarkeit für Agenten (Port 8000 oder Reverse-Proxy)

## Installation

```bash
git clone <repo> kids-control
cd kids-control
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Passwort und Secret setzen
```

## Start

```bash
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Oder systemd: siehe `systemd/kids-control.service`  
`WorkingDirectory` und Pfade an die Installation anpassen. Datenverzeichnis muss schreibbar sein (`ReadWritePaths`).

## Erste Schritte in der UI

1. Einloggen  
2. Kind anlegen  
3. Zeitplan prüfen/anpassen  
4. App-Sperren setzen  
5. Gerät anlegen und **Device-Key** notieren  
6. Agent auf dem Kinder-PC mit diesem Key starten  

## Healthcheck

`GET /healthz` → `{"ok": true, ...}`
