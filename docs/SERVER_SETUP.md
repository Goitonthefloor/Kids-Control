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
