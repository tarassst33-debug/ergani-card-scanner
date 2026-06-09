"""Firestore store for app users, companies, and Ergani credentials (demo UI)."""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from firebase_admin import firestore
from werkzeug.security import check_password_hash, generate_password_hash

from firebase_db import get_firestore

USERS_COLLECTION = "app_users"
COMPANIES_COLLECTION = "companies"
SHIFT_GRIDS_COLLECTION = "shift_grids"
COMPANY_BRANCHES_COLLECTION = "company_branches"
COMPANY_EMPLOYEES_COLLECTION = "company_employees"
SUBMISSIONS_COLLECTION = "submissions"
CARD_PUNCHES_COLLECTION = "card_punches"
COUNTERS_DOC = ("meta", "counters")
SCHEMA_DOC = ("meta", "schema")


@dataclass
class AppUser:
    id: int
    username: str
    role: str
    active: bool


@dataclass
class Company:
    id: int
    name: str
    ergani_username: str
    base_url: str
    user_type: str
    notes: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fernet(secret: str):
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_xor_legacy(plain: str, secret: str) -> str:
    key = hashlib.sha256(secret.encode()).digest()
    data = plain.encode("utf-8")
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.urlsafe_b64encode(xored).decode("ascii")


def _decrypt_xor_legacy(token: str, secret: str) -> str:
    key = hashlib.sha256(secret.encode()).digest()
    data = base64.urlsafe_b64decode(token.encode("ascii"))
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data)).decode("utf-8")


def _encrypt(plain: str, secret: str) -> str:
    return "v2:" + _fernet(secret).encrypt(plain.encode("utf-8")).decode("ascii")


def _decrypt(token: str, secret: str) -> str:
    if token.startswith("v2:"):
        return _fernet(secret).decrypt(token[3:].encode("ascii")).decode("utf-8")
    return _decrypt_xor_legacy(token, secret)


def _db():
    return get_firestore()


def _user_ref(user_id: int):
    return _db().collection(USERS_COLLECTION).document(str(user_id))


def _company_ref(company_id: int):
    return _db().collection(COMPANIES_COLLECTION).document(str(company_id))


def _counters_ref():
    return _db().collection(COUNTERS_DOC[0]).document(COUNTERS_DOC[1])


def _schema_ref():
    return _db().collection(SCHEMA_DOC[0]).document(SCHEMA_DOC[1])


def _shift_grid_doc_id(company_id: int, branch_number: int = 0) -> str:
    return f"{company_id}_{int(branch_number)}"


def _shift_grid_ref(company_id: int, branch_number: int = 0):
    return _db().collection(SHIFT_GRIDS_COLLECTION).document(
        _shift_grid_doc_id(company_id, branch_number)
    )


def _company_branches_ref(company_id: int):
    return _db().collection(COMPANY_BRANCHES_COLLECTION).document(str(company_id))


def _company_employees_ref(company_id: int):
    return _db().collection(COMPANY_EMPLOYEES_COLLECTION).document(str(company_id))


def ensure_firestore_schema() -> None:
    """Create meta documents describing collections (idempotent)."""
    _counters_ref().set({"users": 0, "companies": 0}, merge=True)
    _schema_ref().set(
        {
            "version": 1,
            "collections": {
                "app_users": "Λογαριασμοί εφαρμογής",
                "companies": "Εταιρείες + κρυπτογραφημένοι κωδικοί Ergani",
                "shift_grids": "Πρόγραμμα βαρέων ανά εταιρεία/υποκατάστημα",
                "company_branches": "Υποκαταστήματα (μαγαζιά) ανά εταιρεία",
                "company_employees": "Εργαζόμενοι ανά εταιρεία (από Ergani)",
                "submissions": "Ιστορικό υποβολών (μελλοντικό)",
                "meta": "Μετρητές ids και schema",
            },
            "updated_at": _now(),
        },
        merge=True,
    )


