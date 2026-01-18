# KDE Plasma Widget: KidsControl Status

Dieses Widget zeigt den aktuellen Status pro Kind sowie die verbleibende Zeit aus Kids-Control.

## API-Endpoint

Der Server liefert die Daten unter:

```
GET /api/widget/status?t=<token>
```

Der Token ist optional und wird über die Umgebungsvariable `KIDSCONTROL_WIDGET_TOKEN` abgesichert.
Wenn kein Token gesetzt ist, ist der Endpoint ohne Authentifizierung verfügbar.

Beispielantwort:

```json
{
  "server_time": "2024-01-01T10:15:00+01:00",
  "kids": [
    {
      "username": "kind1",
      "display_name": "Kind 1",
      "allow": true,
      "reason": "schedule",
      "reason_label": "Zeitplan",
      "warn": false,
      "remaining_minutes": 42,
      "remaining_label": "Noch 42 Min",
      "daily_remaining": 60,
      "daily_limit": 120,
      "minutes_left_window": 42,
      "override_text": null
    }
  ]
}
```

## Installation (lokal)

```bash
kpackagetool6 -t Plasma/Applet -i kde-widget/kidscontrol-status
```

Für Plasma 5 ggf.:

```bash
kpackagetool5 -t Plasma/Applet -i kde-widget/kidscontrol-status
```

Danach das Widget „KidsControl Status“ zu Plasma hinzufügen.

## Konfiguration im Widget

* **Server-URL:** Standard ist `http://localhost:8000/api/widget/status`
* **Widget-Token:** Optionaler Token passend zu `KIDSCONTROL_WIDGET_TOKEN`
* **Aktualisierung:** Standard 30 Sekunden

