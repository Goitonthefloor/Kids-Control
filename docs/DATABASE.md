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
| `app_rules` | Programme: Sperre oder Tageskontingent (`daily_minutes` bei Scope `quota`) |
| `app_usage` | Verbrauchte Minuten eines Programm-Kontingents je lokalem Tag |
| `overrides` | Zeitlich befristete Freigaben (+1h) |
| `day_overrides` | „Heute unbegrenzt“ |
| `daily_usage` | Verbrauchte Minuten je lokalem Tag |
| `audit_log` | Nachvollziehbare Eltern-Aktionen |

## App-Regeln

- `pattern`: z.B. `minecraft`, `steam`, `RobloxPlayerBeta.exe`
- `match_mode`: `contains` \| `exact` \| `startswith`
- `scope`: `always` \| `when_denied` \| `quota`
- `daily_minutes`: nur bei `quota`, Minuten pro lokalem Tag

Matching ist absichtlich OS-agnostisch (Prozess-/Dateiname).

## ORM

SQLAlchemy-Modelle in `app/db.py` sind maßgeblich.
