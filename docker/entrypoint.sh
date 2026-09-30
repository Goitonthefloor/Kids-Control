#!/bin/sh
set -eu

if [ ! -f "${KIDSCONTROL_DATA_DIR}/server.env" ]; then
    if [ -z "${KIDSCONTROL_ADMIN_PASSWORD:-}" ] || [ -z "${KIDSCONTROL_SETUP_PASSWORD:-}" ]; then
        echo "KidsControl ist noch nicht eingerichtet." >&2
        echo "Setze KIDSCONTROL_ADMIN_PASSWORD und KIDSCONTROL_SETUP_PASSWORD (je mindestens 8 Zeichen) und starte den Container erneut." >&2
        exit 2
    fi
    python -m app.setup \
        --admin-user "${KIDSCONTROL_ADMIN_USER:-admin}" \
        --admin-password "$KIDSCONTROL_ADMIN_PASSWORD" \
        --setup-password "$KIDSCONTROL_SETUP_PASSWORD" \
        --timezone "${KIDSCONTROL_TZ:-Europe/Berlin}" \
        --host "${HOST:-0.0.0.0}" \
        --port "${PORT:-8000}"
fi

unset KIDSCONTROL_ADMIN_PASSWORD KIDSCONTROL_SETUP_PASSWORD
exec python -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
