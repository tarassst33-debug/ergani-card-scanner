from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

from ergani.client import ErganiClient
from ergani.models import WorkCardMovement


class WorkCardMovementParseTests(TestCase):
    def test_parse_many_from_card_details(self) -> None:
        payload = {
            "Cards": {
                "Card": [
                    {
                        "f_aa": "0",
                        "Details": {
                            "CardDetails": [
                                {
                                    "f_afm": "123456789",
                                    "f_eponymo": "ΠΑΠΑΔΟΠΟΥΛΟΣ",
                                    "f_onoma": "ΓΕΩΡΓΙΟΣ",
                                    "f_type": "0",
                                    "f_reference_date": "2026-06-01",
                                    "f_date": "2026-06-01T09:15:00+03:00",
                                },
                                {
                                    "f_afm": "123456789",
                                    "f_eponymo": "ΠΑΠΑΔΟΠΟΥΛΟΣ",
                                    "f_onoma": "ΓΕΩΡΓΙΟΣ",
                                    "f_type": "1",
                                    "f_reference_date": "2026-06-01",
                                    "f_date": "2026-06-01T17:30:00+03:00",
                                },
                            ]
                        },
                    }
                ]
            }
        }

        movements = WorkCardMovement.parse_many(payload)

        self.assertEqual(len(movements), 2)
        self.assertEqual(movements[0].employee_tax_identification_number, "123456789")
        self.assertEqual(movements[0].movement_type, "DEPARTURE")
        self.assertEqual(movements[1].movement_type, "ARRIVAL")


class ErganiClientWorkCardQueryTests(TestCase):
    def test_get_work_card_movements_uses_configured_service(self) -> None:
        client = ErganiClient("username", "password", "https://example.test")
        response = Mock()
        response.json.return_value = {
            "EX_TEST": {
                "Details": {
                    "CardDetails": [
                        {
                            "f_afm": "987654321",
                            "f_eponymo": "ΛΑΜΠΡΟΣ",
                            "f_onoma": "ΝΙΚΟΣ",
                            "f_type": "0",
                            "f_reference_date": "2026-06-02",
                            "f_date": "2026-06-02T08:00:00",
                        }
                    ]
                }
            }
        }

        with patch.dict("os.environ", {"ERGANI_WORK_CARD_QUERY_SERVICE": "EX_TEST"}):
            with patch.object(
                client, "get_service_parameter_names", return_value=[]
            ):
                with patch.object(
                    client, "_execute_service", return_value=response
                ) as execute_mock:
                    movements, code = client.get_work_card_movements(
                        date_from=date(2026, 6, 1),
                        date_to=date(2026, 6, 2),
                    )

        self.assertEqual(code, "EX_TEST")
        self.assertEqual(len(movements), 1)
        execute_mock.assert_called_once()
        args, kwargs = execute_mock.call_args
        self.assertEqual(args[0], "EX_TEST")