def _allocate_id(field: str) -> int:
    ref = _counters_ref()

    @firestore.transactional
    def _txn(transaction):
        snap = ref.get(transaction=transaction)
        data = snap.to_dict() if snap.exists else {}
        new_id = int(data.get(field, 0)) + 1
        transaction.set(ref, {field: new_id}, merge=True)
        return new_id

    return _txn(_db().transaction())


def _user_from_doc(doc_id: str, data: dict[str, Any]) -> AppUser:
    return AppUser(
        id=int(data.get("id", doc_id)),
        username=data["username"],
        role=data.get("role", "user"),
        active=bool(data.get("active", True)),
    )


def _find_user_by_username(username: str) -> tuple[str, dict[str, Any]] | None:
    normalized = username.strip()
    if not normalized:
        return None
    for doc in (
        _db()
        .collection(USERS_COLLECTION)
        .where("username", "==", normalized)
        .limit(1)
        .stream()
    ):
        return doc.id, doc.to_dict() or {}
    target = normalized.casefold()
    for doc in _db().collection(USERS_COLLECTION).stream():
        data = doc.to_dict() or {}
        if (data.get("username") or "").strip().casefold() == target:
            return doc.id, data
    return None


def sync_bootstrap_admin_from_env() -> None:
    """Ενημέρωση hash admin από env (τοπική χρήση — ERGANI_UI_SYNC_ADMIN_PASSWORD=1)."""
    if os.environ.get("ERGANI_UI_SYNC_ADMIN_PASSWORD", "").strip() not in {
        "1",
        "true",
        "yes",
    }:
        return
    admin_user = os.environ.get("ERGANI_UI_ADMIN_USER", "").strip()
    admin_pass = os.environ.get("ERGANI_UI_ADMIN_PASSWORD", "").strip()
    if not admin_user or len(admin_pass) < 12:
        return
    found = _find_user_by_username(admin_user)
    if not found:
        return
    doc_id, data = found
    user_id = int(data.get("id", doc_id))
    _user_ref(user_id).update(
        {
            "password_hash": generate_password_hash(
                admin_pass, method="pbkdf2:sha256"
            ),
        }
    )


def init_db(secret_key: str) -> None:
    del secret_key
    ensure_firestore_schema()
    users = list(_db().collection(USERS_COLLECTION).limit(1).stream())
    if users:
        sync_bootstrap_admin_from_env()
        return
    admin_user = os.environ.get("ERGANI_UI_ADMIN_USER", "").strip()
    admin_pass = os.environ.get("ERGANI_UI_ADMIN_PASSWORD", "").strip()
    if not admin_user or len(admin_pass) < 12:
        raise RuntimeError(
            "Άδεια Firestore: όρισε ERGANI_UI_ADMIN_USER και ERGANI_UI_ADMIN_PASSWORD "
            "(τουλάχιστον 12 χαρακτήρες)."
        )
    user_id = _allocate_id("users")
    _user_ref(user_id).set(
        {
            "id": user_id,
            "username": admin_user,
            "password_hash": generate_password_hash(admin_pass, method="pbkdf2:sha256"),
            "role": "admin",
            "active": True,
            "company_ids": [],
            "created_at": _now(),
        }
    )


def authenticate_user(username: str, password: str) -> AppUser | None:
    if not password:
        return None
    found = _find_user_by_username(username)
    if not found:
        return None
    doc_id, data = found
    if not data.get("active", True):
        return None
    stored_hash = data.get("password_hash")
    if not stored_hash:
        return None
    if not check_password_hash(stored_hash, password):
        return None
    return _user_from_doc(doc_id, data)


def list_users() -> list[dict[str, Any]]:
    result = []
    for doc in _db().collection(USERS_COLLECTION).stream():
        data = doc.to_dict() or {}
        company_ids = [int(x) for x in data.get("company_ids") or []]
        result.append(
            {
                "id": int(data.get("id", doc.id)),
                "username": data["username"],
                "role": data.get("role", "user"),
                "active": bool(data.get("active", True)),
                "created_at": data.get("created_at", ""),
                "company_ids": sorted(company_ids),
            }
        )
    return sorted(result, key=lambda u: u["username"].lower())


