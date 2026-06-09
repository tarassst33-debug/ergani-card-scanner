#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-$PWD}:$PWD/ui"

for envfile in "$ROOT/.env" "$ROOT/ui/.env"; do
  if [ -f "$envfile" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$envfile"
    set +a
  fi
done

if [ "${ERGANI_AUTO_PUNCH_ENABLED:-}" != "1" ]; then
  echo "Όρισε ERGANI_AUTO_PUNCH_ENABLED=1 στο ui/.env" >&2
  exit 1
fi

if command -v uv >/dev/null 2>&1; then
  exec uv run --group ui python ui/auto_punch.py
fi

exec python3 ui/auto_punch.py
