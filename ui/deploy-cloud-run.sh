#!/usr/bin/env bash
# Βήμα 2 — Deploy Ergani UI στο Google Cloud Run (projectcar-7846b)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT_ID:-projectcar-7846b}"
REGION="${GCP_REGION:-europe-west1}"
SERVICE="${CLOUD_RUN_SERVICE:-ergani-ui}"
SA_JSON="${ERGANI_FIREBASE_CREDENTIALS:-$ROOT/ui/secrets/firebase-service-account.json}"
SECRET_NAME="${FIREBASE_SECRET_NAME:-ergani-firebase-sa}"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE}"

if [ -x /opt/homebrew/share/google-cloud-sdk/bin/gcloud ]; then
  export PATH="/opt/homebrew/share/google-cloud-sdk/bin:$PATH"
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "Εγκατάστησε Google Cloud SDK:" >&2
  echo "  brew install --cask google-cloud-sdk" >&2
  echo "Μετά: gcloud auth login && gcloud config set project $PROJECT_ID" >&2
  exit 1
fi

GCLOUD_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null || true)"
if ! gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
  echo "❌ Το gcloud ($GCLOUD_ACCOUNT) δεν έχει πρόσβαση στο $PROJECT_ID." >&2
  echo "Τρέξε στο Terminal:" >&2
  echo "  export PATH=\"/opt/homebrew/share/google-cloud-sdk/bin:\$PATH\"" >&2
  echo "  gcloud auth login" >&2
  echo "  → διάλεξε tsioumanisbusiness@gmail.com" >&2
  echo "  gcloud config set project $PROJECT_ID" >&2
  exit 1
fi

if [ ! -f "$SA_JSON" ]; then
  echo "Δεν βρέθηκε service account: $SA_JSON" >&2
  exit 1
fi

if grep -q '"private_key_id": "emulator-local"' "$SA_JSON" 2>/dev/null; then
  echo "Χρησιμοποίησε πραγματικό Firebase service account JSON." >&2
  exit 1
fi

for envfile in "$ROOT/ui/.env"; do
  if [ -f "$envfile" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$envfile"
    set +a
  fi
done

: "${ERGANI_UI_SECRET:?Ρύθμισε ERGANI_UI_SECRET στο ui/.env}"
: "${ERGANI_KIOSK_DEVICE_KEY:?Ρύθμισε ERGANI_KIOSK_DEVICE_KEY στο ui/.env}"

echo "=== Cloud Run deploy: $SERVICE ($PROJECT_ID / $REGION) ==="
gcloud config set project "$PROJECT_ID" >/dev/null

echo "→ Enable APIs…"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com >/dev/null

echo "→ Firebase service account secret…"
if ! gcloud secrets describe "$SECRET_NAME" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET_NAME" --replication-policy=automatic
fi
gcloud secrets versions add "$SECRET_NAME" --data-file="$SA_JSON" >/dev/null

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${RUN_SA}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null

echo "→ Build image (Cloud Build)…"
gcloud builds submit --tag "$IMAGE" .

ENV_FILE="$(mktemp)"
trap 'rm -f "$ENV_FILE"' EXIT
cat >"$ENV_FILE" <<EOF
FIREBASE_PROJECT_ID: "${FIREBASE_PROJECT_ID:-projectcar-7846b}"
ERGANI_FIREBASE_CREDENTIALS: "/secrets/firebase-sa.json"
ERGANI_UI_SECRET: "${ERGANI_UI_SECRET}"
ERGANI_UI_ADMIN_USER: "${ERGANI_UI_ADMIN_USER:-admin}"
ERGANI_UI_ADMIN_PASSWORD: "${ERGANI_UI_ADMIN_PASSWORD}"
ERGANI_KIOSK_DEVICE_KEY: "${ERGANI_KIOSK_DEVICE_KEY}"
ERGANI_KIOSK_COMPANY_IDS: "${ERGANI_KIOSK_COMPANY_IDS:-1}"
ERGANI_KIOSK_BRANCH_NUMBER: "${ERGANI_KIOSK_BRANCH_NUMBER:-0}"
ERGANI_KIOSK_WEB_USER: "${ERGANI_KIOSK_WEB_USER:-runwise}"
ERGANI_KIOSK_WEB_PASSWORD: "${ERGANI_KIOSK_WEB_PASSWORD}"
ERGANI_UI_HTTPS: "1"
ERGANI_AUTO_PUNCH_REMOTE_KEY: "${ERGANI_AUTO_PUNCH_REMOTE_KEY:-}"
EOF

echo "→ Deploy Cloud Run…"
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --set-secrets="/secrets/firebase-sa.json=${SECRET_NAME}:latest" \
  --env-vars-file "$ENV_FILE"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo
echo "✓ Deployed: $URL"
echo "Άνοιξε στο browser/tablet αυτό το URL."
echo "Admin: 5× tap στο Ergani → admin / (κωδικός από .env)"