def create_user(
    username: str,
    password: str,
    role: str,
    company_ids: list[int],
) -> int:
    if len((password or "").strip()) < 4:
        raise ValueError("Ο κωδικός πρέπει να έχει τουλάχιστον 4 χαρακτήρες.")
    if _find_user_by_username(username):
        raise ValueError("Υπάρχει ήδη χρήστης με αυτό το όνομα.")
    role = role if role in {"admin", "user"} else "user"
    user_id = _allocate_id("users")
    _user_ref(user_id).set(
        {
            "id": user_id,
            "username": username.strip(),
            "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
            "role": role,
            "active": True,
            "company_ids": [int(c) for c in company_ids],
            "created_at": _now(),
        }
    )
    return user_id


def update_user(
    user_id: int,
    *,
    password: str | None = None,
    role: str | None = None,
    active: bool | None = None,
    company_ids: list[int] | None = None,
) -> None:
    ref = _user_ref(user_id)
    snap = ref.get()
    if not snap.exists:
        return
    updates: dict[str, Any] = {}
    if password:
        updates["password_hash"] = generate_password_hash(password, method="pbkdf2:sha256")
    if role in {"admin", "user"}:
        updates["role"] = role
    if active is not None:
        updates["active"] = active
    if company_ids is not None:
        updates["company_ids"] = [int(c) for c in company_ids]
    if updates:
        ref.update(updates)


def delete_user(user_id: int) -> None:
    _user_ref(user_id).delete()


def list_companies(secret_key: str, *, include_secrets: bool = False) -> list[dict[str, Any]]:
    items = []
    for doc in _db().collection(COMPANIES_COLLECTION).stream():
        row = doc.to_dict() or {}
        item = {
            "id": int(row.get("id", doc.id)),
            "name": row["name"],
            "ergani_username": row["ergani_username"],
            "base_url": row["base_url"],
            "user_type": row.get("user_type", "02"),
            "notes": row.get("notes", ""),
            "created_at": row.get("created_at", ""),
            "has_password": bool(row.get("ergani_password_enc")),
        }
        if include_secrets and row.get("ergani_password_enc"):
            item["ergani_password"] = _decrypt(row["ergani_password_enc"], secret_key)
        items.append(item)
    return sorted(items, key=lambda c: c["name"].lower())


def get_company(company_id: int, secret_key: str) -> dict[str, Any] | None:
    snap = _company_ref(company_id).get()
    if not snap.exists:
        return None
    row = snap.to_dict() or {}
    enc = row.get("ergani_password_enc")
    if not enc:
        return None
    return {
        "id": int(row.get("id", snap.id)),
        "name": row["name"],
        "ergani_username": row["ergani_username"],
        "ergani_password": _decrypt(enc, secret_key),
        "base_url": row["base_url"],
        "user_type": row.get("user_type", "02"),
        "notes": row.get("notes", ""),
    }


def create_company(
    secret_key: str,
    *,
    name: str,
    ergani_username: str,
    ergani_password: str,
    base_url: str,
    user_type: str,
    notes: str = "",
) -> int:
    company_id = _allocate_id("companies")
    _company_ref(company_id).set(
        {
            "id": company_id,
            "name": name.strip(),
            "ergani_username": ergani_username.strip(),
            "ergani_password_enc": _encrypt(ergani_password, secret_key),
            "base_url": base_url.strip(),
            "user_type": user_type,
            "notes": notes.strip(),
            "created_at": _now(),
        }
    )
    return company_id


