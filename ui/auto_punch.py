"""Αυτόματο check-in / check-out από το πρόγραμμα εβδομάδας (shift grid)."""

from __future__ import annotations

import logging
import os
import socket
import sys
import time

import requests
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

UI_DIR = Path(__file__).resolve().parent
ROOT = UI_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))

from ergani.client import ErganiClient
from ergani.exceptions import APIError, AuthenticationError
from ergani.models import CompanyWorkCard, WorkCard
from kiosk import client_for_company, kiosk_company_config
from autopunch_alerts import (
    send_auto_punch_error,
    send_auto_punch_info,
    telegram_configured,
)
from store import append_card_punches, get_shift_grid, list_card_punches

logger = logging.getLogger("ergani.auto_punch")

TZ = ZoneInfo(os.environ.get("ERGANI_AUTO_PUNCH_TZ", "Europe/Athens"))


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def company_ids() -> list[int]:
    raw = os.environ.get("ERGANI_AUTO_PUNCH_COMPANY_IDS", "").strip()
    if not raw:
        single = os.environ.get("ERGANI_AUTO_PUNCH_COMPANY_ID", "").strip()
        raw = single
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


def interval_seconds() -> int:
    try:
        return max(15, int(os.environ.get("ERGANI_AUTO_PUNCH_INTERVAL_SEC", "60")))
    except ValueError:
        return 60


def grace_minutes() -> int:
    try:
        return max(1, int(os.environ.get("ERGANI_AUTO_PUNCH_GRACE_MINUTES", "30")))
    except ValueError:
        return 30


def branch_number() -> int:
    try:
        return int(os.environ.get("ERGANI_AUTO_PUNCH_BRANCH_NUMBER", "0"))
    except ValueError:
        return 0


def late_justification() -> str | None:
    raw = os.environ.get("ERGANI_AUTO_PUNCH_LATE_JUSTIFICATION", "").strip()
    return raw or None


def ui_secret() -> str:
    secret = os.environ.get("ERGANI_UI_SECRET", "").strip()
    if len(secret) < 32:
        raise RuntimeError("Ρύθμισε ERGANI_UI_SECRET (≥32 χαρακτήρες) στο ui/.env")
    return secret


def host_label() -> str:
    override = os.environ.get("ERGANI_AUTO_PUNCH_HOSTNAME", "").strip()
    if override:
        return override
    return socket.gethostname()


