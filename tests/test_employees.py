from unittest import TestCase

from ergani.client import ErganiClient
from ergani.models import Employee


class EmployeeParseTests(TestCase):
    def test_parse_many_from_ex_base_05_payload(self) -> None:
        payload = {
            "EX_BASE_05": {
                "Ergazomenoi": [
                    {
                        "Afm": "162070871",
                        "Onoma": "ΔΗΜΗΤΡΙΟΣ",
                        "Eponymo": "ΓΕΩΡΓΑΝΤΑΣ",
                        "Amka": "15079202360",
                        "Aa": 0,
                        "StatusDescription": "Έναρξη απασχόλησης",
                    },
                    {
                        "Afm": "999999999",
                        "Onoma": "ΜΑΡΙΑ",
                        "Eponymo": "ΠΑΠΑ",
                    },
                ]
            }
        }

        employees = Employee.parse_many(payload)

        self.assertEqual(len(employees), 2)
        self.assertEqual(employees[0].tax_identification_number, "162070871")
        self.assertEqual(employees[0].first_name, "ΔΗΜΗΤΡΙΟΣ")
        self.assertEqual(employees[0].last_name, "ΓΕΩΡΓΑΝΤΑΣ")
        self.assertEqual(employees[0].social_security_number, "15079202360")
        self.assertEqual(employees[0].branch_number, 0)

    def test_parse_nested_dates_and_father_name(self) -> None:
        payload = {
            "Afm": "123456789",
            "Onoma": "ΙΩΑΝΝΗΣ",
            "Eponymo": "ΖΙΩΡΗΣ",
            "Relations": [
                {
                    "OnomaPatros": "ΚΩΝΣΤΑΝΤΙΝΟΣ",
                    "f_from_date": "2023-11-23",
                    "Aa": 0,
                }
            ],
        }
        employee = Employee.parse(payload)
        self.assertEqual(employee.father_name, "ΚΩΝΣΤΑΝΤΙΝΟΣ")
        self.assertEqual(employee.date_from, "23/11/2023")
        self.assertEqual(employee.branch_number, 0)

    def test_build_employee_parameters_only_uses_declared_names(self) -> None:
        client = ErganiClient("user", "pass", "https://example.com/api")
        client._service_parameter_names["EX_BASE_05"] = ["Aa", "Search"]

        params = client._build_employee_service_parameters(
            "EX_BASE_05",
            branch_number=1,
            search="ΓΕΩ",
            current_status_only=False,
            page=0,
        )

        self.assertEqual(params, {"Aa": 1, "Search": "ΓΕΩ"})