def update_company(
    company_id: int,
    secret_key: str,
    *,
    name: str | None = None,
    ergani_username: str | None = None,
    ergani_password: str | None = None,
    base_url: str | None = None,
    user_type: str | None = None,
    notes: str | None = None,
) -> None:
    ref = _company_ref(company_id)
    snap = ref.get()
    if not snap.exists:
        return
    updates: dict[str, Any] = {}
    if name is not None:
        updates["name"] = name.strip()
    if ergani_username is not None:
        updates["ergani_username"] = ergani_username.strip()
    if ergani_password:
        updates["ergani_password_enc"] = _encrypt(ergani_password, secret_key)
    if base_url is not None:
        updates["base_url"] = base_url.strip()
    if user_type is not None:
        updates["user_type"] = user_type
    if notes is not None:
        updates["notes"] = notes.strip()
    if updates:
        ref.update(updates)


def delete_company(company_id: int) -> None:
    _company_ref(company_id).delete()
    _company_branches_ref(company_id).delete()
    for doc in _db().collection(SHIFT_GRIDS_COLLECTION).stream():
        data = doc.to_dict() or {}
        if int(data.get("company_id", -1)) == company_id:
            doc.reference.delete()
        elif doc.id == str(company_id):
            doc.reference.delete()
    _company_employees_ref(company_id).delete()
    for doc in _db().collection(USERS_COLLECTION).stream():
        data = doc.to_dict() or {}
        ids = [int(x) for x in data.get("company_ids") or []]
        if company_id in ids:
            doc.reference.update(
                {"company_ids": [x for x in ids if x != company_id]}
            )


def user_company_ids(user_id: int) -> list[int]:
    snap = _user_ref(user_id).get()
    if not snap.exists:
        return []
    data = snap.to_dict() or {}
    return sorted(int(x) for x in data.get("company_ids") or [])


def list_companies_for_user(user_id: int, role: str) -> list[dict[str, Any]]:
    if role == "admin":
        return [
            {
                "id": c["id"],
                "name": c["name"],
                "ergani_username": c["ergani_username"],
                "base_url": c["base_url"],
                "user_type": c["user_type"],
                "notes": c.get("notes", ""),
            }
            for c in list_companies("", include_secrets=False)
        ]
    allowed = set(user_company_ids(user_id))
    if not allowed:
        return []
    out = []
    for cid in sorted(allowed):
        snap = _company_ref(cid).get()
        if not snap.exists:
            continue
        row = snap.to_dict() or {}
        out.append(
            {
                "id": int(row.get("id", snap.id)),
                "name": row["name"],
                "ergani_username": row["ergani_username"],
                "base_url": row["base_url"],
                "user_type": row.get("user_type", "02"),
                "notes": row.get("notes", ""),
            }
        )
    return sorted(out, key=lambda c: c["name"].lower())


def user_can_access_company(user_id: int, role: str, company_id: int) -> bool:
    if role == "admin":
        return _company_ref(company_id).get().exists
    return company_id in user_company_ids(user_id)


def get_company_meta(company_id: int) -> dict[str, Any]:
    snap = _company_ref(company_id).get()
    if not snap.exists:
        return {}
    return snap.to_dict() or {}


def company_requires_boss_pin(company_id: int) -> bool:
    meta = get_company_meta(company_id)
    return bool((meta.get("boss_access_pin_hash") or "").strip())


def verify_company_boss_pin(company_id: int, pin: str) -> bool:
    meta = get_company_meta(company_id)
    pin_hash = (meta.get("boss_access_pin_hash") or "").strip()
    if not pin_hash:
        return True
    return check_password_hash(pin_hash, (pin or "").strip())


def set_company_boss_pin(company_id: int, pin: str | None) -> None:
    ref = _company_ref(company_id)
    if not pin or not pin.strip():
        ref.update({"boss_access_pin_hash": firestore.DELETE_FIELD})
        return
    ref.update(
        {
            "boss_access_pin_hash": generate_password_hash(
                pin.strip(), method="pbkdf2:sha256"
            )
        }
    )


