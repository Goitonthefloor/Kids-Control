# Server-Integration für App-Blocking

Dieser Guide zeigt, wie der Kids-Control Server erweitert wird, um App-Blocking für den Windows-Client zu unterstützen.

## Übersicht

Der Windows-Client benötigt:
1. Liste gesperrter Apps pro Kind vom Server
2. API-Endpoint zur Abfrage dieser Liste
3. Admin-UI zum Konfigurieren gesperrter Apps

## Schritt 1: Datenbank-Schema erweitern

### Migration erstellen

```python
# app/migrations/add_blocked_apps.py
from app.db import engine
from sqlalchemy import text

def upgrade():
    """Add blocked_apps column to children table."""
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE children ADD COLUMN blocked_apps TEXT"
        ))
        conn.commit()
    print("✓ Added blocked_apps column")

def downgrade():
    """Remove blocked_apps column."""
    with engine.connect() as conn:
        # SQLite doesn't support DROP COLUMN directly
        # Would need to recreate table
        pass

if __name__ == "__main__":
    upgrade()
```

### Modell aktualisieren

```python
# app/db.py
class Child(Base):
    __tablename__ = "children"
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    blocked_apps = Column(String, nullable=True)  # NEW: Comma-separated list
```

## Schritt 2: API-Endpoint erweitern

### Existing /api/check erweitern

```python
# app/main.py
from typing import List

@app.get("/api/check/{user}")
def api_check(user: str, db: Session = Depends(get_db)):
    """
    Check if user is allowed to use computer.
    
    Returns:
        - allowed: bool - Whether screen time is allowed
        - remaining_minutes: int - Minutes remaining today
        - blocked_apps: list[str] - Apps this user cannot run
        - checked_at: str - Server timestamp
    """
    # Existing logic for time check
    child = db.query(Child).filter_by(username=user).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Calculate if time is allowed (existing logic)
    allowed, remaining = check_time_allowed(user, db)
    
    # NEW: Get blocked apps
    blocked_apps = []
    if child.blocked_apps:
        # Parse comma-separated list
        blocked_apps = [
            app.strip() 
            for app in child.blocked_apps.split(',')
            if app.strip()
        ]
    
    return {
        "allowed": allowed,
        "remaining_minutes": remaining,
        "blocked_apps": blocked_apps,
        "checked_at": datetime.now(timezone.utc).isoformat()
    }
```

### Helper-Funktion

```python
# app/main.py
def check_time_allowed(username: str, db: Session) -> tuple[bool, int]:
    """
    Check if child has remaining time.
    
    Returns:
        (allowed: bool, remaining_minutes: int)
    """
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    
    # Check for day override (unlimited)
    day_override = db.query(DayOverride).filter_by(
        username=username,
        day=today
    ).first()
    
    if day_override and day_override.enabled:
        return True, 999  # Unlimited
    
    # Check for hour override
    hour_override = db.query(Override).filter(
        Override.username == username,
        Override.grant_until > now
    ).first()
    
    if hour_override:
        return True, 60  # Extended time
    
    # Check schedule and usage
    schedule = get_current_schedule(username, now, db)
    if not schedule:
        return False, 0
    
    usage = db.query(DailyUsage).filter_by(
        username=username,
        day=today
    ).first()
    
    used_minutes = usage.used_minutes if usage else 0
    remaining = schedule.daily_minutes - used_minutes
    
    return remaining > 0, max(0, remaining)
```

## Schritt 3: Admin-UI erweitern

### Child-Edit Formular

