#!/usr/bin/env bash
set -euo pipefail

DB_PATH="/opt/kids-control/app/data/kidscontrol.sqlite3"
OUT_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$OUT_DIR"

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "sqlite3 fehlt. Installiere mit: sudo apt install sqlite3"
  exit 1
fi

if [ ! -f "$DB_PATH" ]; then
  echo "DB nicht gefunden unter: $DB_PATH"
  exit 1
fi

echo "Exportiere Schema nach $OUT_DIR/schema.sql"
sqlite3 "$DB_PATH" ".schema" > "$OUT_DIR/schema.sql"

echo "Erzeuge leeres Seed-Template"
cat > "$OUT_DIR/seed.sample.sql" <<'SQL'
-- Example seed data (ANONYMIZED TEMPLATE)
-- Use only for dev/test. Do not include real names.

-- INSERT INTO children (...) VALUES (...);
SQL

echo "Fertig."

