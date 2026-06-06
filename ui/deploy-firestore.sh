#!/usr/bin/env bash
# Deploy Firestore rules + indexes για projectcar-7846b
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v firebase >/dev/null 2>&1; then
  echo "Εγκατάστησε Firebase CLI: npm install -g firebase-tools" >&2
  exit 1
fi

echo "Deploy rules + indexes στο project από .firebaserc…"
firebase deploy --only firestore:rules,firestore:indexes
echo "Έτοιμο."
