#!/usr/bin/env bash
# Βήμα 1 — Production Firebase (projectcar-7846b)
# Τρέξε από root project: ./ui/setup-step1-production-firebase.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SA_PATH="${ERGANI_FIREBASE_CREDENTIALS:-$ROOT/ui/secrets/firebase-service-account.json}"
PROJECT_ID="${FIREBASE_PROJECT_ID:-projectcar-7846b}"

echo "=== Βήμα 1: Production Firebase ($PROJECT_ID) ==="
echo

# 1) Έλεγχος service account
if [ ! -f "$SA_PATH" ]; then
  echo "❌ Δεν βρέθηκε service account: $SA_PATH"
  echo
  echo "Κάνε στο Firebase Console (λογαριασμός με πρόσβαση στο project):"
  echo "  https://console.firebase.google.com/project/$PROJECT_ID/settings/serviceaccounts/adminsdk"
  echo "  → Generate new private key → αποθήκευσε ως:"
  echo "  $ROOT/ui/secrets/firebase-service-account.json"
  exit 1
fi

if grep -q '"private_key_id": "emulator-local"' "$SA_PATH" 2>/dev/null; then
  echo "❌ Το service account είναι τοπικό (emulator) — όχι production."
  echo "   Κατέβασε πραγματικό JSON από το Firebase Console (link πάνω)."
  exit 1
fi

echo "✓ Service account JSON: $SA_PATH"

# 2) Deploy Firestore rules
if command -v firebase >/dev/null 2>&1; then
  echo
  echo "Deploy Firestore rules + indexes…"
  if firebase deploy --only firestore:rules,firestore:indexes --project "$PROJECT_ID"; then
    echo "✓ Rules deployed"
  else
    echo
    echo "⚠ Deploy απέτυχε — συνήθως χρειάζεται:"
    echo "  1. firebase login  (με Google account που έχει πρόσβαση στο $PROJECT_ID)"
    echo "  2. IAM role στο project: Editor ή Firebase Admin"
    echo "  https://console.firebase.google.com/project/$PROJECT_ID/settings/iam"
    echo
    echo "Μπορείς να ξανατρέξεις αυτό το script αφού διορθώσεις τα permissions."
  fi
else
  echo "⚠ Firebase CLI λείπει: npm install -g firebase-tools"
fi

# 3) Έλεγχος σύνδεσης cloud Firestore (χωρίς emulator)
echo
echo "Έλεγχος σύνδεσης cloud Firestore…"
unset FIRESTORE_EMULATOR_HOST
export FIREBASE_PROJECT_ID="$PROJECT_ID"
export ERGANI_FIREBASE_CREDENTIALS="$SA_PATH"
export PYTHONPATH="${PYTHONPATH:-$ROOT}:$ROOT/ui"

if command -v uv >/dev/null 2>&1; then
  if uv run --group ui python ui/check_firebase.py; then
    echo "✓ Cloud Firestore OK"
  else
    echo "❌ Αποτυχία σύνδεσης — έλεγξε service account και ότι το Firestore είναι ενεργό στο Console."
    exit 1
  fi
else
  python3 ui/check_firebase.py || exit 1
fi

echo
echo "=== Επόμενο (χειροκίνητα στο ui/.env) ==="
echo "  1. ΣΒΗΣΕ τη γραμμή: FIRESTORE_EMULATOR_HOST=127.0.0.1:8080"
echo "  2. Βεβαιώσου: FIREBASE_PROJECT_ID=$PROJECT_ID"
echo "  3. ΜΗΝ βάλεις ERGANI_UI_SYNC_ADMIN_PASSWORD=1 σε production"
echo
echo "Μετά restart: ./ui/run.sh"
echo "Έλεγξε δεδομένα: https://console.firebase.google.com/project/$PROJECT_ID/firestore"
echo
echo "Όταν τελειώσει το βήμα 1, πες μου για Βήμα 2 (Cloud Run)."
