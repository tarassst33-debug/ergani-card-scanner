#!/usr/bin/env bash
# Εγκατάσταση auto punch bot στο Mac mini (launchd service)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
USERNAME="$(whoami)"
PYTHON="/opt/homebrew/bin/python3.12"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3.12 || command -v python3)"
fi

LABEL="com.ergani.autopunch"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$ROOT/ui/logs"
RUN_SH="$ROOT/ui/run_auto_punch_mac.sh"

mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

if [ ! -f "$ROOT/ui/.env" ]; then
  echo "Λείπει $ROOT/ui/.env" >&2
  exit 1
fi
if [ ! -f "$ROOT/ui/secrets/firebase-service-account.json" ]; then
  echo "Λείπει firebase service account στο ui/secrets/" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Εγκατάσταση uv..."
  curl -fsSL https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

cd "$ROOT"
uv sync --locked --group ui --no-install-project
uv sync --locked --group ui

cat > "$RUN_SH" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="$ROOT"
cd "\$ROOT"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:\$PATH"
export PYTHONPATH="\$ROOT:\$ROOT/ui"
export ERGANI_FIREBASE_CREDENTIALS="\$ROOT/ui/secrets/firebase-service-account.json"
set -a
source "\$ROOT/ui/.env"
set +a
exec uv run --group ui python ui/auto_punch.py
EOF
chmod +x "$RUN_SH"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>WorkingDirectory</key>
    <string>${ROOT}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${RUN_SH}</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>${HOME}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>15</integer>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/auto_punch.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/auto_punch.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST"

echo "✓ Auto punch service: ${LABEL}"
echo "  Logs: tail -f ${LOG_DIR}/auto_punch.out.log"
launchctl list | grep ergani || true
