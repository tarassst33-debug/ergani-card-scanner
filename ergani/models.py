from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Dict, List, Literal, Optional, TypedDict

from ergani.typings import (
    LateDeclarationJustificationType,
    OvertimeJustificationType,
    ScheduleWorkType,
    WorkCardMovementType,
)
from ergani.utils import (
    format_date,
    format_datetime,
    format_time,
    get_day_of_week,
    get_ergani_late_declaration_justification,
    get_ergani_overtime_cancellation,
    get_ergani_overtime_justification,
    get_ergani_work_type,
    get_ergani_workcard_movement_type,
)


@dataclass
class BusinessBranch:
    """
    Represents a business branch returned by the Ergani query services.

    Attributes:
        branch_number (Optional[int]): The verified branch identifier used by later
            query endpoints when present in the payload.
        address (Optional[str]): The branch address when returned by EX_BASE_02.
        sepe_service_code (Optional[str]): The SEPE service code for the branch.
        oaed_service_code (Optional[str]): The OAED service code for the branch.
        business_branch_activity_code (Optional[str]): The branch activity code.
        kallikratis_municipal_code (Optional[str]): The Kallikratis municipal code.
        status_description (Optional[str]): The current branch status description.
        raw_payload (Dict[str, Any]): The raw branch payload returned by the API.
    """

    branch_number: Optional[int]
    address: Optional[str]
    sepe_service_code: Optional[str]
    oaed_service_code: Optional[str]
    business_branch_activity_code: Optional[str]
    kallikratis_municipal_code: Optional[str]
    status_description: Optional[str]
    raw_payload: Dict[str, Any]

    @classmethod
    def parse(cls, payload: Dict[str, Any]) -> BusinessBranch:
        if not isinstance(payload, dict):
            raise ValueError("Expected EX_BASE_02 branch payload to be an object")

        return cls(
            branch_number=_parse_int(payload.get("Aa")),
            address=payload.get("Address"),
            sepe_service_code=payload.get("YpiresiaSepe"),
            oaed_service_code=payload.get("YpiresiaOaed"),
            business_branch_activity_code=payload.get("Kad"),
            kallikratis_municipal_code=payload.get("Kallikratis"),
            status_description=payload.get("StatusDescription"),
            raw_payload=payload,
        )

    @classmethod
    def parse_many(cls, payload: Any) -> List[BusinessBranch]:
        if payload is None:
            return []

        branch_payload = cls._unwrap_payload(payload)

        if isinstance(branch_payload, dict):
            return [cls.parse(branch_payload)]

        if not isinstance(branch_payload, list):
            raise ValueError(
                "Expected EX_BASE_02 branch payload to be an object or list"
            )

        return [cls.parse(item) for item in branch_payload]

    @staticmethod
    def _unwrap_payload(payload: Any) -> Any:
        if not isinstance(payload, dict):
            raise ValueError("Expected EX_BASE_02 payload to be an object")

        if "EX_BASE_02" in payload:
            payload = payload["EX_BASE_02"]

        if not isinstance(payload, dict):
            raise ValueError("Expected EX_BASE_02 payload to contain an object")

        branch_payload = payload.get("Pararthma", payload)

        return branch_payload


