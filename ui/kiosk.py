"""Kiosk API helpers (tablet card scanner — no app-user login)."""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Any

from ergani.client import ErganiClient
from ergani.models import CompanyWorkCard, WorkCard
from store import append_card_punches, get_company, get_company_employees, normalize_employee_row

DEFAULT_BASE_URL = "https://eservices.yeka.gr/WebservicesAPI/Api"

_AFM_RE = re.compile(r"\b(\d{9})\b")


def kiosk_device_key() -> str:
    return os.environ.get("ERGANI_KIOSK_DEVICE_KEY", "").strip()


def kiosk_company_id() -> int | None:
    raw = os.environ.get("ERGANI_KIOSK_COMPANY_ID", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def kiosk_allowed_company_ids() -> list[int]:
    raw = os.environ.get("ERGANI_KIOSK_COMPANY_IDS", "").strip()
    if raw:
        ids: list[int] = []
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        if ids:
            return ids
    single = kiosk_company_id()
    return [single] if single is not None else []


def resolve_kiosk_company_id(headers: Any, data: dict[str, Any] | None = None) -> int:
    allowed = kiosk_allowed_company_ids()
    if not allowed:
        raise ValueError(
            "Δεν έχουν οριστεί εταιρείες kiosk (ERGANI_KIOSK_COMPANY_ID ή ERGANI_KIOSK_COMPANY_IDS)."
        )
    raw = (headers.get("X-Kiosk-Company-Id") or headers.get("X-Kiosk-Company-ID") or "").strip()
    if not raw and data:
        raw = str(data.get("company_id") or "").strip()
    if raw:
        company_id = int(raw)
        if company_id in allowed:
            return company_id
    return allowed[0]


def verify_kiosk_request(headers: Any) -> str | None:
    """Return error message if invalid, else None."""
    expected = kiosk_device_key()
    if not expected or len(expected) < 16:
        return "Kiosk δεν είναι ρυθμισμένο στο server (ERGANI_KIOSK_DEVICE_KEY)."
    provided = (headers.get("X-Kiosk-Key") or headers.get("X-Kiosk-Token") or "").strip()
    if not provided or provided != expected:
        return "Μη έγκυρο κλειδί συσκευής."
    if not kiosk_allowed_company_ids():
        return "Δεν έχουν οριστεί εταιρείες kiosk."
    return None


def kiosk_company_config(company_id: int, secret_key: str) -> dict[str, Any]:
    if company_id not in kiosk_allowed_company_ids():
        raise ValueError("Η εταιρεία δεν επιτρέπεται στο kiosk.")
    company = get_company(company_id, secret_key)
    if not company:
        raise ValueError("Η εταιρεία δεν βρέθηκε.")
    branch_number = int(os.environ.get("ERGANI_KIOSK_BRANCH_NUMBER", "0") or 0)
    employer_afm = (os.environ.get("ERGANI_KIOSK_EMPLOYER_AFM") or "").strip()
    if not employer_afm:
        try:
            client = client_for_company(company_id, secret_key)
            details = client.get_employer_details()
            employer_afm = (details.employer_tax_identification_number or "").strip()
        except Exception:
            employer_afm = ""
    emp_data = get_company_employees(company_id)
    synced_at = emp_data.get("synced_at") or ""
    synced_label = ""
    if synced_at:
        try:
            dt = datetime.fromisoformat(synced_at.replace("Z", "+00:00"))
            synced_label = dt.strftime("Completed at %d/%m/%Y %H:%M")
        except ValueError:
            synced_label = synced_at

    return {
        "company_id": company_id,
        "company_name": company.get("name") or "",
        "employer_afm": employer_afm,
        "branch_number": branch_number,
        "branch_label": f"({branch_number}) ΕΔΡΑ",
        "synced_at": synced_at,
        "synced_at_label": synced_label,
    }


def parse_qr_employee_afm(payload: str) -> str | None:
    """Extract Greek employee AFM (9 digits) from QR text."""
    text = (payload or "").strip()
    if not text:
        return None
    if text.isdigit() and len(text) == 9:
        return text
    for key in ("afm=", "AFM=", "f_afm=", "taxId=", "tax_id="):
        if key in text:
            fragment = text.split(key, 1)[1].split("&", 1)[0].split(",", 1)[0].strip()
            if fragment.isdigit() and len(fragment) == 9:
                return fragment
    match = _AFM_RE.search(text)
    if match:
        return match.group(1)
    return None


def client_for_company(company_id: int, secret_key: str) -> ErganiClient:
    company = get_company(company_id, secret_key)
    if not company:
        raise ValueError("Η εταιρεία δεν βρέθηκε.")
    base_url = (company.get("base_url") or DEFAULT_BASE_URL).strip()
    user_type = (company.get("user_type") or "02").strip()
    if user_type not in {"01", "02", "03"}:
        user_type = "02"
    return ErganiClient(
        company["ergani_username"],
        company["ergani_password"],
        base_url,
        user_type=user_type,
    )


def lookup_employee(company_id: int, afm: str) -> dict[str, Any] | None:
    data = get_company_employees(company_id)
    employees = data.get("employees") or []
    target = afm.strip()
    for row in employees:
        normalized = normalize_employee_row(row if isinstance(row, dict) else {})
        if normalized.get("afm") == target:
            return normalized
    return None


def submit_kiosk_punch(
    *,
    company_id: int,
    secret_key: str,
    movement_type: str,
    employee_afm: str,
    employer_afm: str,
    branch_number: int,
    movement_at: datetime | None = None,
) -> dict[str, Any]:
    employee = lookup_employee(company_id, employee_afm)
    if not employee:
        raise ValueError(
            f"Ο εργαζόμενος με ΑΦΜ {employee_afm} δεν βρέθηκε. "
            "Συγχρόνισε προσωπικό από το admin."
        )

    when = movement_at or datetime.now().astimezone()
    submission_date: date = when.date()
    card = WorkCard(
        employee_tax_identification_number=employee_afm,
        employee_last_name=employee.get("last_name") or "",
        employee_first_name=employee.get("first_name") or "",
        work_card_movement_type=movement_type,
        work_card_submission_date=submission_date,
        work_card_movement_datetime=when,
        late_declaration_justification=None,
    )
    company_card = CompanyWorkCard(
        employer_tax_identification_number=employer_afm,
        business_branch_number=branch_number,
        comments="",
        card_details=[card],
    )
    client = client_for_company(company_id, secret_key)
    results = client.submit_work_card([company_card])
    protocol = results[0].get("protocol") if results else None

    entry = {
        "employee_afm": employee_afm,
        "first_name": employee.get("first_name") or "",
        "last_name": employee.get("last_name") or "",
        "movement_type": movement_type,
        "submission_date": submission_date.isoformat(),
        "movement_datetime": when.isoformat(),
        "branch_number": branch_number,
    }
    append_card_punches(
        company_id,
        [
            {
                "employee_afm": entry["employee_afm"],
                "first_name": entry["first_name"],
                "last_name": entry["last_name"],
                "movement_type": movement_type,
                "date": submission_date.isoformat(),
                "time": when.strftime("%H:%M"),
                "branch_number": branch_number,
                "source": "kiosk",
            }
        ],
        submitted_by="kiosk",
    )

    label = "Προσέλευση" if movement_type == "ARRIVAL" else "Αποχώρηση"
    return {
        "ok": True,
        "protocol": protocol,
        "movement_type": movement_type,
        "movement_label": label,
        "employee": {
            "afm": employee_afm,
            "first_name": entry["first_name"],
            "last_name": entry["last_name"],
            "display_name": f"{entry['last_name']} {entry['first_name']}".strip(),
        },
        "movement_datetime": when.isoformat(),
    }