def normalize_branch_row(row: dict[str, Any]) -> dict[str, Any]:
    try:
        branch_number = int(row.get("branch_number", 0))
    except (TypeError, ValueError):
        branch_number = 0
    name = (row.get("name") or row.get("label") or "").strip()
    address = (row.get("address") or "").strip()
    return {
        "branch_number": branch_number,
        "name": name or f"Υποκατάστημα #{branch_number}",
        "address": address,
        "active": bool(row.get("active", True)),
    }


def get_company_branches(company_id: int) -> list[dict[str, Any]]:
    snap = _company_branches_ref(company_id).get()
    if not snap.exists:
        return []
    data = snap.to_dict() or {}
    rows = data.get("branches") or []
    out: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = normalize_branch_row(raw)
        if row["active"]:
            out.append(row)
    return sorted(out, key=lambda r: r["branch_number"])


def save_company_branches(
    company_id: int,
    branches: list[dict[str, Any]],
    *,
    updated_by: str = "",
) -> None:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw in branches:
        if not isinstance(raw, dict):
            continue
        row = normalize_branch_row(raw)
        if row["branch_number"] in seen:
            continue
        seen.add(row["branch_number"])
        rows.append(row)
    _company_branches_ref(company_id).set(
        {
            "company_id": company_id,
            "branches": sorted(rows, key=lambda r: r["branch_number"]),
            "updated_at": _now(),
            "updated_by": updated_by,
        },
        merge=True,
    )


def ensure_default_company_branch(company_id: int, company_name: str) -> None:
    if get_company_branches(company_id):
        return
    save_company_branches(
        company_id,
        [
            {
                "branch_number": 0,
                "name": company_name,
                "address": "",
                "active": True,
            }
        ],
    )


def get_shift_grid(company_id: int, branch_number: int = 0) -> dict[str, Any] | None:
    snap = _shift_grid_ref(company_id, branch_number).get()
    if not snap.exists and branch_number == 0:
        legacy = _db().collection(SHIFT_GRIDS_COLLECTION).document(str(company_id)).get()
        if legacy.exists:
            snap = legacy
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    grid = data.get("grid")
    if not isinstance(grid, dict):
        return None
    return grid


def save_shift_grid(
    company_id: int,
    grid: dict[str, Any],
    *,
    branch_number: int = 0,
    updated_by: str = "",
) -> None:
    _shift_grid_ref(company_id, branch_number).set(
        {
            "company_id": company_id,
            "branch_number": int(branch_number),
            "grid": grid,
            "updated_at": _now(),
            "updated_by": updated_by,
        },
        merge=True,
    )


def normalize_employee_row(employee: dict[str, Any]) -> dict[str, Any]:
    afm = (
        employee.get("afm")
        or employee.get("tax_identification_number")
        or ""
    ).strip()
    return {
        "afm": afm,
        "first_name": (employee.get("first_name") or "").strip(),
        "last_name": (employee.get("last_name") or "").strip(),
        "father_name": (employee.get("father_name") or "").strip(),
        "branch_number": employee.get("branch_number"),
        "date_from": employee.get("date_from"),
        "date_to": employee.get("date_to"),
        "status_description": employee.get("status_description"),
    }


def get_company_employees(company_id: int) -> dict[str, Any]:
    snap = _company_employees_ref(company_id).get()
    if not snap.exists:
        return {"employees": [], "synced_at": None}
    data = snap.to_dict() or {}
    rows = data.get("employees") or []
    normalized = [normalize_employee_row(r) for r in rows if isinstance(r, dict)]
    normalized = [r for r in normalized if r["afm"]]
    return {
        "employees": sorted(
            normalized,
            key=lambda r: (r.get("last_name") or "", r.get("first_name") or ""),
        ),
        "synced_at": data.get("synced_at"),
    }


