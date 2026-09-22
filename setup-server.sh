#!/usr/bin/env bash
# One-click KidsControl server setup (Linux and macOS).
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.10 oder neuer wird benötigt." >&2
  exit 1
fi

python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -q -r requirements.txt

PORT="${PORT:-8000}"
URL="http://127.0.0.1:${PORT}/"
echo "KidsControl startet auf ${URL}"
echo "Beim ersten Start die Einrichtung im Browser abschließen."
( sleep 2
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then open "$URL" >/dev/null 2>&1 || true
  fi
) &
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