```html
<!-- templates/child_edit.html -->
{% extends "base.html" %}

{% block content %}
<div class="container">
  <h1>Kind bearbeiten: {{ child.display_name }}</h1>
  
  <form method="post" action="/child/{{ child.username }}/update">
    <!-- Existing fields: display_name, etc. -->
    
    <!-- NEW: Blocked Apps Section -->
    <div class="form-group mt-4">
      <h3>App-Einschränkungen</h3>
      
      <label for="blocked_apps">Gesperrte Apps:</label>
      <textarea 
        id="blocked_apps" 
        name="blocked_apps" 
        class="form-control"
        rows="4"
        placeholder="chrome.exe, steam.exe, Discord.exe"
      >{{ child.blocked_apps or '' }}</textarea>
      
      <small class="form-text text-muted">
        App-Namen oder Pfade, durch Kommas getrennt.<br>
        Beispiele: <code>chrome.exe</code>, <code>steam.exe</code>, <code>FortniteClient-Win64-Shipping.exe</code>
      </small>
      
      <div class="alert alert-info mt-2">
        <strong>Hinweis:</strong> Diese Einschränkungen gelten nur für Windows-Clients.
        Der Windows-Client muss auf dem Rechner des Kindes installiert sein.
      </div>
    </div>
    
    <!-- Common blocked apps suggestions -->
    <div class="form-group">
      <label>Häufige Apps zum Blocken:</label>
      <div class="btn-group-vertical" role="group">
        <button type="button" class="btn btn-sm btn-outline-secondary" 
                onclick="addBlockedApp('chrome.exe')">
          🌐 Chrome Browser
        </button>
        <button type="button" class="btn btn-sm btn-outline-secondary"
                onclick="addBlockedApp('steam.exe')">
          🎮 Steam Gaming Platform
        </button>
        <button type="button" class="btn btn-sm btn-outline-secondary"
                onclick="addBlockedApp('Discord.exe')">
          💬 Discord
        </button>
        <button type="button" class="btn btn-sm btn-outline-secondary"
                onclick="addBlockedApp('FortniteClient-Win64-Shipping.exe')">
          🔫 Fortnite
        </button>
        <button type="button" class="btn btn-sm btn-outline-secondary"
                onclick="addBlockedApp('javaw.exe')">
          ⛏ Minecraft (Java)
        </button>
      </div>
    </div>
    
    <div class="form-group mt-4">
      <button type="submit" class="btn btn-primary">Speichern</button>
      <a href="/child/{{ child.username }}" class="btn btn-secondary">Abbrechen</a>
    </div>
  </form>
</div>

<script>
function addBlockedApp(appName) {
  const textarea = document.getElementById('blocked_apps');
  const current = textarea.value.trim();
  
  // Check if already exists
  if (current.includes(appName)) {
    return;
  }
  
  // Add to list
  if (current) {
    textarea.value = current + ', ' + appName;
  } else {
    textarea.value = appName;
  }
}
</script>
{% endblock %}
```

### Update-Endpoint

```python
# app/main.py
@app.post("/child/{user}/update")
def update_child(
    user: str,
    display_name: str = Form(...),
    blocked_apps: str = Form(""),
    db: Session = Depends(get_db),
    current_user: str = Depends(require_auth)
):
    """
    Update child configuration including blocked apps.
    """
    child = db.query(Child).filter_by(username=user).first()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    
    # Update fields
    child.display_name = display_name
    child.blocked_apps = blocked_apps.strip()  # NEW
    
    db.commit()
    
    # Log action
    audit_log = AuditLog(
        at=datetime.now(timezone.utc),
        actor=current_user,
        child=user,
        action="update_child",
        details=f"Updated blocked_apps: {blocked_apps}"
    )
    db.add(audit_log)
    db.commit()
    
    return RedirectResponse(f"/child/{user}", status_code=303)
```

## Schritt 4: Child-Detail Seite

### Blocked Apps anzeigen

```html
<!-- templates/child_detail.html -->
{% extends "base.html" %}

{% block content %}
<div class="container">
  <h1>{{ child.display_name }}</h1>
  
  <!-- Existing sections: schedule, usage, etc. -->
  
  <!-- NEW: Blocked Apps Section -->
  <div class="card mt-4">
    <div class="card-header">
      <h3>App-Einschränkungen</h3>
    </div>
    <div class="card-body">
      {% if child.blocked_apps %}
        <ul class="list-group">
          {% for app in child.blocked_apps.split(',') %}
            <li class="list-group-item">
              <code>{{ app.strip() }}</code>
            </li>
          {% endfor %}
        </ul>
      {% else %}
        <p class="text-muted">Keine Apps blockiert</p>
      {% endif %}
      
      <a href="/child/{{ child.username }}/edit" class="btn btn-primary mt-3">
        App-Einschränkungen bearbeiten
      </a>
    </div>
  </div>
</div>
{% endblock %}
```

