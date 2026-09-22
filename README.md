# KidsControl

Deutsch unten. English follows.

---

# Deutsch

**Zentraler Anlaufpunkt** für Eltern: Nutzungszeit der Kinder-PCs steuern und App-Aufrufe unterbinden – **unabhängig vom Betriebssystem** (Windows, macOS, Linux).

Die Web-Oberfläche gibt es auf Deutsch und Englisch (Schalter **DE / EN**).

## Was KidsControl macht

1. **Eltern-Hub (Server)** – Web-UI und API, einzige Quelle der Wahrheit
2. **Agent auf jedem Kinder-PC** – holt Regeln ab und setzt sie lokal durch
3. **Nutzungszeit** – Zeitfenster, Tagesminuten, +1h, „Heute unbegrenzt“
4. **App-Sperren** – Prozesse nach Muster beenden; jede Sperre ist danach änderbar
5. **Softwarestände und Updates** – Versionen melden, Updates über den Agenten oder per SSH

Keine Inhaltsanalyse, kein Keylogging, keine Bildschirmüberwachung.

## Systemvoraussetzungen

### Server (Eltern-Hub)

| | |
|---|---|
| Betriebssystem | Linux für den Dauerbetrieb (systemd). Windows 10/11 und macOS 12+ können den Hub ebenfalls starten. |
| Python | 3.10 oder neuer, mit `pip` und `venv` |
| Arbeitsspeicher | 256 MB frei reichen für einen Haushalt |
| Speicherplatz | etwa 500 MB inklusive virtueller Umgebung und SQLite-Datenbank |
| Netzwerk | ein freier TCP-Port (Standard **8000**), von den Kinder-PCs im LAN erreichbar |
| Browser | aktuelle Version von Firefox, Chrome, Edge oder Safari |

Nicht nötig: Active Directory, Docker, dieselbe Distribution auf allen Rechnern.

### Clients (Kinder-PCs)

| | Windows | macOS | Linux |
|---|---|---|---|
| Version | Windows 10 oder 11 | macOS 12 oder neuer | aktuelle Distribution mit systemd |
| Python | 3.10+ | 3.10+ | 3.10+ |
| Sitzung sperren | `LockWorkStation` | Bildschirmsperre über das System | `loginctl` oder Bildschirmschoner |
| Apps beenden | `taskkill` | `kill` | `kill` |
| OpenSSH | optional, Client vorhanden | eingebaut | wird beim Setup per apt, dnf oder pacman installiert (`openssh-server`) |
| Updates | optional `winget` | optional Homebrew | `apt`, `dnf` oder `pacman`; Updates brauchen passwortloses `sudo` |

## Einrichtung

### 1. Server

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.setup
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ohne CLI-Setup zeigt der erste Browser-Aufruf dieselbe Einrichtung. Die Datei `data/server.env` nicht ins Git legen.

Es gibt zwei Server-Passwörter:

- **Eltern-Passwort** – Login in der Web-Oberfläche
- **Client-Setup-Passwort** – nur für die Ersteinrichtung des Servers, nicht für jeden Kinder-PC

### 2. Kind und Client in einem Schritt

1. Anmelden und nur den Namen des Kindes eintragen.
2. Die Kind-Seite zeigt **einen Befehl**. Den auf dem Kinder-PC im Ordner `client` ausführen:

```bash
python -m kidscontrol_agent.setup --server http://IP-DES-SERVERS:8000 --token CODE
```

Der Client erkennt das Betriebssystem. Unter Linux installiert er OpenSSH mit dem Paketmanager, erzeugt einen SSH-Schlüssel, legt den öffentlichen Teil in `authorized_keys` und überträgt den privaten Schlüssel an den Server. Danach steht das Gerät in der Eltern-UI, SSH ist für Linux aktiv.

Linux-Dienst: `sudo ./install-linux.sh`, danach denselben Befehl mit `--out /etc/kidscontrol/client.env`.

## Dokumentation

- `docs/ARCHITECTURE.md`
- `docs/DATABASE.md`
- `docs/SERVER_SETUP.md`
- `docs/CLIENT.md`

## Lizenzierung

- Open Source: **GPL-3.0-or-later**
- Kommerzielle Lizenzen: **rolf_greger@web.de**

---

# English

**Central place** for parents to control screen time and block apps on children's PCs, **independent of the operating system** (Windows, macOS, Linux).

The web UI is available in German and English (switch **DE / EN**).

## What KidsControl does

1. **Parent hub (server)** – web UI and API, the only source of truth
2. **Agent on each child PC** – pulls the rules and enforces them locally
3. **Screen time** – weekly windows, daily minutes, +1h, “unlimited today”
4. **App blocks** – stop processes by pattern; each block can be edited later
5. **Software versions and updates** – report versions, update via the agent or over SSH

No content inspection, no keylogging, no screen surveillance.

## System requirements

### Server (parent hub)

| | |
|---|---|
| Operating system | Linux for an always-on hub (systemd). Windows 10/11 and macOS 12+ can run the hub as well. |
| Python | 3.10 or newer, with `pip` and `venv` |
| Memory | 256 MB free is enough for a household |
| Disk | about 500 MB including the virtualenv and the SQLite database |
| Network | one free TCP port (default **8000**) reachable from the child PCs on the LAN |
| Browser | a current Firefox, Chrome, Edge, or Safari |

Not required: Active Directory, Docker, or the same distribution on every machine.

### Clients (child PCs)

| | Windows | macOS | Linux |
|---|---|---|---|
| Version | Windows 10 or 11 | macOS 12 or newer | a current distribution with systemd |
| Python | 3.10+ | 3.10+ | 3.10+ |
| Lock session | `LockWorkStation` | system screen lock | `loginctl` or a screensaver |
| Stop apps | `taskkill` | `kill` | `kill` |
| OpenSSH | optional; the client is usually present | built in | installed during setup by apt, dnf, or pacman (`openssh-server`) |
| Updates | optional `winget` | optional Homebrew | `apt`, `dnf`, or `pacman`; updates need passwordless `sudo` |

## Setup

### 1. Server

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.setup
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Without the CLI, the first browser visit shows the same setup. Do not commit `data/server.env`.

Two server passwords:

- **Parent password** – signs in to the web UI
- **Client setup password** – only for the first server setup, not for every child PC

### 2. Child and client in one step

1. Sign in and enter only the child's name.
2. The child page shows **one command**. Run it on the child PC inside the `client` folder:

```bash
python -m kidscontrol_agent.setup --server http://SERVER-IP:8000 --token CODE
```

The client detects the OS. On Linux it installs OpenSSH with the package manager, creates an SSH key, puts the public key in `authorized_keys`, and sends the private key to the server. The device then shows up in the parent UI, with SSH enabled for Linux.

Linux service: `sudo ./install-linux.sh`, then the same command with `--out /etc/kidscontrol/client.env`.

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/DATABASE.md`
- `docs/SERVER_SETUP.md`
- `docs/CLIENT.md`

## Licensing

- Open source: **GPL-3.0-or-later**
- Commercial licenses: **rolf_greger@web.de**
