# KidsControl – Server Setup

Version: v0.5

## Installationspfad

/opt/kids-control

markdown
Code kopieren

## Benutzer & Rechte

- dedizierter Benutzer: `gregerr`
- keine Root-Ausführung der App
- Root nur für:
  - Installation
  - systemd
  - Firewall

## Python-Umgebung

- Python venv unter:
/opt/kids-control/.venv

bash
Code kopieren

- Start & Tests erfolgen explizit über die venv

Beispiel:
```bash
sudo -u gregerr /opt/kids-control/.venv/bin/python
Start via systemd

systemd-Service ist vorhanden

startet nach Netzwerk

kein AD-Zwang beim Start

Ziel:

Server muss starten können, auch wenn Infrastruktur verzögert ist.

Logging

Logs gehen aktuell an stdout/systemd

Erweiterte Audit-Logs liegen in der Datenbank

Philosophie

explizite Pfade

keine Magie

kein „läuft schon irgendwie“

Das System soll debugbar bleiben.


# KidsControl – Status v0.5

## Was funktioniert

- Server startet stabil
- Web-UI ist erreichbar
- Datenbank ist angebunden
- ORM-Modelle sind konsistent
- Audit- und Entscheidungslogik existiert

## Was bewusst fehlt

- produktive Clients
- Tray-Anwendung
- Offline-Cache
- Benutzerfreundliche Installer

## Was nicht kaputt ist

- Kerberos ist kein Blocker
- AD ist keine Pflicht
- SQLite ist kein Provisorium
- Architektur ist konsistent

## Bekannte technische Schulden

- keine Migrationen
- kein Schema-Versionsmanagement
- keine API-Versionierung

Diese Punkte sind bekannt und akzeptiert.

## Ziel dieses Status

Dieser Stand ist ein **stabiler Fixpunkt**.
Alle weiteren Entwicklungen bauen darauf auf oder ändern ihn bewusst.

> v0.5 ist kein Prototyp – es ist ein Fundament.
