# Kids-Control Windows 11 Client

Windows-Client für das Kids-Control System. Überwacht und beschränkt Bildschirmzeit und App-Zugriff basierend auf Server-Konfiguration.

## Features

✅ **Zeitlimit-Überwachung**: Prüft regelmäßig beim Server, ob Bildschirmzeit verfügbar ist
✅ **App-Blocking**: Blockiert vom Admin gesperrte Anwendungen automatisch
✅ **Warnungen**: Zeigt Benachrichtigungen, wenn Zeit bald abläuft
✅ **Screen-Lock**: Sperrt automatisch den Bildschirm, wenn Zeit abgelaufen ist
✅ **System-Tray**: Läuft unsichtbar im Hintergrund mit Icon im System-Tray
✅ **Auto-Start**: Startet automatisch mit Windows

## Voraussetzungen

- Windows 11 (oder Windows 10)
- Python 3.8 oder höher
- Administrator-Rechte für Installation
- Netzwerkverbindung zum Kids-Control Server

## Installation

### 1. Python installieren

Falls noch nicht vorhanden:

1. Download von [python.org](https://www.python.org/downloads/)
2. Installation mit **"Add Python to PATH"** Option
3. Verifizieren:
   ```cmd
   python --version
   ```

### 2. Client herunterladen

```cmd
cd C:\Program Files
git clone https://github.com/Goitonthefloor/Kids-Control.git
cd Kids-Control\windows-client
```

Oder ZIP herunterladen und entpacken:
```
https://github.com/Goitonthefloor/Kids-Control/archive/refs/heads/Perplexity-Merge.zip
```

### 3. Dependencies installieren

```cmd
cd windows-client
pip install -r requirements.txt
```

Das installiert:
- `requests` - Server-Kommunikation
- `psutil` - Prozess-Überwachung
- `pystray` - System-Tray Icon
- `Pillow` - Icon-Generierung
- `pywin32` - Windows-Integration

### 4. Konfiguration erstellen

Erstelle `C:\Users\<Username>\.kidscontrol\config.json`:

```json
{
  "server_url": "http://192.168.1.100:8000",
  "username": "max",
  "check_interval": 60,
  "auto_start": true
}
```

**Parameter:**
- `server_url`: Adresse des Kids-Control Servers
- `username`: Benutzername des Kindes (wie im Server konfiguriert)
- `check_interval`: Prüfintervall in Sekunden (Standard: 60)
- `auto_start`: Automatisch mit Windows starten (Standard: true)

### 5. Client starten

```cmd
python KidsControlClient.py
```

Das erstellt:
- System-Tray Icon (blaues "KC" Icon)
- Log-Datei: `C:\Users\<Username>\.kidscontrol\client.log`
- Auto-Start Eintrag in Windows Registry

## Verwendung

### System-Tray Icon

Rechtsklick auf das Icon zeigt:

- **Status**: Zeigt aktuellen Status (erlaubt/gesperrt) und gesperrte Apps
- **Konfiguration**: Zeigt Server-URL und Benutzername
- **Beenden**: Stoppt den Client (nur für Tests - wird automatisch neugestartet)

### Automatische Funktionen

**Zeitprüfung:**
- Client fragt alle 60 Sekunden beim Server nach
- Endpoint: `GET /api/check/{username}`
- Server antwortet mit `allowed: true/false` und `blocked_apps: [...]`

**Warnungen:**
- 10 Minuten vor Ablauf: Warnung via Windows-Notification
- 5 Minuten vor Ablauf: Weitere Warnung
- Bei Ablauf: Screen Lock + Benachrichtigung

**App-Blocking:**
- Überwacht alle laufenden Prozesse
- Vergleicht mit `blocked_apps` Liste vom Server
- Beendet gesperrte Apps sofort
- Zeigt Benachrichtigung: "Die App 'XYZ' ist gesperrt"

**Screen Lock:**
- Wenn `allowed: false` vom Server
- Ruft `LockWorkStation()` auf
- Benutzer muss sich neu anmelden (Windows-Login)

## Server-Integration

### API Endpoint erweitern

Der Server muss `/api/check/{username}` erweitern, um `blocked_apps` zurückzugeben:

```python
# app/main.py
@app.get("/api/check/{user}")
def api_check(user: str, db: Session = Depends(get_db)):
    # Existing time check logic...
    allowed = check_if_time_allowed(user, db)
    
    # NEW: Get blocked apps for this child
    child = db.query(Child).filter_by(username=user).first()
    blocked_apps = []
    
    if child and hasattr(child, 'blocked_apps'):
        blocked_apps = child.blocked_apps.split(',') if child.blocked_apps else []
    
    return {
        "allowed": allowed,
        "remaining_minutes": calculate_remaining(user, db),
        "blocked_apps": blocked_apps,
        "checked_at": datetime.now().isoformat()
    }
```

### Datenbank erweitern

Füge `blocked_apps` Spalte zur `children` Tabelle hinzu:

```sql
ALTER TABLE children ADD COLUMN blocked_apps VARCHAR;
```

Oder in `app/db.py`:

```python
class Child(Base):
    __tablename__ = "children"
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    blocked_apps = Column(String, nullable=True)  # Comma-separated list
```

### Admin-UI erweitern

Füge App-Blocking zur Child-Config hinzu:

```html
<!-- templates/child_edit.html -->
<div class="form-group">
  <label>Gesperrte Apps (kommagetrennt):</label>
  <input type="text" name="blocked_apps" 
         value="{{ child.blocked_apps }}" 
         placeholder="chrome.exe, steam.exe, fortnite.exe">
  <small>App-Namen oder Pfade, durch Kommas getrennt</small>
</div>
```

## Konfiguration

### App-Namen finden

Um herauszufinden, welcher Prozess-Name blockiert werden soll:

```python
import psutil

for proc in psutil.process_iter(['pid', 'name', 'exe']):
    try:
        print(f"{proc.info['name']:30} -> {proc.info['exe']}")
    except:
        pass
```

**Beispiele:**
- Chrome: `chrome.exe` oder `C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe`
- Steam: `steam.exe`
- Minecraft: `javaw.exe` oder `minecraft.exe`
- Fortnite: `FortniteClient-Win64-Shipping.exe`
- Discord: `Discord.exe`

### Beispiel Blocked-Apps Liste

Im Server für ein Kind konfigurieren:

```
chrome.exe, steam.exe, Discord.exe, FortniteClient-Win64-Shipping.exe
```

Client prüft sowohl:
- Exakte Dateinamen: `chrome.exe`
- Pfad-Substrings: `steam` matched `C:\Program Files\Steam\steam.exe`

## Troubleshooting

### Client startet nicht

**Prüfe Python-Installation:**
```cmd
python --version
pip list | findstr "requests psutil pystray"
```

**Installiere fehlende Pakete:**
```cmd
pip install -r requirements.txt --upgrade
```

### Keine Verbindung zum Server

**Teste Server-Erreichbarkeit:**
```cmd
curl http://192.168.1.100:8000/api/check/max
```

Oder im Browser: `http://server-ip:8000/api/check/username`

**Prüfe Firewall:**
- Windows Firewall erlaubt ausgehende Verbindungen zu Port 8000?
- Server-Firewall erlaubt eingehende Verbindungen?

### Apps werden nicht blockiert

**Prüfe Administrator-Rechte:**
```cmd
# Client als Administrator starten
runas /user:Administrator python KidsControlClient.py
```

**Prüfe Log-Datei:**
```cmd
type %USERPROFILE%\.kidscontrol\client.log
```

**Prüfe App-Namen:**
```python
# Zeige laufende Prozesse
python -c "import psutil; [print(p.info) for p in psutil.process_iter(['name'])]"
```

### Screen Lock funktioniert nicht

**Erfordert Admin-Rechte.** Client muss als Administrator laufen:

```cmd
# Task Scheduler für Auto-Start als Admin:
schtasks /create /tn "KidsControlClient" /tr "python C:\Path\To\KidsControlClient.py" /sc onlogon /rl highest
```

### Client läuft mehrfach

**Beende alle Instanzen:**
```cmd
taskkill /F /IM python.exe
```

Oder im Task Manager: `python.exe` Prozesse beenden.

## Deinstallation

### 1. Auto-Start entfernen

```cmd
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v KidsControlClient /f
```

### 2. Client-Prozess beenden

```cmd
taskkill /F /IM python.exe
```

### 3. Dateien löschen

```cmd
rmdir /S /Q "C:\Program Files\Kids-Control\windows-client"
rmdir /S /Q "%USERPROFILE%\.kidscontrol"
```

## Sicherheitshinweise

⚠️ **Der Client ist KEIN vollständiger Schutz!**

Erfahrene Benutzer können:
- Client-Prozess beenden (`taskkill`)
- Auto-Start deaktivieren (Registry)
- Netzwerkverbindung unterbrechen
- VM oder zweites Betriebssystem verwenden

**Empfohlene zusätzliche Maßnahmen:**

1. **Kein Admin-Zugang**: Kind hat nur Standard-Benutzer-Konto
2. **BIOS-Passwort**: Verhindert Boot von USB/CD
3. **Router-Regeln**: Blockiere Gerät bei Server-Ausfall
4. **Physische Aufsicht**: Bester Schutz ist aktive Betreuung

## Weiterentwicklung

Geplante Features:

- 🔒 **Tamper Protection**: Client-Prozess schützen
- 📸 **Screenshots**: Periodische Screenshots zur Überwachung
- 🎮 **Spielzeit-Tracking**: Spezielle Limits für Games
- 🔔 **Erweiterte Notifications**: Countdown-Timer im Tray
- ⚙️ **GUI Konfiguration**: Einstellungen ohne JSON-Datei
- 📦 **Installer**: MSI-Paket für einfache Installation
- 🔄 **Auto-Update**: Client aktualisiert sich selbst

## Support

**Probleme oder Fragen?**

Email: rolf_greger@web.de

Oder GitHub Issue erstellen:
https://github.com/Goitonthefloor/Kids-Control/issues

## Lizenz

Siehe Haupt-Repository LICENSE-Datei.
