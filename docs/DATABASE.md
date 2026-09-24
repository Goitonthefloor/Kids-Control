# KidsControl – Datenmodell

Version: v1.0

## Speicher

Standard: SQLite unter `./data/kidscontrol.sqlite3`  
(überschreibbar mit `KIDSCONTROL_DATA_DIR` oder `DATABASE_URL`)

Initialisierung ausschließlich über SQLAlchemy (`init_db()`).

## Tabellen

| Tabelle | Zweck |
|---------|--------|
| `children` | Kind-Profile (slug, Name, Zeitzone, Vorwarnung) |
| `devices` | Registrierte PCs + Device-Key + OS |
| `schedules` | Pro Kind und Wochentag: Start/Ende/Tagesminuten |
| `app_rules` | App-/Prozess-Sperren (Muster, Match-Modus, Scope) |
| `overrides` | Zeitlich befristete Freigaben (+1h) |
| `day_overrides` | „Heute unbegrenzt“ |
| `daily_usage` | Verbrauchte Minuten je lokalem Tag |
| `audit_log` | Nachvollziehbare Eltern-Aktionen |
| `pending_updates` | Vom Client gemeldete ausstehende Paket-Updates (installierte und verfügbare Version) |

## App-Regeln

- `pattern`: z.B. `minecraft`, `steam`, `RobloxPlayerBeta.exe`
- `match_mode`: `contains` \| `exact` \| `startswith`
- `scope`: `always` \| `when_denied`

Matching ist absichtlich OS-agnostisch (Prozess-/Dateiname).

## ORM

SQLAlchemy-Modelle in `app/db.py` sind maßgeblich.
