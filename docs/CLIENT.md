# KidsControl – Client Agent

Version: v1.5.0

Der Agent läuft auf dem Kinder-PC und holt Regeln vom zentralen Server.

## Per Adresse im Browser

Auf der Kind-Seite steht eine Adresse, zum Beispiel `http://192.168.1.10:8000/install/…`. Sie enthält den Einrichtungscode dieses Kindes. Auf dem Kinder-PC die Adresse im Browser öffnen. Die Seite erkennt Windows, macOS oder Linux, lädt den passenden Installer und erklärt, wie du die Datei startest. Der Browser startet das Programm nicht von selbst.

Linux und macOS im Terminal, ohne Browser:

```bash
curl -fsSL "http://192.168.1.10:8000/install/CODE" | sh
```

Das Skript fragt `uname` ab und führt danach denselben Installer aus. Der Link gilt für ein Gerät. Danach erzeugt die Kind-Seite einen neuen Code.

## One-Click

Wer die Datei am Eltern-Rechner speichern will, lädt sie auf der Kind-Seite herunter und startet sie auf dem Kinder-PC:

- Linux: `bash kidscontrol-setup.sh`
- macOS: `bash kidscontrol-setup.command`
- Windows: `kidscontrol-setup.cmd` doppelklicken

Die Datei enthält Server-Adresse und Token. Sie verlangt Administratorrechte, lädt den Agenten von `/setup/agent.tgz` bzw. `/setup/agent.zip` und richtet einen Systemdienst ein:

- Linux: systemd-Unit `kidscontrol-agent` als **root** (`/opt/kidscontrol-client`, `/etc/kidscontrol/client.env`)
- macOS: LaunchDaemon `com.kidscontrol.agent` als **root**
- Windows: Aufgabenplanung `KidsControlAgent` als **SYSTEM** (`%ProgramData%\KidsControl`)

Während der Installation erscheint dieser Hinweis: „Das Kinderkonto darf kein Administrator sein. Mit sudo oder Windows-Adminrechten kann es den Dienst trotzdem stoppen.“ Konfiguration und Geräte-Schlüssel liegen außerhalb des Kinderprofils. Der Einrichtungscode gilt für ein Gerät; danach erzeugt die Kind-Seite einen neuen Code.

## Einrichtung

Nach dem Anlegen eines Kindes zeigt die Eltern-UI einen Befehl. Auf dem Kinder-PC als Administrator:

```bash
cd client
sudo python3 -m kidscontrol_agent.setup --server http://SERVER:8000 --token CODE
```

Der Code steht nur auf der Kind-Seite und gilt nur für dieses Kind. Das Client-Setup-Passwort vom Server ist dafür nicht nötig. Unter Linux installiert das Setup OpenSSH (`apt-get`, `dnf` oder `pacman`), erzeugt den SSH-Schlüssel unter `/root/.config/kidscontrol/ssh/id_ed25519`, trägt den öffentlichen Schlüssel in `/root/.ssh/authorized_keys` ein und sendet den privaten Schlüssel an den Server. Der Server speichert ihn unter `data/keys/` und schaltet SSH für das Linux-Gerät an. Das Kinderkonto kann diesen Schlüssel nicht entfernen.

Ohne Kind-Code geht derselbe Schritt als Notweg mit dem Client-Setup-Passwort:

```bash
sudo python3 -m kidscontrol_agent.setup --server http://SERVER:8000 --setup-password GEHEIM --child mia
```

## Setup

After you add a child, the parent UI shows one command. On the child PC:

```bash
cd client
sudo python3 -m kidscontrol_agent.setup --server http://SERVER:8000 --token CODE
```

On Linux this installs OpenSSH, creates an SSH key for root, and uploads the private key to the controller.

Linux als Systemdienst (root, nicht das Kinderkonto):

```bash
sudo ./install-linux.sh
sudo PYTHONPATH=/opt/kidscontrol-client python3 -m kidscontrol_agent.setup --out /etc/kidscontrol/client.env
```

`kidscontrol_agent.setup` aktiviert den Dienst. Ohne root bricht es ab.

## Konfiguration

Datei `client.env` (Beispiel: `client/client.env.example`):

```
KIDSCONTROL_SERVER=http://192.168.1.10:8000
KIDSCONTROL_DEVICE_KEY=...aus-der-eltern-ui...
KIDSCONTROL_POLL_SECONDS=30
```

Suchpfade:

- `./client.env`
- `/etc/kidscontrol/client.env` (Linux)
- `~/.config/kidscontrol/client.env` (macOS/Linux)

## Start

```bash
cd client
python -m kidscontrol_agent --env /pfad/zu/client.env
```

Einmaliger Test ohne echte Sperren:

```bash
KIDSCONTROL_DRY_RUN=1 python -m kidscontrol_agent --once --env /pfad/zu/client.env
```

## Was der Agent tut

1. `POST /api/v1/agent/sync` mit Device-Key  
2. Wenn Sitzung verboten → Bildschirm/Sitzung sperren (best effort)  
3. Laufende Prozesse gegen App-Regeln matchen und beenden  
4. Vorwarnung anzeigen, wenn das Zeitfenster endet  

## OS-Hinweise

| OS | Prozessliste | Beenden | Sitzungssperre |
|----|--------------|---------|----------------|
| Linux | `ps` | `kill` | `loginctl` / Screensaver |
| macOS | `ps` | `kill` | CGSession |
| Windows | `tasklist` | `taskkill` | `LockWorkStation` |

Der Agent läuft als Systemprozess (root bzw. SYSTEM). Ein Kinderkonto ohne Administratorrechte kann ihn nicht beenden.

## Softwarestände und Updates

Beim Sync sendet der Agent Versionen der beobachteten Pakete und holt ausstehende Update-Befehle ab (`update_one` / `update_all`). Ergebnisse gehen an `POST /api/v1/agent/commands/{id}/result`.

Linux-Updates laufen als root direkt über apt, dnf oder pacman.

## SSH (nur Linux, optional)

In der Eltern-UI: Host, Port, Benutzer und Pfad zum privaten Schlüssel auf dem Server.  
„SSH-Verbindung prüfen“ führt `echo kidscontrol-ok` aus.  
Ist SSH aktiv, startet „Update“ das Upgrade direkt über SSH, sonst über den Agenten.

## Sicherheit

- Device-Key geheim halten (wie ein Passwort)  
- Server idealerweise nur im Heimnetz oder hinter VPN/TLS  
- Verlorenes Gerät in der Eltern-UI entfernen (Key wird ungültig)