## Schritt 5: Testing

### Test API Response

```bash
# Test without blocked apps
curl http://localhost:8000/api/check/testuser

# Expected:
{
  "allowed": true,
  "remaining_minutes": 120,
  "blocked_apps": [],
  "checked_at": "2026-02-09T12:00:00Z"
}

# Add blocked apps via UI, then test again
curl http://localhost:8000/api/check/testuser

# Expected:
{
  "allowed": true,
  "remaining_minutes": 120,
  "blocked_apps": ["chrome.exe", "steam.exe", "Discord.exe"],
  "checked_at": "2026-02-09T12:00:00Z"
}
```

### Test Client Integration

```python
# Test script
import requests

response = requests.get("http://localhost:8000/api/check/testuser")
data = response.json()

print(f"Allowed: {data['allowed']}")
print(f"Remaining: {data['remaining_minutes']} minutes")
print(f"Blocked apps: {', '.join(data['blocked_apps'])}")
```

## Schritt 6: Migration durchführen

### Auf Production Server

```bash
# 1. Backup erstellen
cp /opt/kids-control/app/data/kidscontrol.sqlite3 \
   /opt/kids-control/app/data/kidscontrol.sqlite3.backup

# 2. Server stoppen
sudo systemctl stop kidscontrol

# 3. Code aktualisieren
cd /opt/kids-control
git pull origin Perplexity-Merge

# 4. Migration ausführen
python3 -c "from app.migrations.add_blocked_apps import upgrade; upgrade()"

# 5. Server starten
sudo systemctl start kidscontrol

# 6. Verifizieren
curl http://localhost:8000/api/check/username
```

## Troubleshooting

### Migration schlägt fehl

**Manuell ausführen:**

```bash
sqlite3 /opt/kids-control/app/data/kidscontrol.sqlite3

ALTER TABLE children ADD COLUMN blocked_apps TEXT;
.quit
```

### API gibt keine blocked_apps zurück

**Prüfe Datenbank:**

```bash
sqlite3 /opt/kids-control/app/data/kidscontrol.sqlite3

SELECT username, blocked_apps FROM children;
```

**Prüfe Server-Logs:**

```bash
sudo journalctl -u kidscontrol -n 50
```

## Beispiel App-Namen

Häufig zu blockierende Apps:

### Gaming
```
steam.exe
FortniteClient-Win64-Shipping.exe
LeagueClient.exe
Minecraft.exe
javaw.exe
RobloxPlayerBeta.exe
```

### Social Media
```
Discord.exe
Telegram.exe
WhatsApp.exe
Skype.exe
```

### Browsers (komplett)
```
chrome.exe
firefox.exe
msedge.exe
opera.exe
brave.exe
```

### Entertainment
```
Spotify.exe
vlc.exe
Netflix.exe
YouTube.exe
```

## Sicherheitshinweise

⚠️ **Wichtige Einschränkungen:**

1. **Keine perfekte Sicherheit**: Technisch versierte Kinder können Client deaktivieren
2. **Benennung**: Apps können umbenannt werden (`chrome.exe` → `browser.exe`)
3. **Portable Apps**: Nicht installierte Apps schwerer zu blockieren
4. **VM/WSL**: Virtuelle Maschinen oder Linux-Subsystem umgehen Client

**Empfohlene Zusatzmaßnahmen:**

- Kind hat nur Standard-Benutzer-Rechte (kein Admin)
- BIOS-Passwort gegen Boot von USB
- Router-Level Filtering als Backup
- Regelmäßige Gespräche über digitale Mediennutzung

## Kontakt

Fragen? rolf_greger@web.de
