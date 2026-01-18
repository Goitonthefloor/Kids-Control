# KidsControl – Datenbank & ORM

Version: v0.5

## Überblick

KidsControl verwendet **SQLAlchemy ORM** als primäre Datenbank-Schnittstelle.
Die Datenbank ist aktuell **SQLite**.

Das ORM ist maßgeblich – nicht das rohe SQLite-Schema.

## Aktueller Speicherort
/opt/kids-control/app/data/kidscontrol.sqlite3

## Tabellen (ORM-Sicht)

- children
- schedules
- overrides
- audit_log
- prewarn_log

## Wichtige Erkenntnis

Es gab einen Debug-Fall, bei dem:

- SQLAlchemy alle Tabellen kannte
- `sqlite3 .tables` jedoch nicht alle anzeigte

### Ursache

- Datenbank-Datei existierte
- Initialisierung/Migration wurde nicht sauber ausgeführt

### Lehre

> **ORM-Metadaten sind die Wahrheit.**  
> SQLite-Tools zeigen nur den aktuellen physischen Zustand.

## Konsequenzen

- Tabellen dürfen **nicht manuell** in SQLite erstellt werden
- Initialisierung erfolgt ausschließlich über SQLAlchemy
- Migrationslogik wird später ergänzt

## Warum SQLite?

- Einfach
- Robust
- Kein zusätzlicher Dienst
- Vollständig ausreichend für Heim- und kleine Domänen

Ein späterer Wechsel zu PostgreSQL ist vorgesehen, aber **kein Ziel von v0.5**.