@dataclass
class EmployerDetails:
    employer_id: int | None = None
    employer_tax_identification_number: str | None = None
    name: str | None = None
    distinctive_title: str | None = None
    employer_registry_number: str | None = None
    is_in_card_sector: bool | None = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, payload: Any) -> EmployerDetails:
        employer_payload = cls._parse_payload(payload)

        return cls(
            employer_id=_parse_int(employer_payload.get("Id")),
            employer_tax_identification_number=employer_payload.get("Afm"),
            name=employer_payload.get("Eponimia"),
            distinctive_title=employer_payload.get("DiakritikosTitlos"),
            employer_registry_number=employer_payload.get("Ame"),
            is_in_card_sector=_parse_card_sector_flag(
                employer_payload.get("IsInCardSector")
            ),
            raw_payload=dict(employer_payload),
        )

    @classmethod
    def _parse_payload(cls, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Expected EX_BASE_01 payload to be an object")

        if "EX_BASE_01" in payload:
            payload = payload["EX_BASE_01"]

        if not isinstance(payload, dict):
            raise ValueError("Expected EX_BASE_01 payload to contain an object")

        employer_payload = payload.get("Ergodotis", payload)

        if not isinstance(employer_payload, dict):
            raise ValueError("Expected EX_BASE_01 employer payload to be an object")

        return employer_payload


def _parse_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_card_sector_flag(value: Any) -> bool | None:
    if isinstance(value, str):
        normalized_value = value.strip()
        if normalized_value == "1":
            return True
        if normalized_value == "0":
            return False

    return None


def parse_employer_details(payload: Any) -> EmployerDetails:
    return EmployerDetails.parse(payload)


def _first_present(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None and payload[key] != "":
            return payload[key]
    return None


def _pick_str(payload: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _deep_pick_str(payload: Any, *keys: str) -> Optional[str]:
    if isinstance(payload, dict):
        value = _pick_str(payload, *keys)
        if value:
            return value
        for child in payload.values():
            value = _deep_pick_str(child, *keys)
            if value:
                return value
    elif isinstance(payload, list):
        for item in payload:
            value = _deep_pick_str(item, *keys)
            if value:
                return value
    return None


def _format_ergani_date(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not text:
        return None
    if "/" in text and len(text) >= 8:
        return text
    normalized = text.replace("T", " ").split(".")[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return text


@dataclass
class Employee:
    """Employee record from Ergani query services (e.g. EX_BASE_05)."""

    tax_identification_number: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    father_name: Optional[str]
    identity_number: Optional[str]
    social_security_number: Optional[str]
    profession_code: Optional[str]
    branch_number: Optional[int]
    date_from: Optional[str]
    date_to: Optional[str]
    status_description: Optional[str]
    raw_payload: Dict[str, Any]

    @classmethod
    def parse(cls, payload: Dict[str, Any]) -> Employee:
        father_name = _pick_str(
            payload,
            "OnomaPatros",
            "Patronymic",
            "PatrosOnoma",
            "onomaPatros",
            "f_patronymo",
            "f_onoma_patros",
        ) or _deep_pick_str(
            payload,
            "OnomaPatros",
            "Patronymic",
            "PatrosOnoma",
            "f_patronymo",
            "f_onoma_patros",
        )
        date_from_raw = _first_present(
            payload,
            "HmApo",
            "hmApo",
            "DateFrom",
            "dateFrom",
            "apo",
            "Apo",
            "f_from_date",
            "FromDate",
        ) or _deep_pick_str(
            payload, "HmApo", "hmApo", "f_from_date", "DateFrom", "FromDate"
        )
        date_to_raw = _first_present(
            payload, "HmEos", "hmEos", "DateTo", "dateTo", "eos", "Eos", "f_to_date", "ToDate"
        ) or _deep_pick_str(payload, "HmEos", "hmEos", "f_to_date", "DateTo", "ToDate")
        branch_raw = _first_present(
            payload,
            "Aa",
            "aa",
            "f_aa",
            "BranchNumber",
            "AaPararthmatos",
            "aaPararthmatos",
            "f_aa_pararthmatos",
        )
        if branch_raw is None:
            branch_deep = _deep_pick_str(
                payload, "Aa", "aa", "f_aa", "AaPararthmatos", "f_aa_pararthmatos"
            )
            branch_raw = int(branch_deep) if branch_deep and str(branch_deep).isdigit() else branch_deep

        return cls(
            tax_identification_number=_pick_str(
                payload, "Afm", "afm", "f_afm", "AFM", "f_afm"
            ),
            first_name=_pick_str(payload, "Onoma", "onoma", "f_onoma", "FirstName"),
            last_name=_pick_str(
                payload, "Eponymo", "eponymo", "f_eponymo", "LastName", "Eponimo"
            ),
            father_name=father_name,
            identity_number=_pick_str(
                payload,
                "ArTautotitas",
                "ArTaxotitas",
                "IdentityNumber",
                "AriythmosTautotitas",
                "f_ar_tautotitas",
            ),
            social_security_number=_pick_str(
                payload, "Amka", "amka", "f_amka", "AMKA", "AmkaErgazomenou"
            ),
            profession_code=_pick_str(
                payload,
                "Step",
                "step",
                "f_step",
                "ProfessionCode",
                "Eidikotita",
                "EidikotitaPerigrafi",
                "KodikosEidikotitas",
            ),
            branch_number=_parse_int(branch_raw),
            date_from=_format_ergani_date(date_from_raw),
            date_to=_format_ergani_date(date_to_raw),
            status_description=_pick_str(
                payload,
                "StatusDescription",
                "Status",
                "Katastasi",
                "EmploymentStatus",
                "TrexousaKatastasi",
            ),
            raw_payload=dict(payload),
        )

    @classmethod
    def _looks_like_employee(cls, payload: Dict[str, Any]) -> bool:
        return (
            _pick_str(payload, "Afm", "afm", "f_afm", "AFM", "f_afm") is not None
        )

    @classmethod
    def _collect_records(cls, payload: Any, found: List[Dict[str, Any]]) -> None:
        if isinstance(payload, dict):
            if cls._looks_like_employee(payload):
                found.append(payload)
            for value in payload.values():
                cls._collect_records(value, found)
        elif isinstance(payload, list):
            for item in payload:
                cls._collect_records(item, found)

    @classmethod
    def parse_many(cls, payload: Any) -> List[Employee]:
        if payload is None:
            return []

        if isinstance(payload, dict) and "EX_BASE_05" in payload:
            payload = payload["EX_BASE_05"]

        records: List[Dict[str, Any]] = []
        cls._collect_records(payload, records)

        employees: List[Employee] = []
        seen_afms: set[str] = set()
        for record in records:
            employee = cls.parse(record)
            afm = employee.tax_identification_number
            if not afm or afm in seen_afms:
                continue
            seen_afms.add(afm)
            employees.append(employee)

        return employees


@dataclass
class WorkCardMovement:
    """Work card punch (arrival/departure) from Ergani query services."""

    employee_tax_identification_number: Optional[str]
    employee_first_name: Optional[str]
    employee_last_name: Optional[str]
    movement_type: Optional[WorkCardMovementType]
    reference_date: Optional[str]
    movement_datetime: Optional[str]
    branch_number: Optional[int]
    raw_payload: Dict[str, Any]

    @classmethod
    def parse(cls, payload: Dict[str, Any]) -> WorkCardMovement:
        from ergani.utils import parse_workcard_movement_type

        movement_raw = _first_present(
            payload, "f_type", "Type", "type", "KinisiType", "MovementType"
        )
        movement_dt_raw = _first_present(
            payload,
            "f_date",
            "Date",
            "date",
            "KinisiDate",
            "MovementDate",
            "HmKinisis",
            "DateTime",
        )
        ref_raw = _first_present(
            payload,
            "f_reference_date",
            "ReferenceDate",
            "reference_date",
            "HmAnaforas",
            "DateAnaforas",
        )
        branch_raw = _first_present(
            payload, "f_aa", "Aa", "aa", "BranchNumber", "f_aa_pararthmatos"
        )
        return cls(
            employee_tax_identification_number=_pick_str(
                payload, "f_afm", "Afm", "afm", "AFM"
            ),
            employee_first_name=_pick_str(
                payload, "f_onoma", "Onoma", "onoma", "FirstName"
            ),
            employee_last_name=_pick_str(
                payload, "f_eponymo", "Eponymo", "eponymo", "Eponimo", "LastName"
            ),
            movement_type=parse_workcard_movement_type(movement_raw),
            reference_date=_format_ergani_date(ref_raw),
            movement_datetime=_format_movement_datetime(movement_dt_raw),
            branch_number=_parse_int(branch_raw),
            raw_payload=dict(payload),
        )

    @classmethod
    def _looks_like_movement(cls, payload: Dict[str, Any]) -> bool:
        if _pick_str(payload, "f_afm", "Afm", "afm", "AFM") is None:
            return False
        return _first_present(
            payload, "f_date", "Date", "date", "KinisiDate", "MovementDate"
        ) is not None

    @classmethod
    def _collect_records(cls, payload: Any, found: List[Dict[str, Any]]) -> None:
        if isinstance(payload, dict):
            details = payload.get("CardDetails") or payload.get("cardDetails")
            if isinstance(details, list):
                for item in details:
                    if isinstance(item, dict):
                        found.append(item)
            if cls._looks_like_movement(payload):
                found.append(payload)
            for value in payload.values():
                cls._collect_records(value, found)
        elif isinstance(payload, list):
            for item in payload:
                cls._collect_records(item, found)

    @classmethod
    def parse_many(cls, payload: Any) -> List[WorkCardMovement]:
        if payload is None:
            return []

        records: List[Dict[str, Any]] = []
        cls._collect_records(payload, records)

        movements: List[WorkCardMovement] = []
        seen: set[tuple[str, str, str]] = set()
        for record in records:
            movement = cls.parse(record)
            if not movement.movement_datetime:
                continue
            key = (
                movement.employee_tax_identification_number or "",
                movement.movement_datetime,
                movement.movement_type or "",
            )
            if key in seen:
                continue
            seen.add(key)
            movements.append(movement)

        movements.sort(
            key=lambda m: (m.reference_date or "", m.movement_datetime or ""),
            reverse=True,
        )
        return movements


def _format_movement_datetime(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ):
        try:
            parsed = datetime.strptime(normalized.split(".")[0], fmt.split(".")[0])
            return parsed.isoformat()
        except ValueError:
            continue
    return text


@dataclass
class WorkCard:
    """
    Represents a work card entry for an employee

    Attributes:
        employee_tax_identification_number (str): The employee's tax identification number
        employee_last_name (str): The last name of the employee
        employee_first_name (str): The first name of the employee
        work_card_movement_type (WorkCardMovementType): The type of work card movement
        work_card_submission_date (date): The date the work card was submitted
        work_card_movement_datetime (datetime): The exact date and time of the work card movement
        late_declaration_justification (Optional[LateDeclarationJustificationType]): The justification for the late declaration of the work card movement
    """

    employee_tax_identification_number: str
    employee_last_name: str
    employee_first_name: str
    work_card_movement_type: WorkCardMovementType
    work_card_submission_date: date
    work_card_movement_datetime: datetime
    late_declaration_justification: Optional[LateDeclarationJustificationType] = None

    def serialize(self):
        return {
            "f_afm": self.employee_tax_identification_number,
            "f_eponymo": self.employee_last_name,
            "f_onoma": self.employee_first_name,
            "f_type": get_ergani_workcard_movement_type(self.work_card_movement_type),
            "f_reference_date": self.work_card_submission_date.isoformat(),
            "f_date": format_datetime(self.work_card_movement_datetime),
            "f_aitiologia": get_ergani_late_declaration_justification(
                self.late_declaration_justification
            ),
        }


@dataclass
class CompanyWorkCard:
    """
    Represents work card entries that are issued on a single business branch

    Attributes:
        employer_tax_identification_number (str): The employer's tax identification number
        business_branch_number (int): The number identifying the specific business branch
        comments (Optional[str]): Additional comments related to the work cards
        card_details (List[WorkCard]): A list of `WorkCard` entries for the business branch
    """

    employer_tax_identification_number: str
    business_branch_number: int
    comments: Optional[str] = ""
    card_details: List[WorkCard] = field(default_factory=list)

    def serialize(self):
        return {
            "f_afm_ergodoti": self.employer_tax_identification_number,
            "f_aa": self.business_branch_number,
            "f_comments": self.comments,
            "Details": {
                "CardDetails": [
                    work_card.serialize() for work_card in self.card_details
                ]
            },
        }


@dataclass
class Overtime:
    """
    Represents an overtime entry for an employee

    Attributes:
        employee_tax_identification_number (str): The employee's tax identification number
        employee_social_security_number (str): The employee's social security number
        employee_last_name (str): The last name of the employee
        employee_first_name (str): The first name of the employee
        overtime_date (date): The date of the overtime
        overtime_start_time (time): The start time of the overtime period
        overtime_end_time (time): The end time of the overtime period
        overtime_cancellation (bool): Indicates if the overtime was cancelled or not
        employee_profession_code (str): The profession code of the employee
        overtime_justification (OvertimeJustificationType): The justification for the overtime
        weekly_workdays_number (Literal[5, 6]): The number of the employee's working days in a week
        asee_approval (Optional[str]): The ASEE aproval
    """

    employee_tax_identification_number: str
    employee_social_security_number: str
    employee_last_name: str
    employee_first_name: str
    overtime_date: date
    overtime_start_time: time
    overtime_end_time: time
    overtime_cancellation: bool
    employee_profession_code: str
    overtime_justification: OvertimeJustificationType
    weekly_workdays_number: Literal[5, 6]
    asee_approval: Optional[str] = ""

    def serialize(self):
        return {
            "f_afm": self.employee_tax_identification_number,
            "f_amka": self.employee_social_security_number,
            "f_eponymo": self.employee_last_name,
            "f_onoma": self.employee_first_name,
            "f_date": format_date(self.overtime_date),
            "f_from": format_time(self.overtime_start_time),
            "f_to": format_time(self.overtime_end_time),
            "f_cancellation": get_ergani_overtime_cancellation(
                self.overtime_cancellation
            ),
            "f_step": self.employee_profession_code,
            "f_reason": get_ergani_overtime_justification(self.overtime_justification),
            "f_weekdates": self.weekly_workdays_number,
            "f_asee": self.asee_approval,
        }


@dataclass
class CompanyOvertime:
    """
    Represents overtime entries that are issued on a single business branch

    Attributes:
        business_branch_number (int): The number identifying the specific business branch
        sepe_service_code (str): The SEPE service code
        business_primary_activity_code (str): The primary activity code of the business
        business_branch_activity_code (str): The activity code for the specific branch
        kallikratis_municipal_code (str): The kallikratis municipal code
        legal_representative_tax_identification_number (str): Tax identification number of the legal representative
        employee_overtimes (List[Overtime]): A list of `Overtime` entries for employees
        related_protocol_id (Optional[str]): Related protocol ID
        related_protocol_date (Optional[date]): The date of the related protocol
        employer_organization (Optional[str]): The employer's organization name
        business_secondary_activity_code_1 (Optional[str]): Secondary activity code 1
        business_secondary_activity_code_2 (Optional[str]): Secondary activity code 2
        business_secondary_activity_code_3 (Optional[str]): Secondary activity code 3
        business_secondary_activity_code_4 (Optional[str]): Secondary activity code 4
        comments (Optional[str]): Additional comments related to the overtime entries
    """

    business_branch_number: int
    sepe_service_code: str
    business_primary_activity_code: str
    business_branch_activity_code: str
    kallikratis_municipal_code: str
    legal_representative_tax_identification_number: str
    employee_overtimes: List[Overtime] = field(default_factory=list)
    related_protocol_id: Optional[str] = ""
    related_protocol_date: Optional[date] = None
    employer_organization: Optional[str] = ""
    business_secondary_activity_code_1: Optional[str] = ""
    business_secondary_activity_code_2: Optional[str] = ""
    business_secondary_activity_code_3: Optional[str] = ""
    business_secondary_activity_code_4: Optional[str] = ""
    comments: Optional[str] = ""

    def serialize(self):
        return {
            "f_aa_pararthmatos": self.business_branch_number,
            "f_rel_protocol": self.related_protocol_id,
            "f_rel_date": format_date(self.related_protocol_date),
            "f_ypiresia_sepe": self.sepe_service_code,
            "f_ergodotikh_organwsh": self.employer_organization,
            "f_kad_kyria": self.business_primary_activity_code,
            "f_kad_deyt_1": self.business_secondary_activity_code_1,
            "f_kad_deyt_2": self.business_secondary_activity_code_2,
            "f_kad_deyt_3": self.business_secondary_activity_code_3,
            "f_kad_deyt_4": self.business_secondary_activity_code_4,
            "f_kad_pararthmatos": self.business_branch_activity_code,
            "f_kallikratis_pararthmatos": self.kallikratis_municipal_code,
            "f_comments": self.comments,
            "f_afm_proswpoy": self.legal_representative_tax_identification_number,
            "Ergazomenoi": {
                "OvertimeErgazomenosDate": [
                    overtime.serialize() for overtime in self.employee_overtimes
                ]
            },
        }


@dataclass
class WorkdayDetails:
    """
    Represents details of an employee's workday

    Attributes:
        work_type (ScheduleWorkType): The type of an employee's work schedule
        start_time (time): The start time of the workday
        end_time (time): The end time of the workday
    """

    work_type: ScheduleWorkType
    start_time: time
    end_time: time

    def serialize(self):
        return {
            "f_type": get_ergani_work_type(self.work_type),
            "f_from": format_time(self.start_time),
            "f_to": format_time(self.end_time),
        }


@dataclass
class EmployeeDailySchedule:
    """
    Represents a daily schedule entry for an employee

    Attributes:
        employee_tax_identification_number (str): The employee's tax identification number
        employee_last_name (str): The employee's last name
        employee_first_name (str): The employee's first name
        schedule_date (date): The date of the schedule
        workday_details (List[WorkdayDetails]): A list of workday detail entries for the employee
    """

    employee_tax_identification_number: str
    employee_last_name: str
    employee_first_name: str
    schedule_date: date
    workday_details: List[WorkdayDetails] = field(default_factory=list)

    def serialize(self):
        return {
            "f_afm": self.employee_tax_identification_number,
            "f_eponymo": self.employee_last_name,
            "f_onoma": self.employee_first_name,
            "f_date": format_date(self.schedule_date),
            "ErgazomenosAnalytics": {
                "ErgazomenosWTOAnalytics": [
                    workday_detail.serialize()
                    for workday_detail in self.workday_details
                ]
            },
        }


@dataclass
class CompanyDailySchedule:
    """
    Represents daily schedule entries that are issued on a single business branch

    Attributes:
        business_branch_number (int): The number identifying the business branch
        start_date (Optional[date]): The start date of the schedule
        end_date (Optional[date]): The end date of the schedule period
        employee_schedules (List[EmployeeDailySchedule]): A list of daily schedules for employees
        related_protocol_id (Optional[str]): The ID of the related protocol
        related_protocol_date (Optional[date]): The date of the related protocol
        comments (Optional[str]): Additional comments regarding the daily schedule entries
    """

    business_branch_number: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    employee_schedules: List[EmployeeDailySchedule] = field(default_factory=list)
    related_protocol_id: Optional[str] = ""
    related_protocol_date: Optional[date] = None
    comments: Optional[str] = ""

    def serialize(self):
        return {
            "f_aa_pararthmatos": self.business_branch_number,
            "f_rel_protocol": self.related_protocol_id,
            "f_rel_date": format_date(self.related_protocol_date),
            "f_comments": self.comments,
            "f_from_date": format_date(self.start_date),
            "f_to_date": format_date(self.end_date),
            "Ergazomenoi": {
                "ErgazomenoiWTO": [
                    employee_schedule.serialize()
                    for employee_schedule in self.employee_schedules
                ]
            },
        }


@dataclass
class EmployeeWeeklySchedule:
    """
    Represents a weekly schedule entry for an employee

    Attributes:
        employee_tax_identification_number (str): The employee's tax identification number
        employee_last_name (str): The employee's last name
        employee_first_name (str): The employee's first name
        schedule_date (date): The date of the schedule
        workday_details (List[WorkdayDetails]): A list of workday detail entries for the week
    """

    employee_tax_identification_number: str
    employee_last_name: str
    employee_first_name: str
    schedule_date: date
    workday_details: List[WorkdayDetails] = field(default_factory=list)

    def serialize(self):
        return {
            "f_afm": self.employee_tax_identification_number,
            "f_eponymo": self.employee_last_name,
            "f_onoma": self.employee_first_name,
            "f_day": get_day_of_week(self.schedule_date),
            "ErgazomenosAnalytics": {
                "ErgazomenosWTOAnalytics": [
                    workday_detail.serialize()
                    for workday_detail in self.workday_details
                ]
            },
        }


@dataclass
class CompanyWeeklySchedule:
    """
    Represents weekly schedule entries that are issued on a single business branch

    Attributes:
        business_branch_number (int): The number identifying the business branch
        start_date (date): The start date of the weekly schedule
        end_date (date): The end date of the weekly schedule
        employee_schedules (List[EmployeeWeeklySchedule]): A list of weekly schedules for employees
        related_protocol_id (Optional[str]): The ID of the related protocol
        related_protocol_date (Optional[date]): The date of the related protocol
        comments (Optional[str]): Additional comments regarding the weekly schedule entries
    """

    business_branch_number: int
    start_date: date
    end_date: date
    employee_schedules: List[EmployeeWeeklySchedule] = field(default_factory=list)
    related_protocol_id: Optional[str] = ""
    related_protocol_date: Optional[date] = None
    comments: Optional[str] = ""

    def serialize(self):
        return {
            "f_aa_pararthmatos": self.business_branch_number,
            "f_rel_protocol": self.related_protocol_id,
            "f_rel_date": format_date(self.related_protocol_date),
            "f_comments": self.comments,
            "f_from_date": format_date(self.start_date),
            "f_to_date": format_date(self.end_date),
            "Ergazomenoi": {
                "ErgazomenoiWTO": [
                    employee_schedule.serialize()
                    for employee_schedule in self.employee_schedules
                ]
            },
        }


class SubmissionResponse(TypedDict):
    """
    Represents a submission response from the Ergani API

    Attributes:
        submission_id (str): The unique identifier of the submission
        protocol (str): The protocol associated with the submission
        submission_date (datetime): The datetime of the submission
    """

    submission_id: str
    protocol: str
    submission_date: datetime
