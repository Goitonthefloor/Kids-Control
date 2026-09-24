# KidsControl – Architektur

Version: v1.0  
Fokus: zentraler Hub, OS-unabhängige Durchsetzung

## Zielbild

KidsControl ist die **zentrale Schaltstelle** für Eltern:

- Nutzungszeit von Kinder-PCs regeln (Zeitfenster + Tagesbudget)
- Ausgewählte Apps/Prozesse unterbinden
- Regeln einmal pflegen, auf **Windows, macOS und Linux** durchsetzen

Der Server ist die **einzige Quelle der Wahrheit**. Clients treffen keine eigenen Regeln.

## Komponenten

### 1. Server (Eltern-Hub)

- FastAPI + SQLite
- Web-UI für Kinder, Zeitpläne, App-Sperren, Geräte, Overrides
- Agent-API (`/api/v1/agent/sync`) mit Device-Key-Auth
- Audit-Protokoll elterlicher Aktionen

### 2. Agent (Kinder-PC)

- Läuft lokal als Dienst/Prozess
- Pollt den Server periodisch
- Meldet Hostname/OS und aktive Sitzung
- Setzt lokal durch:
  - Sitzung sperren, wenn Zeit abgelaufen
  - Gesperrte Apps beenden (Prozessnamen-Muster)
  - Vorwarnungen anzeigen

### 3. Geräte

Jedes Kinder-Gerät erhält einen geheimen **Device-Key**.  
Der Key bindet das Gerät an genau ein Kind-Profil.

## Entscheidungsreihenfolge (Sitzung)

1. Kind deaktiviert? → sperren  
2. Tages-Override („Heute unbegrenzt“)? → erlauben  
3. Aktive Stunden-Freigabe (+1h)? → erlauben  
4. Kein Zeitplan / außerhalb Fenster / 0 Minuten? → sperren  
5. Tagesbudget aufgebraucht? → sperren  
6. Sonst erlauben (optional Vorwarnung)

**App-Sperren** gelten zusätzlich (Scope `always`) auch während erlaubter Nutzungszeit.

**Programm-Kontingente** (Scope `quota`) erlauben ein Programm für eine Anzahl Minuten pro lokalem Tag. Der Agent meldet, ob der Prozess läuft. Läuft er noch und die Restzeit erreicht 5, 2 oder 1 Minute, erscheint auf dem Kinder-PC je Stufe eine Warnung. Ist das Kontingent aufgebraucht, wird der Prozess beendet, die restliche Sitzung bleibt davon unberührt.

## Softwarestände und Updates

- Eltern legen eine Beobachtungsliste (Paketnamen) je Kind an.
- Der Agent meldet die installierte Version (apt/rpm/pacman, Homebrew, winget).
- Der Agent meldet ausstehende Updates (winget, apt, dnf, pacman). Die Eltern-UI zeigt sie je Gerät mit Auswahl. „Ausgewählte aktualisieren“ legt nur die markierten Pakete in die Warteschlange. „Updates abwählen“ setzt die Markierung zurück.
- Updates können in die Agenten-Warteschlange gelegt werden.
- Linux-Geräte mit hinterlegtem SSH-Schlüssel können Updates sofort vom Server aus anstoßen (`BatchMode`, kein Passwort-Prompt).

## Nicht-Ziele

- keine Inhaltsfilterung / Web-Proxy-Pflicht
- kein Keylogging
- keine Bildschirmüberwachung
- kein Verhaltensprofiling

## Kommunikation

- Client → Server (Pull)
- Keine Push-Abhängigkeit
- Offline: Agent kann zuletzt bekannte Sperr-Policy hart halten (Erweiterung); v1.0 erfordert Erreichbarkeit für Freigaben