def monday_of_week(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_dates(week_start: date) -> list[date]:
    return [week_start + timedelta(days=i) for i in range(7)]


def today_day_index(week_start: date, today: date) -> int:
    dates = week_dates(week_start)
    try:
        return dates.index(today)
    except ValueError:
        return -1


def parse_week_start(raw: Any) -> date | None:
    text = str(raw or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def parse_hhmm(raw: str) -> tuple[int, int] | None:
    text = (raw or "").strip()
    if len(text) != 5 or text[2] != ":":
        return None
    try:
        hour = int(text[:2])
        minute = int(text[3:])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def is_work_shift(shift: dict[str, Any] | None) -> bool:
    if not shift or not isinstance(shift, dict):
        return False
    if shift.get("off"):
        return False
    if shift.get("empty", True):
        return False
    return bool(parse_hhmm(str(shift.get("arrival") or ""))) and bool(
        parse_hhmm(str(shift.get("departure") or ""))
    )


def is_overnight_shift(shift: dict[str, Any]) -> bool:
    arrival_parts = parse_hhmm(str(shift.get("arrival") or ""))
    departure_parts = parse_hhmm(str(shift.get("departure") or ""))
    return bool(
        arrival_parts
        and departure_parts
        and departure_parts <= arrival_parts
    )


def shift_targets(week_start: date, now: datetime) -> list[tuple[date, int, bool]]:
    """(ημέρα βάρδιας, index εβδομάδας, μόνο overnight checkout)."""
    today = now.date()
    day_index = today_day_index(week_start, today)
    if day_index < 0:
        return []
    targets: list[tuple[date, int, bool]] = [(today, day_index, False)]
    if day_index > 0:
        targets.append((today - timedelta(days=1), day_index - 1, True))
    return targets


def scheduled_movement(
    shift_date: date,
    movement_type: str,
    shift: dict[str, Any],
) -> datetime | None:
    arrival_hhmm = str(shift.get("arrival") or "")
    departure_hhmm = str(shift.get("departure") or "")
    arrival_parts = parse_hhmm(arrival_hhmm)
    departure_parts = parse_hhmm(departure_hhmm)
    if movement_type == "ARRIVAL":
        return movement_at(shift_date, arrival_hhmm)
    scheduled = movement_at(shift_date, departure_hhmm)
    if not scheduled:
        return None
    if (
        arrival_parts
        and departure_parts
        and departure_parts <= arrival_parts
    ):
        scheduled += timedelta(days=1)
    return scheduled


def movement_at(day: date, hhmm: str) -> datetime | None:
    parsed = parse_hhmm(hhmm)
    if not parsed:
        return None
    hour, minute = parsed
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def is_due(scheduled: datetime, now: datetime, grace: int) -> bool:
    return scheduled <= now < scheduled + timedelta(minutes=grace)


def already_punched(
    today_punches: list[dict[str, Any]], afm: str, movement_type: str
) -> bool:
    for row in today_punches:
        if row.get("afm") != afm and row.get("employee_afm") != afm:
            continue
        if row.get("movement_type") == movement_type:
            return True
    return False


def remote_punch_url() -> str:
    return os.environ.get("ERGANI_AUTO_PUNCH_REMOTE_URL", "").strip().rstrip("/")


def remote_punch_key() -> str:
    return os.environ.get("ERGANI_AUTO_PUNCH_REMOTE_KEY", "").strip()


def submit_punch(
    *,
    company_id: int,
    secret_key: str,
    employee: dict[str, Any],
    movement_type: str,
    when: datetime,
    employer: str,
    branch: int,
    late: str | None,
) -> str | None:
    url = remote_punch_url()
    key = remote_punch_key()
    if url and key:
        return _submit_punch_remote(
            url=url,
            key=key,
            company_id=company_id,
            employee=employee,
            movement_type=movement_type,
            when=when,
            employer=employer,
            branch=branch,
            late=late,
        )
    return _submit_punch_local(
        company_id=company_id,
        secret_key=secret_key,
        employee=employee,
        movement_type=movement_type,
        when=when,
        employer=employer,
        branch=branch,
        late=late,
    )


def _submit_punch_remote(
    *,
    url: str,
    key: str,
    company_id: int,
    employee: dict[str, Any],
    movement_type: str,
    when: datetime,
    employer: str,
    branch: int,
    late: str | None,
) -> str | None:
    payload: dict[str, Any] = {
        "company_id": company_id,
        "employee_afm": employee["afm"],
        "movement_type": movement_type,
        "movement_datetime": when.isoformat(),
        "employer_afm": employer,
        "branch_number": branch,
    }
    if late:
        payload["late_declaration_justification"] = late
    res = requests.post(
        f"{url}/api/internal/auto-punch",
        headers={"X-Auto-Punch-Key": key, "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    data: dict[str, Any] = {}
    try:
        data = res.json()
    except ValueError:
        pass
    if res.status_code >= 400:
        raise ValueError(data.get("error") or res.text[:200] or f"HTTP {res.status_code}")
    return data.get("protocol")


def employer_afm(company_id: int, secret_key: str) -> str:
    override = os.environ.get("ERGANI_AUTO_PUNCH_EMPLOYER_AFM", "").strip()
    if override:
        return override
    cfg = kiosk_company_config(company_id, secret_key)
    return (cfg.get("employer_afm") or "").strip()


def _submit_punch_local(
    *,
    company_id: int,
    secret_key: str,
    employee: dict[str, Any],
    movement_type: str,
    when: datetime,
    employer: str,
    branch: int,
    late: str | None,
) -> str | None:
    card = WorkCard(
        employee_tax_identification_number=employee["afm"],
        employee_last_name=employee.get("last_name") or "",
        employee_first_name=employee.get("first_name") or "",
        work_card_movement_type=movement_type,
        work_card_submission_date=when.date(),
        work_card_movement_datetime=when,
        late_declaration_justification=late,
    )
    company_card = CompanyWorkCard(
        employer_tax_identification_number=employer,
        business_branch_number=branch,
        comments="",
        card_details=[card],
    )
    client: ErganiClient = client_for_company(company_id, secret_key)
    results = client.submit_work_card([company_card])
    protocol = results[0].get("protocol") if results else None
    append_card_punches(
        company_id,
        [
            {
                "employee_afm": employee["afm"],
                "afm": employee["afm"],
                "first_name": employee.get("first_name") or "",
                "last_name": employee.get("last_name") or "",
                "movement_type": movement_type,
                "date": when.date().isoformat(),
                "reference_date": when.date().isoformat(),
                "time": when.strftime("%H:%M"),
                "movement_datetime": when.isoformat(),
                "branch_number": branch,
                "source": "auto_punch",
            }
        ],
        submitted_by="auto_punch",
    )
    return protocol


def process_company(company_id: int, secret_key: str, now: datetime) -> None:
    grid = get_shift_grid(company_id, branch_number())
    if not grid:
        logger.debug("company %s: no shift grid", company_id)
        return

    week_start = parse_week_start(grid.get("weekStart"))
    if not week_start:
        logger.warning("company %s: invalid weekStart in shift grid", company_id)
        return

    today = now.date()
    targets = shift_targets(week_start, now)
    if not targets:
        logger.warning(
            "company %s: today %s not in grid week starting %s — update week in UI",
            company_id,
            today,
            week_start,
        )
        return

    employees = grid.get("employees") or []
    if not isinstance(employees, list) or not employees:
        logger.debug("company %s: no employees in shift grid", company_id)
        return

    employer = employer_afm(company_id, secret_key)
    if not employer:
        logger.error("company %s: missing employer AFM", company_id)
        return

    branch = branch_number()
    grace = grace_minutes()
    late = late_justification()
    yesterday_iso = (today - timedelta(days=1)).isoformat()
    day_iso = today.isoformat()
    recent_punches = list_card_punches(
        company_id, date_from=yesterday_iso, date_to=day_iso
    )

    for emp in employees:
        if not isinstance(emp, dict):
            continue
        afm = (emp.get("afm") or "").strip()
        if not afm:
            continue
        shifts = emp.get("shifts") or []
        if not isinstance(shifts, list):
            continue

        name = f"{emp.get('last_name', '')} {emp.get('first_name', '')}".strip() or afm

        for shift_date, day_index, departure_only in targets:
            if day_index >= len(shifts):
                continue
            shift = shifts[day_index]
            if not is_work_shift(shift):
                continue
            if departure_only and not is_overnight_shift(shift):
                continue

            movements: tuple[tuple[str, str], ...]
            if departure_only:
                movements = (("DEPARTURE", str(shift.get("departure") or "")),)
            else:
                movements = (
                    ("ARRIVAL", str(shift.get("arrival") or "")),
                    ("DEPARTURE", str(shift.get("departure") or "")),
                )

            for movement_type, hhmm in movements:
                if (
                    movement_type == "DEPARTURE"
                    and not departure_only
                    and is_overnight_shift(shift)
                ):
                    continue
                scheduled = scheduled_movement(shift_date, movement_type, shift)
                if not scheduled:
                    continue
                if not is_due(scheduled, now, grace):
                    continue
                if already_punched(recent_punches, afm, movement_type):
                    continue
                label = "Check-in" if movement_type == "ARRIVAL" else "Check-out"
                ref_day = scheduled.date().isoformat()
                try:
                    protocol = submit_punch(
                        company_id=company_id,
                        secret_key=secret_key,
                        employee={"afm": afm, **emp},
                        movement_type=movement_type,
                        when=scheduled,
                        employer=employer,
                        branch=branch,
                        late=late if now > scheduled + timedelta(minutes=2) else None,
                    )
                    logger.info(
                        "%s %s %s %s — protocol %s",
                        label,
                        name,
                        afm,
                        hhmm,
                        protocol or "—",
                    )
                    send_auto_punch_info(
                        f"{label} {name}\nΑΦΜ: {afm}\nΏρα: {hhmm}\nΗμ/νία: {ref_day}"
                        + (f"\nProtocol: {protocol}" if protocol else "")
                    )
                except (AuthenticationError, APIError, ValueError) as exc:
                    err = f"{label} {name}\nΑΦΜ: {afm}\nΏρα: {hhmm}\n{exc}"
                    logger.error("%s failed: %s", label, err)
                    send_auto_punch_error(
                        err, key=f"{company_id}:{afm}:{movement_type}:{exc}"
                    )


def run_once() -> None:
    secret = ui_secret()
    ids = company_ids()
    if not ids:
        logger.error("Όρισε ERGANI_AUTO_PUNCH_COMPANY_IDS στο ui/.env")
        return
    now = datetime.now(TZ)
    for company_id in ids:
        try:
            process_company(company_id, secret, now)
        except Exception as exc:
            logger.exception("company %s: unexpected error", company_id)
            err = f"Εταιρεία {company_id}\n{exc}"
            send_auto_punch_error(err, key=f"company:{company_id}:{exc}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    if not _env_bool("ERGANI_AUTO_PUNCH_ENABLED"):
        logger.error("ERGANI_AUTO_PUNCH_ENABLED=1 στο ui/.env για να τρέξει το bot")
        raise SystemExit(1)

    ids = company_ids()
    logger.info(
        "Auto punch started — host=%s companies=%s interval=%ss grace=%sm",
        host_label(),
        ids,
        interval_seconds(),
        grace_minutes(),
    )
    if telegram_configured():
        send_auto_punch_info(f"Bot ξεκίνησε\nΕταιρείες: {ids}")
    else:
        logger.warning(
            "Telegram δεν είναι ρυθμισμένο — όρισε ERGANI_AUTO_PUNCH_TELEGRAM_* στο .env"
        )
    while True:
        run_once()
        time.sleep(interval_seconds())


if __name__ == "__main__":
    main()
