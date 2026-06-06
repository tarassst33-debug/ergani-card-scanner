"""Local web UI for the Ergani Python SDK (development / demo only)."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, redirect, request, session, send_from_directory

from ergani.client import ErganiClient
from ergani.utils import normalize_base_url
from ergani.exceptions import APIError, AuthenticationError, Error
from ergani.models import (
    BusinessBranch,
    CompanyDailySchedule,
    CompanyOvertime,
    CompanyWeeklySchedule,
    CompanyWorkCard,
    Employee,
    EmployeeDailySchedule,
    EmployeeWeeklySchedule,
    EmployerDetails,
    Overtime,
    WorkCard,
    WorkCardMovement,
    WorkdayDetails,
)

UI_DIR = Path(__file__).resolve().parent
STATIC_DIR = UI_DIR / "static"
DEFAULT_BASE_URL = "https://eservices.yeka.gr/WebservicesAPI/Api"
TRIAL_BASE_URL = "https://trialeservices.yeka.gr/WebservicesAPI/Api"

if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))

from security import (  # noqa: E402
    check_login_rate_limit,
    client_ip,
    configure_app,
    manual_connect_enabled,
    require_ui_secret,
    username_allowed,
)
from firebase_db import ping_firestore  # noqa: E402
from kiosk import (  # noqa: E402
    kiosk_allowed_company_ids,
    kiosk_company_config,
    parse_qr_employee_afm,
    resolve_kiosk_company_id,
    submit_kiosk_punch,
    verify_kiosk_request,
)
from store import (  # noqa: E402
    authenticate_user,
    create_company,
    create_user,
    delete_company,
    delete_user,
    get_company,
    get_company_employees,
    get_shift_grid,
    init_db,
    normalize_employee_row,
    save_company_employees,
    list_companies,
    list_companies_for_user,
    list_users,
    save_shift_grid,
    append_card_punches,
    get_card_punches_meta,
    list_card_punches,
    save_card_punches,
    save_submission,
    update_company,
    update_user,
    user_can_access_company,
)

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
app.secret_key = require_ui_secret()
configure_app(app)

try:
    init_db(app.secret_key)
except RuntimeError as exc:
    raise SystemExit(str(exc)) from exc


def _ergani_session_keys() -> tuple[str, ...]:
    return ("username", "base_url", "user_type", "company_id", "company_name")


def _clear_ergani_session() -> None:
    for key in _ergani_session_keys():
        session.pop(key, None)


def _clear_app_session() -> None:
    for key in ("app_user_id", "app_username", "app_role", "app_authenticated"):
        session.pop(key, None)


def _is_app_authenticated() -> bool:
    return bool(session.get("app_authenticated") and session.get("app_user_id"))


def _require_app_user(*, admin_only: bool = False):
    if not _is_app_authenticated():
        _clear_app_session()
        return None, (jsonify({"error": "Συνδεθείτε στο σύστημα."}), 401)
    user_id = session.get("app_user_id")
    if not user_id:
        return None, (jsonify({"error": "Συνδεθείτε στο σύστημα."}), 401)
    role = session.get("app_role") or "user"
    if admin_only and role != "admin":
        return None, (jsonify({"error": "Απαιτείται λογαριασμός admin."}), 403)
    return {"id": user_id, "username": session.get("app_username"), "role": role}, None


def _client() -> ErganiClient | None:
    company_id = session.get("company_id")
    if not company_id:
        return None
    company = get_company(int(company_id), app.secret_key)
    if not company:
        return None
    return ErganiClient(
        company["ergani_username"],
        company["ergani_password"],
        session.get("base_url") or company.get("base_url") or DEFAULT_BASE_URL,
        user_type=session.get("user_type") or company.get("user_type") or "02",
    )


def _require_client():
    client = _client()
    if client is None:
        return None, (jsonify({"error": "Δεν είστε συνδεδεμένοι."}), 401)
    return client, None


def _require_app_and_client():
    _, err = _require_app_user()
    if err:
        return None, err
    return _require_client()


def _format_error_message(exc: Exception) -> str:
    if isinstance(exc, AuthenticationError):
        raw = exc.message
        if isinstance(raw, dict):
            raw = str(raw)
        text = (raw or "").strip() if isinstance(raw, str) else ""
        if text and not text.startswith("Error message:"):
            return text
        if exc.response is not None:
            status = exc.response.status_code
            body = (exc.response.text or "").strip().replace("\n", " ")[:280]
            if status == 401:
                base = (
                    "Αποτυχία σύνδεσης (401). Έλεγξε κωδικό και τύπο χρήστη: "
                    "01 = εξωτερικό σύστημα (π.χ. ika…), "
                    "02 = κωδικοί σύνδεσης Ergani portal, "
                    "03 = οικοδομικά έργα ΕΦΚΑ."
                )
                if body and body not in base:
                    return f"{body} ({base})"
                return base
            if status == 404:
                hint = (
                    f"Το endpoint δεν βρέθηκε (404). Το trial API ({TRIAL_BASE_URL}) "
                    "δεν είναι διαθέσιμο αυτή τη στιγμή. "
                    f"Δοκιμάστε production: {DEFAULT_BASE_URL}"
                )
                return hint if "trialeservices" in (exc.response.url or "") else (
                    f"Σφάλμα HTTP 404. {body}".strip() if body else hint
                )
            return f"Σφάλμα HTTP {status}. {body}".strip() if body else f"Σφάλμα HTTP {status}."
        return "Αποτυχία ταυτοποίησης στο Ergani API."

    if isinstance(exc, APIError):
        raw = exc.message
        text = (raw or "").strip() if isinstance(raw, str) else str(raw or "")
        if text and "Error message:" not in text:
            return text
        if exc.response is not None:
            status = exc.response.status_code
            body = (exc.response.text or "").strip().replace("\n", " ")[:280]
            return f"Σφάλμα HTTP {status}. {body}".strip() if body else f"Σφάλμα HTTP {status}."

    if isinstance(exc, Error):
        text = str(exc).strip()
        if text and not text.endswith("Error message:") and text != "Error message:":
            return text

    return str(exc) or "Άγνωστο σφάλμα."


def _error_response(exc: Exception, status: int = 400):
    if isinstance(exc, AuthenticationError):
        status = 401
    elif isinstance(exc, APIError):
        status = exc.response.status_code if exc.response is not None else 502
    message = _format_error_message(exc)
    return jsonify({"error": message}), status


def _employer_dict(details: EmployerDetails) -> dict[str, Any]:
    return {
        "employer_id": details.employer_id,
        "employer_tax_identification_number": details.employer_tax_identification_number,
        "name": details.name,
        "distinctive_title": details.distinctive_title,
        "employer_registry_number": details.employer_registry_number,
        "is_in_card_sector": details.is_in_card_sector,
    }


def _employee_dict(employee: Employee) -> dict[str, Any]:
    return {
        "tax_identification_number": employee.tax_identification_number,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "father_name": employee.father_name,
        "identity_number": employee.identity_number,
        "social_security_number": employee.social_security_number,
        "profession_code": employee.profession_code,
        "branch_number": employee.branch_number,
        "date_from": employee.date_from,
        "date_to": employee.date_to,
        "status_description": employee.status_description,
    }


def _branch_dict(branch: BusinessBranch) -> dict[str, Any]:
    return {
        "branch_number": branch.branch_number,
        "address": branch.address,
        "sepe_service_code": branch.sepe_service_code,
        "oaed_service_code": branch.oaed_service_code,
        "business_branch_activity_code": branch.business_branch_activity_code,
        "kallikratis_municipal_code": branch.kallikratis_municipal_code,
        "status_description": branch.status_description,
    }


def _submission_list(results: list) -> list[dict[str, Any]]:
    formatted = []
    for item in results:
        submitted = item.get("sumbmission_date") or item.get("submission_date")
        formatted.append(
            {
                "submission_id": item.get("submission_id"),
                "protocol": item.get("protocol"),
                "submission_date": submitted.isoformat() if submitted else None,
            }
        )
    return formatted


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_time(value: str) -> time:
    parts = value.split(":")
    return time(int(parts[0]), int(parts[1]))


def _movement_type_label(movement_type: str | None) -> str:
    if movement_type == "ARRIVAL":
        return "Προσέλευση"
    if movement_type == "DEPARTURE":
        return "Αποχώρηση"
    return "—"


def _work_card_movement_dict(movement: WorkCardMovement) -> dict[str, Any]:
    ref = movement.reference_date
    movement_dt = movement.movement_datetime or ""
    movement_date = ref
    movement_time = ""
    if movement_dt:
        try:
            parsed = datetime.fromisoformat(movement_dt.replace("Z", "+00:00"))
            movement_date = parsed.date().isoformat()
            movement_time = parsed.strftime("%H:%M")
        except ValueError:
            if "T" in movement_dt:
                movement_date = movement_dt.split("T", 1)[0]
                movement_time = movement_dt.split("T", 1)[1][:5]
    full_name = " ".join(
        part
        for part in (movement.employee_last_name, movement.employee_first_name)
        if part
    ).strip()
    return {
        "afm": movement.employee_tax_identification_number,
        "first_name": movement.employee_first_name,
        "last_name": movement.employee_last_name,
        "full_name": full_name or "—",
        "movement_type": movement.movement_type,
        "movement_label": _movement_type_label(movement.movement_type),
        "reference_date": ref,
        "movement_date": movement_date,
        "movement_time": movement_time,
        "movement_datetime": movement_dt,
        "branch_number": movement.branch_number,
        "source": "ergani",
    }


def _entry_to_punch_dict(entry: dict[str, Any], branch_number: int) -> dict[str, Any]:
    movement_dt = _parse_datetime(entry["movement_datetime"])
    ref_date = _parse_date(entry.get("submission_date")) or movement_dt.date()
    return {
        "afm": (entry.get("employee_afm") or "").strip(),
        "first_name": (entry.get("first_name") or "").strip(),
        "last_name": (entry.get("last_name") or "").strip(),
        "full_name": " ".join(
            part
            for part in (entry.get("last_name"), entry.get("first_name"))
            if part
        ).strip(),
        "movement_type": entry.get("movement_type"),
        "movement_label": _movement_type_label(entry.get("movement_type")),
        "reference_date": ref_date.isoformat(),
        "movement_date": movement_dt.date().isoformat(),
        "movement_time": movement_dt.strftime("%H:%M"),
        "movement_datetime": movement_dt.isoformat(),
        "branch_number": branch_number,
        "source": "app",
    }


def _index_html() -> str:
    import json

    from kiosk import kiosk_allowed_company_ids, kiosk_device_key

    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    device_key = kiosk_device_key()
    company_items = []
    for company_id in kiosk_allowed_company_ids():
        company = get_company(company_id, app.secret_key)
        if company:
            company_items.append(
                {"id": company_id, "name": company.get("name") or ""}
            )
    bootstrap = json.dumps(
        {"companies": company_items, "kiosk_ready": bool(device_key)},
        ensure_ascii=False,
    )
    html = html.replace("__KIOSK_KEY__", device_key)
    return html.replace("__KIOSK_BOOTSTRAP__", bootstrap)


@app.get("/")
def index():
    return _index_html(), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.get("/kiosk")
def kiosk_page():
    """Παλιό URL — ίδια εφαρμογή."""
    return redirect("/", code=302)


def _resolve_base_url(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return DEFAULT_BASE_URL
    try:
        return normalize_base_url(raw)
    except ValueError:
        return DEFAULT_BASE_URL


def _normalize_user_type(value: str | None) -> str:
    normalized = (value or "02").strip()
    if normalized not in {"01", "02", "03"}:
        return "02"
    return normalized


def _establish_session_from_company(company: dict[str, Any]):
    base_url = _resolve_base_url(company.get("base_url"))
    user_type = _normalize_user_type(company.get("user_type"))
    client = ErganiClient(
        company["ergani_username"],
        company["ergani_password"],
        base_url,
        user_type=user_type,
    )
    employer = client.get_employer_details()
    session["username"] = company["ergani_username"]
    session["base_url"] = base_url
    session["user_type"] = user_type
    session.pop("password", None)
    return employer


@app.get("/api/auth/status")
def auth_status():
    if not _is_app_authenticated():
        if session.get("app_user_id") or session.get("app_username"):
            _clear_app_session()
            _clear_ergani_session()
        return jsonify(
            {
                "app_user": None,
                "app_role": None,
                "ergani_connected": False,
                "company": None,
            }
        )

    return jsonify(
        {
            "app_user": session.get("app_username"),
            "app_role": session.get("app_role"),
            "ergani_connected": bool(session.get("company_id")),
            "company": (
                {
                    "id": session.get("company_id"),
                    "name": session.get("company_name"),
                }
                if session.get("company_id")
                else None
            ),
        }
    )


@app.post("/api/auth/login")
def app_login():
    blocked = check_login_rate_limit(client_ip(request))
    if blocked:
        return jsonify({"error": blocked}), 429

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "Συμπλήρωσε όνομα και κωδικό."}), 400

    if not username_allowed(username):
        return jsonify({"error": "Λάθος όνομα ή κωδικός."}), 401

    user = authenticate_user(username, password)
    if not user:
        return jsonify({"error": "Λάθος όνομα ή κωδικός."}), 401

    _clear_ergani_session()
    session["app_user_id"] = user.id
    session["app_username"] = user.username
    session["app_role"] = user.role
    session["app_authenticated"] = True

    companies = list_companies_for_user(user.id, user.role)
    return jsonify(
        {
            "app_user": user.username,
            "app_role": user.role,
            "companies": companies,
        }
    )


@app.post("/api/auth/logout")
def app_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/auth/companies")
def auth_companies():
    user, err = _require_app_user()
    if err:
        return err
    companies = list_companies_for_user(user["id"], user["role"])
    return jsonify({"companies": companies})


@app.post("/api/auth/select-company")
def auth_select_company():
    user, err = _require_app_user()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    company_id = data.get("company_id")
    if company_id is None:
        return jsonify({"error": "Επίλεξε εταιρεία."}), 400
    try:
        company_id = int(company_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Μη έγκυρη εταιρεία."}), 400

    if not user_can_access_company(user["id"], user["role"], company_id):
        return jsonify({"error": "Δεν έχεις πρόσβαση σε αυτή την εταιρεία."}), 403

    company = get_company(company_id, app.secret_key)
    if not company:
        return jsonify({"error": "Η εταιρεία δεν βρέθηκε."}), 404

    try:
        employer = _establish_session_from_company(company)
    except (AuthenticationError, APIError, ValueError) as exc:
        _clear_ergani_session()
        return _error_response(exc)

    session["company_id"] = company_id
    session["company_name"] = company["name"]

    return jsonify(
        {
            "connected": True,
            "company": {"id": company_id, "name": company["name"]},
            "employer": _employer_dict(employer),
        }
    )


@app.get("/api/admin/firebase-status")
def admin_firebase_status():
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    try:
        return jsonify(ping_firestore())
    except Exception as exc:
        return jsonify({"error": str(exc), "firestore": "error"}), 503


@app.get("/api/admin/users")
def admin_list_users():
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    return jsonify({"users": list_users()})


@app.post("/api/admin/users")
def admin_create_user():
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "user").strip()
    company_ids = data.get("company_ids") or []
    if not username or not password:
        return jsonify({"error": "Συμπληρώστε χρήστη και κωδικό."}), 400
    try:
        company_ids = [int(x) for x in company_ids]
    except (TypeError, ValueError):
        return jsonify({"error": "Μη έγκυρα παραρτήματα εταιρειών."}), 400
    try:
        user_id = create_user(username, password, role, company_ids)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"id": user_id}), 201


@app.put("/api/admin/users/<int:user_id>")
def admin_update_user(user_id: int):
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    company_ids = data.get("company_ids")
    if company_ids is not None:
        try:
            company_ids = [int(x) for x in company_ids]
        except (TypeError, ValueError):
            return jsonify({"error": "Μη έγκυρα παραρτήματα εταιρειών."}), 400
    update_user(
        user_id,
        password=data.get("password") or None,
        role=data.get("role"),
        active=data.get("active"),
        company_ids=company_ids,
    )
    return jsonify({"ok": True})


@app.delete("/api/admin/users/<int:user_id>")
def admin_delete_user(user_id: int):
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    if user_id == session.get("app_user_id"):
        return jsonify({"error": "Δεν μπορείς να διαγράψεις τον τρέχοντα λογαριασμό."}), 400
    delete_user(user_id)
    return jsonify({"ok": True})


@app.get("/api/admin/companies")
def admin_list_companies():
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    return jsonify({"companies": list_companies(app.secret_key)})


@app.post("/api/admin/companies")
def admin_create_company():
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    ergani_username = (data.get("ergani_username") or "").strip()
    ergani_password = data.get("ergani_password") or ""
    if not name or not ergani_username or not ergani_password:
        return jsonify({"error": "Συμπληρώστε όνομα, χρήστη και κωδικό Ergani."}), 400
    company_id = create_company(
        app.secret_key,
        name=name,
        ergani_username=ergani_username,
        ergani_password=ergani_password,
        base_url=_resolve_base_url(data.get("base_url")),
        user_type=_normalize_user_type(data.get("user_type")),
        notes=(data.get("notes") or "").strip(),
    )
    return jsonify({"id": company_id}), 201


@app.put("/api/admin/companies/<int:company_id>")
def admin_update_company(company_id: int):
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    update_company(
        company_id,
        app.secret_key,
        name=data.get("name"),
        ergani_username=data.get("ergani_username"),
        ergani_password=data.get("ergani_password") or None,
        base_url=data.get("base_url"),
        user_type=data.get("user_type"),
        notes=data.get("notes"),
    )
    return jsonify({"ok": True})


@app.delete("/api/admin/companies/<int:company_id>")
def admin_delete_company(company_id: int):
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    delete_company(company_id)
    return jsonify({"ok": True})


@app.get("/api/env-defaults")
def env_defaults():
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    if not manual_connect_enabled():
        return jsonify({"error": "Η χειροκίνητη σύνδεση είναι απενεργοποιημένη."}), 403
    return jsonify(
        {
            "username": os.environ.get("ERGANI_USERNAME", ""),
            "base_url": _resolve_base_url(os.environ.get("ERGANI_BASE_URL")),
            "has_password": bool(os.environ.get("ERGANI_PASSWORD")),
            "user_type": _normalize_user_type(os.environ.get("ERGANI_USER_TYPE")),
        }
    )


@app.get("/api/session")
def session_status():
    connected = bool(session.get("company_id"))
    return jsonify(
        {
            "connected": connected,
            "username": session.get("username") if connected else None,
            "base_url": session.get("base_url") if connected else DEFAULT_BASE_URL,
            "app_user": session.get("app_username"),
            "app_role": session.get("app_role"),
            "company": (
                {
                    "id": session.get("company_id"),
                    "name": session.get("company_name"),
                }
                if session.get("company_id")
                else None
            ),
        }
    )


@app.post("/api/session")
def connect():
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    if not manual_connect_enabled():
        return jsonify({"error": "Η χειροκίνητη σύνδεση είναι απενεργοποιημένη."}), 403
    return jsonify({"error": "Χρησιμοποίησε σύνδεση μέσω εταιρείας."}), 403


@app.post("/api/session/from-env")
def connect_from_env():
    _, err = _require_app_user(admin_only=True)
    if err:
        return err
    if not manual_connect_enabled():
        return jsonify({"error": "Η χειροκίνητη σύνδεση είναι απενεργοποιημένη."}), 403
    return jsonify({"error": "Χρησιμοποίησε σύνδεση μέσω εταιρείας."}), 403


@app.delete("/api/session")
def disconnect():
    _clear_ergani_session()
    return jsonify({"connected": False})


@app.get("/api/employer")
def employer():
    client, err = _require_app_and_client()
    if err:
        return err
    try:
        return jsonify({"employer": _employer_dict(client.get_employer_details())})
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


def _session_company_id() -> int | None:
    raw = session.get("company_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@app.get("/api/shift-grid")
def get_shift_grid_route():
    user, err = _require_app_user()
    if err:
        return err
    company_id = _session_company_id()
    if not company_id:
        return jsonify({"error": "Επίλεξε εταιρεία."}), 400
    if not user_can_access_company(user["id"], user["role"], company_id):
        return jsonify({"error": "Δεν έχεις πρόσβαση σε αυτή την εταιρεία."}), 403
    grid = get_shift_grid(company_id)
    return jsonify({"grid": grid, "company_id": company_id})


@app.put("/api/shift-grid")
def put_shift_grid_route():
    user, err = _require_app_user()
    if err:
        return err
    company_id = _session_company_id()
    if not company_id:
        return jsonify({"error": "Επίλεξε εταιρεία."}), 400
    if not user_can_access_company(user["id"], user["role"], company_id):
        return jsonify({"error": "Δεν έχεις πρόσβαση σε αυτή την εταιρεία."}), 403
    data = request.get_json(silent=True) or {}
    grid = data.get("grid")
    if not isinstance(grid, dict):
        return jsonify({"error": "Μη έγκυρο πρόγραμμα."}), 400
    save_shift_grid(
        company_id,
        grid,
        updated_by=user.get("username") or "",
    )
    return jsonify({"ok": True, "company_id": company_id})


@app.get("/api/branches")
def branches():
    client, err = _require_app_and_client()
    if err:
        return err
    try:
        items = [_branch_dict(b) for b in client.get_branch_details()]
        return jsonify({"branches": items})
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


def _fetch_employees_from_ergani(
    client: ErganiClient,
    *,
    branch_number: int | None = None,
    all_branches: bool = False,
) -> list[Employee]:
    seen_afms: set[str] = set()
    collected: list[Employee] = []

    def _add_from_branch(bn: int | None) -> None:
        for employee in client.get_employees(
            bn,
            current_status_only=True,
        ):
            afm = (employee.tax_identification_number or "").strip()
            if not afm or afm in seen_afms:
                continue
            seen_afms.add(afm)
            collected.append(employee)

    if all_branches or branch_number is None:
        for branch in client.get_branch_details():
            _add_from_branch(branch.branch_number)
    else:
        _add_from_branch(branch_number)

    return collected


@app.get("/api/employees/stored")
def employees_stored():
    user, err = _require_app_user()
    if err:
        return err
    company_id = _session_company_id()
    if not company_id:
        return jsonify({"error": "Επίλεξε εταιρεία."}), 400
    if not user_can_access_company(user["id"], user["role"], company_id):
        return jsonify({"error": "Δεν έχεις πρόσβαση σε αυτή την εταιρεία."}), 403
    data = get_company_employees(company_id)
    employees = [
        {
            "tax_identification_number": e["afm"],
            "first_name": e["first_name"],
            "last_name": e["last_name"],
            "father_name": e["father_name"],
            "branch_number": e.get("branch_number"),
            "date_from": e.get("date_from"),
            "date_to": e.get("date_to"),
            "status_description": e.get("status_description"),
        }
        for e in data["employees"]
    ]
    return jsonify(
        {
            "employees": employees,
            "count": len(employees),
            "synced_at": data.get("synced_at"),
            "source": "firestore",
        }
    )


@app.post("/api/employees/sync")
def employees_sync():
    user, err = _require_app_user()
    if err:
        return err
    client, err = _require_app_and_client()
    if err:
        return err
    company_id = _session_company_id()
    if not company_id:
        return jsonify({"error": "Επίλεξε εταιρεία."}), 400
    if not user_can_access_company(user["id"], user["role"], company_id):
        return jsonify({"error": "Δεν έχεις πρόσβαση σε αυτή την εταιρεία."}), 403

    payload = request.get_json(silent=True) or {}
    all_branches = payload.get("all_branches", True)
    branch_number = payload.get("branch_number")
    if branch_number is not None:
        try:
            branch_number = int(branch_number)
            all_branches = False
        except (TypeError, ValueError):
            return jsonify({"error": "Μη έγκυρο παράρτημα."}), 400

    try:
        items = _fetch_employees_from_ergani(
            client,
            branch_number=branch_number,
            all_branches=bool(all_branches),
        )
        rows = [
            normalize_employee_row(_employee_dict(employee)) for employee in items
        ]
        save_company_employees(
            company_id,
            rows,
            synced_by=user.get("username") or "",
        )
        stored = get_company_employees(company_id)
        employees = [
            {
                "tax_identification_number": e["afm"],
                "first_name": e["first_name"],
                "last_name": e["last_name"],
                "father_name": e["father_name"],
                "branch_number": e.get("branch_number"),
                "date_from": e.get("date_from"),
                "date_to": e.get("date_to"),
                "status_description": e.get("status_description"),
            }
            for e in stored["employees"]
        ]
        return jsonify(
            {
                "employees": employees,
                "count": len(employees),
                "synced_at": stored.get("synced_at"),
                "source": "ergani",
            }
        )
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


@app.get("/api/employees")
def employees():
    client, err = _require_app_and_client()
    if err:
        return err

    branch_raw = request.args.get("branch_number")
    branch_number: int | None = None
    if branch_raw is not None and branch_raw != "":
        try:
            branch_number = int(branch_raw)
        except ValueError:
            return jsonify({"error": "Μη έγκυρο Α/Α παραρτήματος."}), 400

    current_status_only = request.args.get("current_status_only", "1").lower() not in {
        "0",
        "false",
        "no",
    }
    include_inactive = request.args.get("include_inactive", "").lower() in {
        "1",
        "true",
        "yes",
    }

    try:
        items = client.get_employees(
            branch_number,
            afm=(request.args.get("afm") or "").strip(),
            identity_number=(request.args.get("identity_number") or "").strip(),
            first_name=(request.args.get("first_name") or "").strip(),
            last_name=(request.args.get("last_name") or "").strip(),
            father_name=(request.args.get("father_name") or "").strip(),
            current_status_only=current_status_only,
            include_inactive=include_inactive,
            search=(request.args.get("search") or "").strip(),
        )
        return jsonify(
            {
                "employees": [_employee_dict(employee) for employee in items],
                "count": len(items),
                "service_code": "EX_BASE_05",
            }
        )
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


@app.get("/api/services")
def services():
    client, err = _require_app_and_client()
    if err:
        return err
    try:
        response = client.get_services_list()
        if response is None:
            return jsonify({"services": None})
        return jsonify({"services": response.json()})
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


@app.get("/api/work-card/punches/hints")
def work_card_punch_service_hints():
    client, err = _require_app_and_client()
    if err:
        return err
    hints: list[dict[str, Any]] = []
    try:
        response = client.get_services_list()
        if response is not None:
            services = response.json()
            if isinstance(services, list):
                for service in services:
                    if not isinstance(service, dict):
                        continue
                    name = str(service.get("name") or "").strip()
                    if not name:
                        continue
                    desc = str(service.get("description") or "")
                    blob = f"{name} {desc}".lower()
                    if any(
                        kw in blob
                        for kw in client._WORK_CARD_SERVICE_KEYWORDS
                    ):
                        hints.append({"name": name, "description": desc})
    except (AuthenticationError, APIError, ValueError) as exc:
        return jsonify({"error": _format_error_message(exc)}), 400
    return jsonify({"services": hints, "env_hint": "ERGANI_WORK_CARD_QUERY_SERVICE"})


@app.get("/api/work-card/punches")
def list_work_card_punches():
    _, err = _require_app_user()
    if err:
        return err
    company_id = _session_company_id()
    if not company_id:
        return jsonify({"error": "Επίλεξε εταιρεία."}), 400

    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()
    punches = list_card_punches(
        company_id, date_from=date_from, date_to=date_to
    )
    return jsonify(
        {
            "punches": punches,
            "count": len(punches),
            **get_card_punches_meta(company_id),
        }
    )


@app.post("/api/work-card/punches/sync")
def sync_work_card_punches():
    client, err = _require_app_and_client()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    date_from_raw = (data.get("date_from") or request.args.get("date_from") or "").strip()
    date_to_raw = (data.get("date_to") or request.args.get("date_to") or "").strip()
    if not date_from_raw or not date_to_raw:
        return jsonify({"error": "Συμπλήρωσε ημερομηνία από και έως."}), 400

    try:
        date_from = _parse_date(date_from_raw)
        date_to = _parse_date(date_to_raw)
    except ValueError:
        return jsonify({"error": "Μη έγκυρες ημερομηνίες."}), 400
    if not date_from or not date_to:
        return jsonify({"error": "Συμπλήρωσε ημερομηνία από και έως."}), 400
    if date_from > date_to:
        return jsonify({"error": "Η «από» πρέπει να είναι πριν ή ίση με την «έως»."}), 400

    branch_raw = data.get("branch_number")
    branch_number: int | None = None
    if branch_raw is not None and branch_raw != "":
        try:
            branch_number = int(branch_raw)
        except ValueError:
            return jsonify({"error": "Μη έγκυρο Α/Α παραρτήματος."}), 400

    service_code = (data.get("service_code") or "").strip()
    employee_afm = (data.get("employee_afm") or "").strip()

    company_id = _session_company_id()
    try:
        movements, used_code = client.get_work_card_movements(
            branch_number=branch_number,
            date_from=date_from,
            date_to=date_to,
            employee_afm=employee_afm,
            service_code=service_code,
        )
    except ValueError as exc:
        cached = (
            list_card_punches(
                company_id, date_from=date_from_raw, date_to=date_to_raw
            )
            if company_id
            else []
        )
        return jsonify(
            {
                "punches": cached,
                "count": len(cached),
                "warning": str(exc),
                "service_code": service_code or None,
                **(get_card_punches_meta(company_id) if company_id else {}),
            }
        ), 422
    except (AuthenticationError, APIError) as exc:
        return _error_response(exc)

    punches = [_work_card_movement_dict(m) for m in movements]
    if company_id:
        save_card_punches(
            company_id,
            punches,
            service_code=used_code,
            synced_by=session.get("app_username") or "",
            merge=True,
        )

    return jsonify(
        {
            "punches": punches,
            "count": len(punches),
            "service_code": used_code,
            "synced_at": datetime.now().astimezone().isoformat(),
        }
    )


@app.post("/api/work-card")
def submit_work_card():
    client, err = _require_app_and_client()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    employer_afm = (data.get("employer_afm") or "").strip()
    branch_number = data.get("branch_number")
    comments = data.get("comments") or ""
    entries = data.get("entries") or []

    if not employer_afm or branch_number is None or not entries:
        return jsonify({"error": "Λείπουν υποχρεωτικά πεδία κάρτας."}), 400

    cards: list[WorkCard] = []
    for index, entry in enumerate(entries, start=1):
        if not (entry.get("employee_afm") or "").strip():
            return jsonify({"error": f"Λείπει ΑΦΜ στη γραμμή {index}."}), 400
        movement_dt = _parse_datetime(entry["movement_datetime"])
        cards.append(
            WorkCard(
                employee_tax_identification_number=entry["employee_afm"].strip(),
                employee_last_name=entry["last_name"].strip(),
                employee_first_name=entry["first_name"].strip(),
                work_card_movement_type=entry["movement_type"],
                work_card_submission_date=_parse_date(entry["submission_date"])
                or movement_dt.date(),
                work_card_movement_datetime=movement_dt,
                late_declaration_justification=entry.get("late_justification"),
            )
        )

    company = CompanyWorkCard(
        employer_tax_identification_number=employer_afm,
        business_branch_number=int(branch_number),
        comments=comments,
        card_details=cards,
    )

    try:
        results = client.submit_work_card([company])
        listed = _submission_list(results)
        company_id = _session_company_id()
        if company_id:
            protocol = listed[0].get("protocol") if listed else None
            save_submission(
                company_id,
                submission_type="work_card",
                payload_summary={
                    "entries": len(entries),
                    "branch_number": branch_number,
                },
                protocol=protocol,
                submitted_by=session.get("app_username") or "",
            )
            append_card_punches(
                company_id,
                [
                    _entry_to_punch_dict(entry, int(branch_number))
                    for entry in entries
                ],
                submitted_by=session.get("app_username") or "",
            )
        return jsonify({"submissions": listed})
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


@app.post("/api/overtime")
def submit_overtime():
    client, err = _require_app_and_client()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    branch = data.get("branch") or {}
    entries = data.get("entries") or []

    if not entries:
        return jsonify({"error": "Προσθέστε τουλάχιστον μία υπερωρία."}), 400

    overtimes: list[Overtime] = []
    for entry in entries:
        overtimes.append(
            Overtime(
                employee_tax_identification_number=entry["employee_afm"].strip(),
                employee_social_security_number=entry["amka"].strip(),
                employee_last_name=entry["last_name"].strip(),
                employee_first_name=entry["first_name"].strip(),
                overtime_date=_parse_date(entry["overtime_date"]),
                overtime_start_time=_parse_time(entry["start_time"]),
                overtime_end_time=_parse_time(entry["end_time"]),
                overtime_cancellation=bool(entry.get("cancellation")),
                employee_profession_code=entry["profession_code"].strip(),
                overtime_justification=entry["justification"],
                weekly_workdays_number=int(entry.get("weekly_workdays") or 5),
                asee_approval=entry.get("asee_approval") or "",
            )
        )

    company = CompanyOvertime(
        business_branch_number=int(branch["branch_number"]),
        sepe_service_code=branch.get("sepe_service_code", ""),
        business_primary_activity_code=branch.get("primary_kad", ""),
        business_branch_activity_code=branch.get("branch_kad", ""),
        kallikratis_municipal_code=branch.get("kallikratis", ""),
        legal_representative_tax_identification_number=branch.get(
            "legal_rep_afm", ""
        ),
        employee_overtimes=overtimes,
        comments=data.get("comments") or "",
    )

    try:
        results = client.submit_overtime([company])
        return jsonify({"submissions": _submission_list(results)})
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


@app.post("/api/daily-schedule")
def submit_daily_schedule():
    client, err = _require_app_and_client()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    schedules = data.get("employee_schedules") or []
    if not schedules:
        return jsonify({"error": "Προσθέστε τουλάχιστον ένα ημερήσιο πρόγραμμα."}), 400

    employee_rows: list[EmployeeDailySchedule] = []
    for row in schedules:
        workdays = [
            WorkdayDetails(
                work_type=wd["work_type"],
                start_time=_parse_time(wd["start_time"]),
                end_time=_parse_time(wd["end_time"]),
            )
            for wd in row.get("workdays") or []
        ]
        employee_rows.append(
            EmployeeDailySchedule(
                employee_tax_identification_number=row["employee_afm"].strip(),
                employee_last_name=row["last_name"].strip(),
                employee_first_name=row["first_name"].strip(),
                schedule_date=_parse_date(row["schedule_date"]),
                workday_details=workdays,
            )
        )

    company = CompanyDailySchedule(
        business_branch_number=int(data["branch_number"]),
        start_date=_parse_date(data.get("start_date")),
        end_date=_parse_date(data.get("end_date")),
        employee_schedules=employee_rows,
        comments=data.get("comments") or "",
    )

    try:
        results = client.submit_daily_schedule([company])
        return jsonify({"submissions": _submission_list(results)})
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


@app.post("/api/weekly-schedule")
def submit_weekly_schedule():
    client, err = _require_app_and_client()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    schedules = data.get("employee_schedules") or []
    if not schedules:
        return jsonify({"error": "Προσθέστε τουλάχιστον ένα εβδομαδιαίο πρόγραμμα."}), 400

    employee_rows: list[EmployeeWeeklySchedule] = []
    for row in schedules:
        workdays = [
            WorkdayDetails(
                work_type=wd["work_type"],
                start_time=_parse_time(wd["start_time"]),
                end_time=_parse_time(wd["end_time"]),
            )
            for wd in row.get("workdays") or []
        ]
        employee_rows.append(
            EmployeeWeeklySchedule(
                employee_tax_identification_number=row["employee_afm"].strip(),
                employee_last_name=row["last_name"].strip(),
                employee_first_name=row["first_name"].strip(),
                schedule_date=_parse_date(row["schedule_date"]),
                workday_details=workdays,
            )
        )

    company = CompanyWeeklySchedule(
        business_branch_number=int(data["branch_number"]),
        start_date=_parse_date(data["start_date"]),
        end_date=_parse_date(data["end_date"]),
        employee_schedules=employee_rows,
        comments=data.get("comments") or "",
    )

    try:
        results = client.submit_weekly_schedule([company])
        return jsonify({"submissions": _submission_list(results)})
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


@app.get("/api/kiosk/ping")
def kiosk_ping():
    """Έλεγχος ότι τρέχει η σωστή έκδοση server (JSON, όχι 404 HTML)."""
    blocked = verify_kiosk_request(request.headers)
    if blocked:
        return jsonify({"ok": False, "error": blocked}), 401
    return jsonify({"ok": True, "kiosk_api": True})


@app.get("/api/kiosk/companies")
def kiosk_companies():
    blocked = verify_kiosk_request(request.headers)
    if blocked:
        return jsonify({"error": blocked}), 401
    items = []
    for company_id in kiosk_allowed_company_ids():
        company = get_company(company_id, app.secret_key)
        if company:
            items.append({"id": company_id, "name": company.get("name") or ""})
    return jsonify({"companies": items})


@app.post("/api/kiosk/connect")
def kiosk_connect():
    """Έλεγχος σύνδεσης Ergani για επιλεγμένη εταιρεία (κωδικοί από admin)."""
    blocked = verify_kiosk_request(request.headers)
    if blocked:
        return jsonify({"error": blocked}), 401
    data = request.get_json(silent=True) or {}
    try:
        company_id = resolve_kiosk_company_id(request.headers, data)
        cfg = kiosk_company_config(company_id, app.secret_key)
        return jsonify({"ok": True, "connected": True, **cfg})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except (AuthenticationError, APIError) as exc:
        return _error_response(exc)


@app.get("/api/kiosk/config")
def kiosk_config():
    blocked = verify_kiosk_request(request.headers)
    if blocked:
        return jsonify({"error": blocked}), 401
    try:
        company_id = resolve_kiosk_company_id(request.headers)
        return jsonify(kiosk_company_config(company_id, app.secret_key))
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


@app.get("/api/kiosk/statements")
def kiosk_statements():
    blocked = verify_kiosk_request(request.headers)
    if blocked:
        return jsonify({"error": blocked}), 401
    try:
        company_id = resolve_kiosk_company_id(request.headers)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()
    punches = list_card_punches(
        company_id, date_from=date_from, date_to=date_to
    )
    return jsonify(
        {
            "punches": punches,
            "count": len(punches),
            **get_card_punches_meta(company_id),
        }
    )


@app.post("/api/kiosk/sync")
def kiosk_sync():
    blocked = verify_kiosk_request(request.headers)
    if blocked:
        return jsonify({"error": blocked}), 401
    data = request.get_json(silent=True) or {}
    try:
        company_id = resolve_kiosk_company_id(request.headers, data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    from kiosk import client_for_company

    try:
        client = client_for_company(company_id, app.secret_key)
        items = _fetch_employees_from_ergani(client, all_branches=True)
        rows = [
            {
                "afm": (e.tax_identification_number or "").strip(),
                "first_name": e.first_name or "",
                "last_name": e.last_name or "",
                "father_name": e.father_name or "",
                "branch_number": e.branch_number,
            }
            for e in items
            if (e.tax_identification_number or "").strip()
        ]
        save_company_employees(
            company_id,
            rows,
            synced_by="kiosk",
        )
        synced_at = get_company_employees(company_id).get("synced_at") or ""
        return jsonify(
            {
                "ok": True,
                "count": len(rows),
                "synced_at": synced_at,
                "synced_at_label": _format_sync_label(synced_at),
            }
        )
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


def _format_sync_label(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("Completed at %d/%m/%Y %H:%M")
    except ValueError:
        return iso


@app.post("/api/kiosk/preview")
def kiosk_preview():
    """Προεπισκόπηση QR πριν την υποβολή (χωρίς αποστολή στο Ergani)."""
    blocked = verify_kiosk_request(request.headers)
    if blocked:
        return jsonify({"error": blocked}), 401

    data = request.get_json(silent=True) or {}
    movement_type = (data.get("movement_type") or "").strip().upper()
    if movement_type not in {"ARRIVAL", "DEPARTURE"}:
        return jsonify({"error": "Άγνωστος τύπος κίνησης."}), 400

    qr_payload = (data.get("qr_payload") or data.get("qr") or "").strip()
    employee_afm = parse_qr_employee_afm(qr_payload)
    try:
        company_id = resolve_kiosk_company_id(request.headers, data)
        cfg = kiosk_company_config(company_id, app.secret_key)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    from kiosk import lookup_employee

    employee = lookup_employee(company_id, employee_afm) if employee_afm else None
    display_name = ""
    if employee:
        display_name = f"{employee.get('last_name') or ''} {employee.get('first_name') or ''}".strip()

    label = "Προσέλευση (Check-in)" if movement_type == "ARRIVAL" else "Αποχώρηση (Check-out)"
    return jsonify(
        {
            "movement_type": movement_type,
            "movement_label": label,
            "afm": employee_afm,
            "employee": {
                "display_name": display_name,
                "first_name": (employee or {}).get("first_name") or "",
                "last_name": (employee or {}).get("last_name") or "",
            }
            if employee
            else None,
            "company_name": cfg.get("company_name") or "",
        }
    )


@app.post("/api/kiosk/punch")
def kiosk_punch():
    blocked = verify_kiosk_request(request.headers)
    if blocked:
        return jsonify({"error": blocked}), 401

    data = request.get_json(silent=True) or {}
    movement_type = (data.get("movement_type") or "").strip().upper()
    if movement_type not in {"ARRIVAL", "DEPARTURE"}:
        return jsonify({"error": "movement_type πρέπει να είναι ARRIVAL ή DEPARTURE."}), 400

    qr_payload = (data.get("qr_payload") or data.get("qr") or "").strip()
    employee_afm = (data.get("employee_afm") or "").strip() or parse_qr_employee_afm(
        qr_payload
    )
    if not employee_afm:
        return jsonify({"error": "Δεν βρέθηκε ΑΦΜ στο QR."}), 400

    try:
        company_id = resolve_kiosk_company_id(request.headers, data)
        cfg = kiosk_company_config(company_id, app.secret_key)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except (AuthenticationError, APIError) as exc:
        return _error_response(exc)

    employer_afm = (data.get("employer_afm") or cfg["employer_afm"]).strip()
    branch_raw = data.get("branch_number")
    if branch_raw is not None and branch_raw != "":
        try:
            branch_number = int(branch_raw)
        except ValueError:
            return jsonify({"error": "Μη έγκυρο παράρτημα."}), 400
    else:
        branch_number = int(cfg["branch_number"])

    try:
        result = submit_kiosk_punch(
            company_id=company_id,
            secret_key=app.secret_key,
            movement_type=movement_type,
            employee_afm=employee_afm,
            employer_afm=employer_afm,
            branch_number=branch_number,
        )
        return jsonify(result)
    except (AuthenticationError, APIError, ValueError) as exc:
        return _error_response(exc)


def main() -> None:
    port = int(os.environ.get("ERGANI_UI_PORT", "5050"))
    host = os.environ.get("ERGANI_UI_HOST", "127.0.0.1").strip() or "127.0.0.1"
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
