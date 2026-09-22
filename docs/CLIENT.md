# KidsControl – Client Agent

Version: v1.0

Der Agent läuft auf dem Kinder-PC und holt Regeln vom zentralen Server.

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

Für harte Durchsetzung sollte der Agent mit ausreichenden Rechten und als Autostart/Dienst laufen (systemd / launchd / Windows-Dienst – je nach Umgebung).

## Softwarestände und Updates

Beim Sync sendet der Agent Versionen der beobachteten Pakete und holt ausstehende Update-Befehle ab (`update_one` / `update_all`). Ergebnisse gehen an `POST /api/v1/agent/commands/{id}/result`.

Linux-Updates erwarten passwortloses `sudo` für apt, dnf oder pacman.

## SSH (nur Linux, optional)

In der Eltern-UI: Host, Port, Benutzer und Pfad zum privaten Schlüssel auf dem Server.  
„SSH-Verbindung prüfen“ führt `echo kidscontrol-ok` aus.  
Ist SSH aktiv, startet „Update“ das Upgrade direkt über SSH, sonst über den Agenten.

## Sicherheit

- Device-Key geheim halten (wie ein Passwort)  
- Server idealerweise nur im Heimnetz oder hinter VPN/TLS  
- Verlorenes Gerät in der Eltern-UI entfernen (Key wird ungültig)
