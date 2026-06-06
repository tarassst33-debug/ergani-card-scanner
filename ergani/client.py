import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import requests
from requests.models import Response

from ergani.auth import ErganiAuthentication
from ergani.exceptions import APIError, AuthenticationError
from ergani.models import (
    BusinessBranch,
    CompanyDailySchedule,
    CompanyOvertime,
    CompanyWeeklySchedule,
    CompanyWorkCard,
    Employee,
    EmployerDetails,
    SubmissionResponse,
    WorkCardMovement,
)
from ergani.utils import extract_error_message, normalize_base_url


class ErganiClient:
    """
    A client for interacting with the Ergani API

    Args:
        username str: The username for authentication with Ergani
        password str: The password for authentication with Ergani
        base_url str: The base URL of the Ergani API. Defaults to "https://eservices.yeka.gr/WebservicesAPI/Api".
    """

    def __init__(
        self,
        username: str,
        password: str,
        base_url: Optional[str] = "https://eservices.yeka.gr/WebservicesAPI/Api",
        user_type: Optional[str] = None,
    ) -> None:
        self.username = username
        self.password = password
        self.base_url = normalize_base_url(base_url)
        self.user_type = user_type
        self._service_parameter_names: Dict[str, List[str]] = {}

    def _request(
        self, method: str, endpoint: str, payload: Optional[Dict[str, Any]] = None
    ) -> Optional[Response]:
        """
        Sends a request to the specified endpoint using the given HTTP method and payload

        Args:
            method (str): The HTTP method to use for the request (e.g., 'GET', 'POST')
            endpoint (str): The API endpoint to which the request should be sent to
            payload (Optional[Dict[str, Any]]): The JSON-serializable dictionary to be sent as the request payload

        Returns:
            Optional[Response]: The response object from the requests library. Returns None for 204 No Content responses.

        Raises:
            Requests exceptions may be raised for network-related errors
        """

        normalized_endpoint = endpoint.lstrip("/")
        url = f"{self.base_url}/{normalized_endpoint}"
        auth = ErganiAuthentication(
            self.username, self.password, self.base_url, self.user_type
        )

        response = requests.request(
            method,
            url,
            json=payload,
            auth=auth,
        )

        return self._handle_response(response, payload)

    def _handle_response(
        self, response: Response, payload: Optional[Dict[str, Any]] = None
    ) -> Optional[Response]:
        """
        Handles the HTTP response, raising exceptions for error status codes and returning the response for successful ones

        Args:
            response (Response): The response object to handle
            payload (Optional[Dict[str, Any]]): The original request payload for inclusion in exceptions if needed

        Returns:
            Optional[Response]: The original response object for successful requests or None for 204 No Content responses

        Raises:
            APIError: An error occurred while communicating with the Ergani API
            AuthenticationError: Raised if there is an authentication error with the Ergani API
        """

        if response.status_code == 401:
            error_message = extract_error_message(response)
            raise AuthenticationError(message=error_message, response=response)

        if response.status_code == 204:
            return None

        try:
            response.raise_for_status()
            return response
        except requests.HTTPError:
            error_message = extract_error_message(response)
            raise APIError(message=error_message, response=response, payload=payload)

    def _execute_service(
        self, service_code: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[Response]:
        request_payload = {
            "ServiceCode": service_code,
            "Parameters": [
                {"ParameterName": name, "ParameterValue": value}
                for name, value in (parameters or {}).items()
            ],
        }

        return self._request("POST", "/WebServices/ExecuteService", request_payload)

    def _extract_submission_result(
        self, response: Optional[Response]
    ) -> List[SubmissionResponse]:
        """
        Extracts the submission result from the Ergani API response

        Args:
            response (Response): The response object from the Ergani API

        Returns:
            List[SubmissionResponse]: A list of submission responses parsed from the API response

        Raises:
            ValueError: If the response cannot be parsed into submission responses, indicating an unexpected format
        """

        if not response:
            return []

        data = response.json()
        submissions = []

        for submission in data:
            submission_date_str = submission["submitDate"]
            submission_date = datetime.strptime(submission_date_str, "%d/%m/%Y %H:%M")

            submission_response = SubmissionResponse(
                submission_id=submission["id"],
                protocol=submission["protocol"],
                sumbmission_date=submission_date,
            )
            submissions.append(submission_response)

        return submissions

    def submit_work_card(
        self, company_work_cards: List[CompanyWorkCard]
    ) -> List[SubmissionResponse]:
        """
        Submits work card records (check-in, check-out) for employees to the Ergani API

        Args:
            company_work_cards List[CompanyWorkCard]: A list of CompanyWorkCard instances to be submitted

        Returns:
            List[SubmissionResponse]: A list of SumbmissionResponse that were parsed from the API response

        Raises:
            APIError: An error occurred while communicating with the Ergani API
            AuthenticationError: Raised if there is an authentication error with the Ergani API
        """

        endpoint = "/Documents/WRKCardSE"

        request_payload = {
            "Cards": {
                "Card": [
                    company_card.serialize() for company_card in company_work_cards
                ]
            }
        }

        response = self._request("POST", endpoint, request_payload)

        return self._extract_submission_result(response)

    def submit_overtime(
        self, company_overtimes: List[CompanyOvertime]
    ) -> List[SubmissionResponse]:
        """
        Submits overtime records for employees to the Ergani API

        Args:
            company_overtimes List[CompanyOvertime]: A list of CompanyOvertime instances to be submitted

        Returns:
            List[SubmissionResponse]: A list of SumbmissionResponse that were parsed from the API response

        Raises:
            APIError: An error occurred while communicating with the Ergani API
            AuthenticationError: Raised if there is an authentication error with the Ergani API
        """

        endpoint = "/Documents/OvTime"

        request_payload = {
            "Overtimes": {
                "Overtime": [
                    company_overtime.serialize()
                    for company_overtime in company_overtimes
                ]
            }
        }

        response = self._request("POST", endpoint, request_payload)

        return self._extract_submission_result(response)

    def submit_daily_schedule(
        self, company_daily_schedules: List[CompanyDailySchedule]
    ) -> List[SubmissionResponse]:
        """
        Submits schedule records that are updated on a daily basis for employees to the Ergani API

        Args:
            company_daily_schedules List[CompanyDailySchedule]: A list of CompanyDailySchedule instances to be submitted

        Returns:
            List[SubmissionResponse]: A list of SumbmissionResponse that were parsed from the API response

        Raises:
            APIError: An error occurred while communicating with the Ergani API
            AuthenticationError: Raised if there is an authentication error with the Ergani API
        """

        endpoint = "/Documents/WTODaily"

        request_payload = {
            "WTOS": {
                "WTO": [schedule.serialize() for schedule in company_daily_schedules]
            }
        }

        response = self._request("POST", endpoint, request_payload)

        return self._extract_submission_result(response)

    def submit_weekly_schedule(
        self, company_weekly_schedules: List[CompanyWeeklySchedule]
    ) -> List[SubmissionResponse]:
        """
        Submits weekly schedule records for employees to the Ergani API

        Args:
            company_weekly_schedules List[CompanyWeeklySchedule]: A list of CompanyWeeklySchedule instances to be submitted

        Returns:
            List[SubmissionResponse]: A list of SumbmissionResponse that were parsed from the API response

        Raises:
            APIError: An error occurred while communicating with the Ergani API
            AuthenticationError: Raised if there is an authentication error with the Ergani API
        """

        endpoint = "/Documents/WTOWeek"

        request_payload = {
            "WTOS": {
                "WTO": [schedule.serialize() for schedule in company_weekly_schedules]
            }
        }

        response = self._request("POST", endpoint, request_payload)

        return self._extract_submission_result(response)

    def get_services_list(self) -> Optional[Response]:
        """
        Fetches the available services list from the Ergani API.

        Returns:
            Optional[Response]: The raw response returned by the services list endpoint.

        Raises:
            APIError: An error occurred while communicating with the Ergani API
            AuthenticationError: Raised if there is an authentication error with the Ergani API
        """
        last_error: APIError | None = None
        for endpoint in (
            "/WebServices/ServicesList",
            "/WebServices/serviceslist",
        ):
            try:
                return self._request("GET", endpoint, None)
            except APIError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    last_error = exc
                    continue
                raise
        if last_error is not None:
            raise last_error
        return None

    def get_branch_details(self) -> List[BusinessBranch]:
        """
        Fetches the authenticated employer's branch details from the Ergani API.

        Returns:
            List[BusinessBranch]: The parsed branch detail entries.

        Raises:
            APIError: An error occurred while communicating with the Ergani API
            AuthenticationError: Raised if there is an authentication error with the Ergani API
            ValueError: The response payload could not be parsed as a branch list
        """

        response = self._execute_service("EX_BASE_02")
        payload = None

        if response:
            try:
                payload = response.json()
            except ValueError as error:
                raise ValueError("EX_BASE_02 returned a non-JSON response") from error

        return BusinessBranch.parse_many(payload)

    def get_employer_details(self) -> EmployerDetails:
        """
        Fetches employer details from the Ergani API.

        Returns:
            EmployerDetails: Employer details parsed from the EX_BASE_01 response.

        Raises:
            APIError: An error occurred while communicating with the Ergani API
            AuthenticationError: Raised if there is an authentication error with the Ergani API
            ValueError: Raised if the query payload cannot be parsed into an employer details object
        """

        response = self._execute_service("EX_BASE_01")

        if response is None:
            return EmployerDetails.parse({})

        try:
            payload = response.json()
        except ValueError as error:
            raise ValueError("EX_BASE_01 returned a non-JSON response") from error

        return EmployerDetails.parse(payload)

    def get_service_parameter_names(self, service_code: str) -> List[str]:
        """
        Returns declared parameter names for an ExecuteService code (from ServicesList).
        """
        if service_code in self._service_parameter_names:
            return self._service_parameter_names[service_code]

        names: List[str] = []
        try:
            response = self.get_services_list()
        except (APIError, AuthenticationError):
            response = None
        if response is not None:
            try:
                services = response.json()
            except ValueError:
                services = []

            if isinstance(services, list):
                for service in services:
                    if not isinstance(service, dict):
                        continue
                    if service.get("name") != service_code:
                        continue
                    parameters = service.get("parameters") or []
                    if isinstance(parameters, list):
                        names = [
                            str(item.get("name"))
                            for item in parameters
                            if isinstance(item, dict) and item.get("name")
                        ]
                    break

        self._service_parameter_names[service_code] = names
        return names

    def _set_first_allowed_parameter(
        self,
        parameters: Dict[str, Any],
        allowed: set[str],
        candidates: List[str],
        value: Any,
    ) -> None:
        if value is None or value == "":
            return
        for key in candidates:
            if not allowed or key in allowed:
                parameters[key] = value
                return

    def _build_employee_service_parameters(
        self,
        service_code: str,
        *,
        branch_number: Optional[int] = None,
        afm: str = "",
        identity_number: str = "",
        first_name: str = "",
        last_name: str = "",
        father_name: str = "",
        current_status_only: bool = True,
        search: str = "",
        page: int = 0,
    ) -> Dict[str, Any]:
        allowed = set(self.get_service_parameter_names(service_code))
        parameters: Dict[str, Any] = {}

        self._set_first_allowed_parameter(
            parameters,
            allowed,
            ["Aa", "aa", "Param1", "BranchNumber", "f_aa"],
            branch_number,
        )
        self._set_first_allowed_parameter(
            parameters, allowed, ["Afm", "afm", "AFM"], afm.strip()
        )
        self._set_first_allowed_parameter(
            parameters,
            allowed,
            ["ArTautotitas", "ArTaxotitas", "IdentityNumber", "AriythmosTautotitas"],
            identity_number.strip(),
        )
        self._set_first_allowed_parameter(
            parameters, allowed, ["Onoma", "onoma", "f_onoma"], first_name.strip()
        )
        self._set_first_allowed_parameter(
            parameters, allowed, ["Eponymo", "eponymo", "f_eponymo"], last_name.strip()
        )
        self._set_first_allowed_parameter(
            parameters,
            allowed,
            ["OnomaPatros", "Patronymic", "PatrosOnoma", "onomaPatros"],
            father_name.strip(),
        )

        if search.strip() and not any(
            (
                afm.strip(),
                identity_number.strip(),
                first_name.strip(),
                last_name.strip(),
                father_name.strip(),
            )
        ):
            self._set_first_allowed_parameter(
                parameters, allowed, ["Search", "search", "Param2"], search.strip()
            )

        if current_status_only:
            self._set_first_allowed_parameter(
                parameters,
                allowed,
                [
                    "TrexousaKatastasi",
                    "CurrentStatus",
                    "OnlyActive",
                    "Current",
                    "IncludeCurrent",
                ],
                True,
            )
        else:
            self._set_first_allowed_parameter(
                parameters,
                allowed,
                ["IncludeInactive", "includeInactive", "Inactive", "AllStatuses"],
                True,
            )

        self._set_first_allowed_parameter(
            parameters, allowed, ["Page", "page"], page
        )

        return parameters

    def get_employees(
        self,
        branch_number: Optional[int] = None,
        *,
        afm: str = "",
        identity_number: str = "",
        first_name: str = "",
        last_name: str = "",
        father_name: str = "",
        current_status_only: bool = True,
        include_inactive: bool = False,
        search: str = "",
        service_code: str = "EX_BASE_05",
        max_pages: int = 50,
    ) -> List[Employee]:
        """
        Fetches employees from Ergani (EX_BASE_05 by default).

        Args:
            branch_number: Optional branch serial (Α/Α παραρτήματος).
            afm: Employee tax ID filter.
            identity_number: Identity document filter.
            first_name, last_name, father_name: Name filters (like Ergani portal).
            current_status_only: When True, only current employment (Τρέχουσα Κατάσταση).
            include_inactive: Legacy flag; when True, disables current_status_only.
            search: Legacy free-text filter if name fields are empty.
            service_code: ExecuteService code (defaults to EX_BASE_05).
            max_pages: Maximum pages to fetch when the API is paginated.

        Returns:
            List[Employee]: Parsed employee records.
        """
        if include_inactive:
            current_status_only = False

        employees: List[Employee] = []
        seen_afms: set[str] = set()

        for page in range(max_pages):
            parameters = self._build_employee_service_parameters(
                service_code,
                branch_number=branch_number,
                afm=afm,
                identity_number=identity_number,
                first_name=first_name,
                last_name=last_name,
                father_name=father_name,
                current_status_only=current_status_only,
                search=search,
                page=page,
            )
            if page > 0 and "Page" not in parameters and "page" not in parameters:
                break

            response = self._execute_service(service_code, parameters)
            if response is None:
                break

            try:
                payload = response.json()
            except ValueError as error:
                raise ValueError(
                    f"{service_code} returned a non-JSON response"
                ) from error

            page_employees = Employee.parse_many(payload)
            if not page_employees:
                break

            added = 0
            for employee in page_employees:
                afm = employee.tax_identification_number
                if not afm or afm in seen_afms:
                    continue
                seen_afms.add(afm)
                employees.append(employee)
                added += 1

            if added == 0:
                break

        return employees

    _WORK_CARD_SERVICE_KEYWORDS = (
        "κάρτα",
        "καρτα",
        "card",
        "wrk",
        "ημερολόγ",
        "ημερολογ",
        "απασχόλ",
        "απασχολ",
        "κίνησ",
        "kinisi",
        "έναρξ",
        "λήξη",
    )

    _WORK_CARD_SERVICE_FALLBACKS = (
        "EX_BASE_06",
        "EX_BASE_07",
        "EX_BASE_08",
        "EX_BASE_09",
        "EX_BASE_10",
        "EX_WRK_01",
        "EX_CARD_01",
        "EX_CARD_02",
    )

    def _discover_work_card_service_codes(self) -> List[str]:
        configured = os.environ.get("ERGANI_WORK_CARD_QUERY_SERVICE", "").strip()
        if configured:
            return [configured]

        codes: List[str] = []
        try:
            response = self.get_services_list()
        except (APIError, AuthenticationError):
            response = None
        if response is not None:
            try:
                services = response.json()
            except ValueError:
                services = []
            if isinstance(services, list):
                for service in services:
                    if not isinstance(service, dict):
                        continue
                    name = str(service.get("name") or "").strip()
                    if not name:
                        continue
                    blob = " ".join(
                        (
                            name,
                            str(service.get("description") or ""),
                        )
                    ).lower()
                    if any(keyword in blob for keyword in self._WORK_CARD_SERVICE_KEYWORDS):
                        codes.append(name)

        for fallback in self._WORK_CARD_SERVICE_FALLBACKS:
            if fallback not in codes:
                codes.append(fallback)
        return codes

    def _build_work_card_query_parameters(
        self,
        service_code: str,
        *,
        branch_number: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        employee_afm: str = "",
    ) -> Dict[str, Any]:
        allowed = set(self.get_service_parameter_names(service_code))
        parameters: Dict[str, Any] = {}

        self._set_first_allowed_parameter(
            parameters,
            allowed,
            ["Aa", "aa", "Param1", "BranchNumber", "f_aa"],
            branch_number,
        )
        self._set_first_allowed_parameter(
            parameters, allowed, ["Afm", "afm", "AFM"], employee_afm.strip()
        )

        if date_from and date_to:
            iso_from = date_from.isoformat()
            iso_to = date_to.isoformat()
            dmy_from = date_from.strftime("%d/%m/%Y")
            dmy_to = date_to.strftime("%d/%m/%Y")
            yyyymmdd_from = date_from.strftime("%Y%m%d")
            yyyymmdd_to = date_to.strftime("%Y%m%d")
            for keys, value in (
                (["DateFrom", "dateFrom", "HmApo", "hmApo", "FromDate", "apo"], iso_from),
                (["DateTo", "dateTo", "HmEos", "hmEos", "ToDate", "eos"], iso_to),
                (
                    ["HmerominiaApo", "HmerominiaEos", "HmerominiaAnaforasApo"],
                    iso_from,
                ),
                (["HmerominiaMexri", "HmerominiaAnaforasEos"], iso_to),
                (["ReportDateFrom", "StartDate"], iso_from),
                (["ReportDateTo", "EndDate"], iso_to),
                (["DateFromDMY", "Apo"], dmy_from),
                (["DateToDMY", "Eos"], dmy_to),
                (["SubmittedDateFrom"], yyyymmdd_from),
                (["SubmittedDateTo"], yyyymmdd_to),
            ):
                self._set_first_allowed_parameter(parameters, allowed, keys, value)

        if date_from and not any(
            key in parameters
            for key in (
                "DateFrom",
                "dateFrom",
                "HmApo",
                "ReportYear",
                "HmerominiaApo",
            )
        ):
            self._set_first_allowed_parameter(
                parameters,
                allowed,
                ["ReportYear"],
                str(date_from.year),
            )
            self._set_first_allowed_parameter(
                parameters,
                allowed,
                ["ReportMonth"],
                str(date_from.month),
            )

        return parameters

    def get_work_card_movements(
        self,
        *,
        branch_number: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        employee_afm: str = "",
        service_code: str = "",
    ) -> tuple[List[WorkCardMovement], str]:
        """
        Fetch work card punches from Ergani ExecuteService.

        Returns movements and the service code that produced them.
        Set ERGANI_WORK_CARD_QUERY_SERVICE to force a specific service.
        """
        codes = [service_code] if service_code else self._discover_work_card_service_codes()
        errors: List[str] = []

        for code in codes:
            parameters = self._build_work_card_query_parameters(
                code,
                branch_number=branch_number,
                date_from=date_from,
                date_to=date_to,
                employee_afm=employee_afm,
            )
            try:
                response = self._execute_service(code, parameters)
            except (APIError, AuthenticationError) as exc:
                errors.append(f"{code}: {exc}")
                continue

            if response is None:
                errors.append(f"{code}: κενή απάντηση")
                continue

            try:
                payload = response.json()
            except ValueError as exc:
                errors.append(f"{code}: μη έγκυρο JSON")
                continue

            movements = WorkCardMovement.parse_many(payload)
            if movements:
                return movements, code

            errors.append(f"{code}: δεν βρέθηκαν χτυπήματα")

        hint = (
            "Το Ergani δεν επέστρεψε χτυπήματα κάρτας για αυτό το διάστημα. "
            "Άνοιξε «Λίστα υπηρεσιών» για να βρεις τον σωστό κωδικό και όρισε "
            "ERGANI_WORK_CARD_QUERY_SERVICE στο .env, ή δες τα χτυπήματα που "
            "έχουν καταχωρηθεί μέσω αυτής της εφαρμογής."
        )
        if errors:
            hint = f"{hint} Δοκιμές: {'; '.join(errors[:4])}"
        raise ValueError(hint)
