# KidsControl

**Zentraler Anlaufpunkt** für Eltern: Nutzungszeit der Kinder-PCs steuern und App-Aufrufe unterbinden – **unabhängig vom Betriebssystem** (Windows, macOS, Linux).

Dieses Projekt wurde mit Unterstützung von KI erstellt.

---

## Was KidsControl macht

1. **Eltern-Hub (Server)** – Web-UI + API als einzige Quelle der Wahrheit  
2. **Agent auf jedem Kinder-PC** – holt Regeln vom Server und setzt sie lokal durch  
3. **Nutzungszeit** – Wochentags-Fenster, Tagesminuten, +1h / „Heute unbegrenzt“  
4. **App-Sperren** – Prozesse nach Namen/Muster beenden (z.B. `minecraft`, `steam`, `RobloxPlayerBeta.exe`)

Keine Inhaltsanalyse, kein Keylogging, keine Bildschirmüberwachung.

---

## Architektur

```
Eltern-Browser ──► KidsControl Server (FastAPI + SQLite)
                         ▲
                         │ HTTPS/HTTP Poll (Device-Key)
           ┌─────────────┼─────────────┐
           │             │             │
      Agent Win     Agent macOS    Agent Linux
```

Der Server entscheidet. Der Agent führt aus (Sitzung sperren, Apps beenden, Nutzung melden).

---

## Schnellstart (Server)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export KIDSCONTROL_ADMIN_USER=admin
export KIDSCONTROL_ADMIN_PASSWORD=geheim
export KIDSCONTROL_SECRET=$(python -c 'import secrets;print(secrets.token_urlsafe(32))')

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Öffne http://127.0.0.1:8000 → Login → Kind anlegen → Gerät anlegen → Device-Key kopieren.

---

## Agent auf dem Kinder-PC

```bash
# client.env (siehe client/client.env.example)
KIDSCONTROL_SERVER=http://IP-DES-SERVERS:8000
KIDSCONTROL_DEVICE_KEY=...aus-der-eltern-ui...

cd client
python -m kidscontrol_agent --env /pfad/zu/client.env
# Testlauf ohne Sperren:
KIDSCONTROL_DRY_RUN=1 python -m kidscontrol_agent --once --env /pfad/zu/client.env
```

Der Agent läuft unter Windows, macOS und Linux mit denselben Regeln.

---

## Dokumentation

- `docs/ARCHITECTURE.md` – Zielbild und Komponenten  
- `docs/DATABASE.md` – Datenmodell  
- `docs/SERVER_SETUP.md` – Installation  
- `docs/CLIENT.md` – Agent-Setup je OS  

---

## Lizenzierung

Dual Licensing:

- Open Source: **GPL-3.0-or-later**
- Kommerzielle Lizenzen auf Anfrage: **rolf_greger@web.de**

---

## Status

**v1.0 – Cross-Platform Hub**

Server-UI, Policy-Engine, App-Sperren, Geräte-API und Cross-Platform-Agent sind enthalten.
