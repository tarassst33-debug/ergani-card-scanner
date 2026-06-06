#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-$PWD}"

for envfile in "$ROOT/.env" "$ROOT/ui/.env"; do
  if [ -f "$envfile" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$envfile"
    set +a
  fi
done

export FIREBASE_PROJECT_ID="${FIREBASE_PROJECT_ID:-projectcar-7846b}"
DEFAULT_SA="$ROOT/ui/secrets/firebase-service-account.json"
if [ -z "${ERGANI_FIREBASE_CREDENTIALS:-}" ] && [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && [ -f "$DEFAULT_SA" ]; then
  export ERGANI_FIREBASE_CREDENTIALS="$DEFAULT_SA"
fi

if [ -z "${ERGANI_FIREBASE_CREDENTIALS:-}" ] && [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && [ ! -f "$DEFAULT_SA" ]; then
  if [ -z "${FIRESTORE_EMULATOR_HOST:-}" ]; then
    export FIRESTORE_EMULATOR_HOST="127.0.0.1:8080"
    echo "Χωρίς service account — χρήση Firestore emulator στο $FIRESTORE_EMULATOR_HOST" >&2
    echo "Για production: ui/secrets/firebase-service-account.json (δες ui/secrets/README.md)" >&2
  fi
fi
if [ -z "${ERGANI_UI_SECRET:-}" ] || [ "${#ERGANI_UI_SECRET}" -lt 32 ]; then
  echo "Ρύθμισε ERGANI_UI_SECRET (≥32 χαρακτήρες). Δες ui/SECURITY.md." >&2
  exit 1
fi

if command -v uv >/dev/null 2>&1; then
  exec uv run --group ui python ui/app.py
fi

python3 -m pip install -q flask requests firebase-admin 2>/dev/null || true
exec python3 ui/app.py
