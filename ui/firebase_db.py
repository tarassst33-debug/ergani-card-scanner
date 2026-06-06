"""Firebase Admin / Firestore client for the Ergani UI (server-side only)."""

from __future__ import annotations

import json
import os
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ID = "projectcar-7846b"
DEFAULT_CREDENTIAL_PATHS = (
    UI_DIR / "secrets" / "firebase-service-account.json",
    UI_DIR / "secrets" / "service-account.json",
)

_db = None


def default_project_id() -> str:
    return (
        os.environ.get("FIREBASE_PROJECT_ID", "").strip()
        or DEFAULT_PROJECT_ID
    )


def _credentials_path() -> Path:
    raw = (
        os.environ.get("ERGANI_FIREBASE_CREDENTIALS")
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        or ""
    ).strip()
    if raw:
        path = Path(raw).expanduser()
        if path.is_file():
            return path
        raise RuntimeError(f"Δεν βρέθηκε αρχείο Firebase credentials: {path}")

    for candidate in DEFAULT_CREDENTIAL_PATHS:
        if candidate.is_file():
            return candidate

    raise RuntimeError(
        "Βάλε το service account JSON στο ui/secrets/firebase-service-account.json "
        "(Firebase Console → projectcar-7846b → Service accounts → Generate new private key). "
        "Δες ui/secrets/README.md."
    )


def _emulator_host() -> str:
    return os.environ.get("FIRESTORE_EMULATOR_HOST", "").strip()


def get_firestore():
    """Return the shared Firestore client (initializes Firebase Admin once)."""
    global _db
    if _db is not None:
        return _db

    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        project_id = default_project_id()
        if _emulator_host():
            firebase_admin.initialize_app(options={"projectId": project_id})
        else:
            try:
                cred_path = _credentials_path()
                with cred_path.open(encoding="utf-8") as fh:
                    cred_data = json.load(fh)
                project_id = cred_data.get("project_id") or project_id
                cred = credentials.Certificate(str(cred_path))
                firebase_admin.initialize_app(cred, {"projectId": project_id})
            except RuntimeError:
                if os.environ.get("ERGANI_UI_USE_ADC", "").strip() in {
                    "1",
                    "true",
                    "yes",
                }:
                    cred = credentials.ApplicationDefault()
                    firebase_admin.initialize_app(
                        cred, {"projectId": project_id}
                    )
                else:
                    raise

    _db = firestore.client()
    return _db


def ping_firestore() -> dict[str, str]:
    """Lightweight connectivity check (reads meta/counters + schema)."""
    from store import ensure_firestore_schema

    ensure_firestore_schema()
    db = get_firestore()
    counters = db.collection("meta").document("counters").get()
    schema = db.collection("meta").document("schema").get()
    return {
        "project_id": default_project_id(),
        "firestore": "ok",
        "counters_exists": str(counters.exists),
        "schema_exists": str(schema.exists),
    }
