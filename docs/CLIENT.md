# KidsControl – Client Agent

Version: v1.6.0

Der Agent läuft auf dem Kinder-PC und holt Regeln vom zentralen Server.

## Per Adresse im Browser

Auf der Übersicht und auf der Kind-Seite steht eine Adresse, zum Beispiel `http://192.168.1.10:8000/install/…`. Auf dem Kinder-PC die Adresse im Browser öffnen.

1. Die Maske fragt, welchem Kind der PC gehört, und nach einem Namen.
2. Der Eintrag wird angelegt. Die Seite bestätigt das sofort.
3. Der Installer für das erkannte System wird heruntergeladen. Die Datei starten und die Administratorabfrage bestätigen.
4. Der PC schickt Name, System und Schlüssel an den Server. Jede Rückmeldung erscheint in der Liste auf der Seite: Installer gestartet, Python bereit, Agent geladen, Daten übertragen, Dienst gestartet, fertig.

Dieselbe Adresse gilt **4 Stunden** und kann in der Zeit weitere PCs einrichten. Pro PC einmal das Kind wählen. Danach zeigt die Eltern-Seite eine neue Adresse; alte Links funktionieren nicht mehr. Ein fehlender Ablaufzeitpunkt (älterer Stand) gilt als abgelaufen. Der Einrichtungscode je Kind (Befehl und One-Click-Datei) bleibt einmalig und gilt nur für dieses Kind.

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
sudo KIDSCONTROL_ACCOUNT=kinder python3 -m kidscontrol_agent.setup --server http://SERVER:8000 --token CODE --account kinder
```

Der Code steht nur auf der Kind-Seite und gilt nur für dieses Kind. Das Client-Setup-Passwort vom Server ist dafür nicht nötig. Unter Linux installiert das Setup OpenSSH (`apt-get`, `dnf` oder `pacman`), erzeugt den SSH-Schlüssel unter `/root/.config/kidscontrol/ssh/id_ed25519`, trägt den öffentlichen Schlüssel in `/root/.ssh/authorized_keys` ein und sendet den privaten Schlüssel an den Server. Der Server speichert ihn unter `data/keys/` und schaltet SSH für das Linux-Gerät an. Das Kinderkonto kann diesen Schlüssel nicht entfernen.

Ohne Kind-Code geht derselbe Schritt als Notweg mit dem Client-Setup-Passwort:

```bash
sudo KIDSCONTROL_ACCOUNT=kinder python3 -m kidscontrol_agent.setup --server http://SERVER:8000 --setup-password GEHEIM --child mia --account kinder
```

## Setup

After you add a child, the parent UI shows one command. On the child PC:

```bash
cd client
sudo KIDSCONTROL_ACCOUNT=kinder python3 -m kidscontrol_agent.setup --server http://SERVER:8000 --token CODE --account kinder
```

On Linux this installs OpenSSH, creates an SSH key for root, and uploads the private key to the controller.

Linux als Systemdienst (root, nicht das Kinderkonto):

```bash
sudo ./install-linux.sh
sudo PYTHONPATH=/opt/kidscontrol-client KIDSCONTROL_ACCOUNT=kinder python3 -m kidscontrol_agent.setup --account kinder --out /etc/kidscontrol/client.env
```

`kidscontrol_agent.setup` aktiviert den Dienst. Ohne root bricht es ab.

Der Agent verlangt beim Setup den lokalen Anmeldenamen des Kinderkontos (`--account`).
Dieses Konto wird bei abgelehnter Policy sofort für neue Anmeldungen gesperrt und
nach der Warnfrist abgemeldet; Eltern- und Administratorkonten bleiben unangetastet.
Bei Freigabe wird nur der vorherige Zustand dieses Kinderkontos wiederhergestellt.
Falls der Agent nicht mehr startet, kann ein Administrator mit
`python3 -m kidscontrol_agent --env /etc/kidscontrol/client.env --restore-account`
die protokollierte Kontosperre zurücknehmen.

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
2. Wenn Sitzung verboten → Bildschirm/Sitzung sperren und das etwa alle 5 Sekunden wiederholen  
3. Laufende Prozesse gegen App-Regeln matchen und beenden  
4. Programme mit Tageskontingent melden, solange das Kontingent reicht, und danach beenden  
5. Warnen, solange so ein Programm läuft und noch 5, 2 oder 1 Minute übrig sind. Jede Stufe einmal.  
6. Vorwarnung anzeigen, wenn das Zeitfenster endet  
7. Ist der Hub nicht erreichbar, die Sitzung sperren (fail-closed) und die zuletzt bekannten App-Sperren weiter durchsetzen. Kontingent-Programme werden offline ebenfalls beendet, weil die Restzeit ohne Hub nicht mehr stimmt. Die nächste erfolgreiche Abfrage hebt die Sperre nur auf, wenn der Hub die Sitzung erlaubt.

Die Art der Warnung stellt das Menü auf dem Kinder-PC ein:

```bash
python3 -m kidscontrol_agent --settings
```

**Meldungsfenster** bleibt offen, bis es bestätigt wird. **Toast** ist ein kurzer Hinweis und verschwindet von selbst. Ohne Auswahl bleibt es beim bisherigen Verhalten: Windows zeigt ein Fenster, Linux und macOS einen Toast. Die Auswahl liegt neben `client.env` und gilt ab der nächsten Warnung. Das Menü braucht dieselben Rechte wie der Agent, sonst kann es die Datei nicht schreiben.

Läuft der Agent als root oder SYSTEM, gehen Meldungen in die grafische Sitzung: Linux über `runuser` (sonst `sudo -n`) und den Session-Bus des angemeldeten Benutzers, macOS über `launchctl asuser`, Windows über einen Prozess in der aktiven Konsole. Ohne lokale grafische Sitzung bleibt die Meldung unsichtbar.

## OS-Hinweise

| OS | Prozessliste | Beenden | Sitzungssperre |
|----|--------------|---------|----------------|
| Linux | `ps` | `kill` | `loginctl lock-sessions` (root), sonst `loginctl lock-session` / Screensaver |
| macOS | `ps` | `kill` | `SACLockScreenImmediate`, sonst `LockScreen.app`, sonst altes `CGSession -suspend`, sonst die Sperr-Tastenkombination in der Konsolensitzung |
| Windows | `tasklist` | `taskkill` | `LockWorkStation`, aus einer SYSTEM-Sitzung in der aktiven Konsole |

Solange die Sitzung verboten ist, wiederholt der Agent die Sperre etwa alle 5 Sekunden. Wer das Passwort des Kinderkontos kennt, kann entsperren, aber nur bis zum nächsten Versuch. Das ist keine Kiosk-Sperre. macOS kann eine zukünftige Version der privaten Lock-API ignorieren; dann bleibt der Fallback best effort.

Der Agent läuft als Systemprozess (root bzw. SYSTEM). Ein Kinderkonto ohne Administratorrechte kann ihn nicht beenden.

## Softwarestände und Updates

Beim Sync sendet der Agent Versionen der beobachteten Pakete und holt ausstehende Update-Befehle ab (`update_one` / `update_all`). Ergebnisse gehen an `POST /api/v1/agent/commands/{id}/result`.

Zusätzlich meldet der Agent Pakete, für die der Paketmanager eine neuere Version kennt: unter Windows `winget upgrade`, unter Linux `apt list --upgradable`, `dnf check-update` oder `pacman -Qu`. Die Eltern-UI listet diese Stände je Gerät. Gesetzte Häkchen legt „Ausgewählte aktualisieren“ in die Agenten-Warteschlange. „Updates abwählen“ hebt die Häkchen auf, ohne ein Update zu starten.

Linux-Updates laufen als root direkt über apt, dnf oder pacman.

## SSH (nur Linux, optional)

In der Eltern-UI: Host, Port, Benutzer und Pfad zum privaten Schlüssel auf dem Server.  
„SSH-Verbindung prüfen“ führt `echo kidscontrol-ok` aus.  
Ist SSH aktiv, startet „Update“ das Upgrade direkt über SSH, sonst über den Agenten.

## Sicherheit

- Device-Key geheim halten (wie ein Passwort)  
- Server idealerweise nur im Heimnetz oder hinter VPN/TLS  
- Verlorenes Gerät in der Eltern-UI entfernen (Key wird ungültig)