def save_company_employees(
    company_id: int,
    employees: list[dict[str, Any]],
    *,
    synced_by: str = "",
) -> None:
    rows = []
    seen: set[str] = set()
    for raw in employees:
        if not isinstance(raw, dict):
            continue
        row = normalize_employee_row(raw)
        if not row["afm"] or row["afm"] in seen:
            continue
        seen.add(row["afm"])
        rows.append(row)
    rows.sort(key=lambda r: (r.get("last_name") or "", r.get("first_name") or ""))
    _company_employees_ref(company_id).set(
        {
            "company_id": company_id,
            "employees": rows,
            "count": len(rows),
            "synced_at": _now(),
            "synced_by": synced_by,
        },
        merge=True,
    )


def save_submission(
    company_id: int,
    *,
    submission_type: str,
    payload_summary: dict[str, Any],
    protocol: str | None = None,
    submitted_by: str = "",
) -> str:
    ref = _db().collection(SUBMISSIONS_COLLECTION).document()
    ref.set(
        {
            "company_id": company_id,
            "type": submission_type,
            "protocol": protocol or "",
            "summary": payload_summary,
            "submitted_by": submitted_by,
            "created_at": _now(),
        }
    )
    return ref.id


def _card_punches_ref(company_id: int):
    return _db().collection(CARD_PUNCHES_COLLECTION).document(str(company_id))


def get_card_punches_meta(company_id: int) -> dict[str, Any]:
    snap = _card_punches_ref(company_id).get()
    if not snap.exists:
        return {}
    data = snap.to_dict() or {}
    return {
        "synced_at": data.get("synced_at"),
        "service_code": data.get("service_code"),
    }


def list_card_punches(
    company_id: int,
    *,
    date_from: str = "",
    date_to: str = "",
) -> list[dict[str, Any]]:
    snap = _card_punches_ref(company_id).get()
    if not snap.exists:
        return []
    data = snap.to_dict() or {}
    punches = data.get("punches") or []
    if not isinstance(punches, list):
        return []

    def in_range(item: dict[str, Any]) -> bool:
        ref = (item.get("reference_date") or item.get("movement_date") or "")[:10]
        movement = (item.get("movement_datetime") or "")[:10]
        day = ref or movement
        if not day:
            return True
        if date_from and day < date_from:
            return False
        if date_to and day > date_to:
            return False
        return True

    rows = [p for p in punches if isinstance(p, dict) and in_range(p)]
    rows.sort(
        key=lambda r: (
            r.get("reference_date") or "",
            r.get("movement_datetime") or "",
        ),
        reverse=True,
    )
    return rows


def save_card_punches(
    company_id: int,
    punches: list[dict[str, Any]],
    *,
    synced_at: str | None = None,
    service_code: str = "",
    synced_by: str = "",
    merge: bool = False,
) -> None:
    ref = _card_punches_ref(company_id)
    existing: list[dict[str, Any]] = []
    if merge:
        snap = ref.get()
        if snap.exists:
            raw = (snap.to_dict() or {}).get("punches") or []
            if isinstance(raw, list):
                existing = [p for p in raw if isinstance(p, dict)]

    seen = {
        (
            str(p.get("afm") or ""),
            str(p.get("movement_datetime") or ""),
            str(p.get("movement_type") or ""),
        )
        for p in existing
    }
    merged = list(existing)
    for punch in punches:
        key = (
            str(punch.get("afm") or ""),
            str(punch.get("movement_datetime") or ""),
            str(punch.get("movement_type") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(punch)

    ref.set(
        {
            "company_id": company_id,
            "punches": merged,
            "count": len(merged),
            "synced_at": synced_at or _now(),
            "service_code": service_code,
            "synced_by": synced_by,
        },
        merge=True,
    )


def append_card_punches(
    company_id: int,
    punches: list[dict[str, Any]],
    *,
    submitted_by: str = "",
) -> None:
    for punch in punches:
        punch.setdefault("source", "app")
        punch.setdefault("recorded_at", _now())
        if submitted_by:
            punch.setdefault("submitted_by", submitted_by)
    save_card_punches(company_id, punches, merge=True)
