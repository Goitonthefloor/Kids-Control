# KidsControl

**Zentraler Anlaufpunkt** für Eltern: Nutzungszeit der Kinder-PCs steuern und App-Aufrufe unterbinden – **unabhängig vom Betriebssystem** (Windows, macOS, Linux).

Dieses Projekt wurde mit Unterstützung von KI erstellt.

---

## Was KidsControl macht

1. **Eltern-Hub (Server)** – Web-UI + API als einzige Quelle der Wahrheit
2. **Agent auf jedem Kinder-PC** – holt Regeln vom Server und setzt sie lokal durch
3. **Nutzungszeit** – Wochentags-Fenster, Tagesminuten, +1h / „Heute unbegrenzt“
4. **App-Sperren** – Prozesse nach Namen/Muster beenden (z.B. `minecraft`, `steam`)
5. **Softwarestände und Updates** – beobachtete Paketversionen, Update per Agent oder SSH (Linux)

Keine Inhaltsanalyse, kein Keylogging, keine Bildschirmüberwachung.

---

## Systemvoraussetzungen

### Server (Eltern-Hub)

| | |
|---|---|
| Betriebssystem | Linux für den Dauerbetrieb (systemd). Windows 10/11 und macOS 12+ können den Hub ebenfalls starten. |
| Python | 3.10 oder neuer, mit `pip` und `venv` |
| Arbeitsspeicher | 256 MB frei reichen für einen Haushalt |
| Speicherplatz | etwa 500 MB inklusive virtueller Umgebung und SQLite-Datenbank |
| Netzwerk | ein freier TCP-Port (Standard **8000**), von den Kinder-PCs im LAN erreichbar |
| Browser | aktuelle Version von Firefox, Chrome, Edge oder Safari für die Eltern-UI |

Nicht nötig: Active Directory, Docker, dieselbe Distribution auf allen Rechnern.

### Clients (Kinder-PCs)

| | Windows | macOS | Linux |
|---|---|---|---|
| Version | Windows 10 oder 11 | macOS 12 oder neuer | aktuelle Distribution mit systemd |
| Python | 3.10+ | 3.10+ | 3.10+ |
| Sitzung sperren | `LockWorkStation` | Bildschirmsperre über das System | `loginctl` oder Bildschirmschoner |
| Apps beenden | `taskkill` | `kill` | `kill` |
| Softwarestände / Updates | optional `winget` | optional Homebrew | `apt`, `dnf` oder `pacman`; Updates brauchen passwortloses `sudo` |
| Autostart | Aufgabenplanung oder Dienst | launchd | systemd (siehe `client/install-linux.sh`) |

Jeder Client braucht Netzwerkzugriff zum Server. Für Linux-Updates über SSH zusätzlich OpenSSH auf dem Kinder-PC und einen privaten Schlüssel auf dem Server.

---

## Einrichtung

Es gibt zwei Passwörter:

- **Eltern-Passwort** – Login in der Web-Oberfläche
- **Client-Setup-Passwort** – nur für die Einrichtung eines Kinder-PCs. Damit legt der Client ein Gerät an einem bereits vorhandenen Kind an und erhält einen Device-Key.

### 1. Server

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.setup                # fragt beide Passwörter ab
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ohne vorheriges CLI-Setup zeigt der erste Aufruf im Browser dieselbe Einrichtung.

Danach: anmelden, Kind anlegen, Zeitplan und App-Sperren setzen.

Die Konfiguration liegt in `data/server.env` (nicht ins Git legen).

### 2. Client

Auf dem Kinder-PC, im Ordner `client` (Linux-Dienst: `sudo ./install-linux.sh`):

```bash
python -m kidscontrol_agent.setup
```

Abgefragt werden Server-Adresse, **Client-Setup-Passwort**, Kind und Gerätename. Das schreibt `client.env`. Start:

```bash
python -m kidscontrol_agent --env /pfad/zu/client.env
```

Nicht-interaktiv:

```bash
python -m kidscontrol_agent.setup \
  --server http://192.168.1.10:8000 \
  --setup-password '...' \
  --child mia \
  --device-name "Laptop" \
  --out client.env
```

---

## Architektur

```
Eltern-Browser ──► KidsControl Server (FastAPI + SQLite)
                         ▲
                         │ Poll mit Device-Key
           ┌─────────────┼─────────────┐
           │             │             │
      Agent Win     Agent macOS    Agent Linux
```

Der Server entscheidet. Der Agent führt aus.

---

## Dokumentation

- `docs/ARCHITECTURE.md` – Zielbild
- `docs/DATABASE.md` – Datenmodell
- `docs/SERVER_SETUP.md` – Server-Installation
- `docs/CLIENT.md` – Agent je Betriebssystem

---

## Lizenzierung

Dual Licensing:

- Open Source: **GPL-3.0-or-later**
- Kommerzielle Lizenzen auf Anfrage: **rolf_greger@web.de**

---

## Status

**v1.1 – Setup für Server und Clients**

Eltern-Hub, Zeitregeln, App-Sperren, Softwarestände, optionales SSH und ein Setup mit getrenntem Client-Passwort.
