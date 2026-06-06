import os
from typing import Optional

import requests
from requests.auth import AuthBase
from requests.models import PreparedRequest

from ergani.exceptions import AuthenticationError
from ergani.utils import extract_error_message, normalize_base_url


class ErganiAuthentication(AuthBase):
    """
    Authentication handler for the Ergani API
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
        self.user_type = user_type or os.environ.get("ERGANI_USER_TYPE", "02")
        self.access_token = self._authenticate()

    def __call__(self, request: PreparedRequest) -> PreparedRequest:
        request.headers["Authorization"] = f"Bearer {self.access_token}"
        return request

    def _authenticate(self) -> str:
        # Official docs: "02" = Ergani portal; "01" = external integrator; "03" = EFKA projects.
        payload = {
            "Username": self.username,
            "Password": self.password,
            "UserType": self.user_type,
        }

        response = requests.post(f"{self.base_url}/Authentication", json=payload)

        if response.status_code != 200:
            error_message = extract_error_message(response)
            raise AuthenticationError(message=error_message, response=response)

        try:
            token = response.json()["accessToken"]
        except (KeyError, TypeError, ValueError) as error:
            error_message = extract_error_message(response)

            if not error_message:
                preview = (
                    response.text.strip().splitlines()[0][:200] if response.text else ""
                )
                error_message = (
                    preview or "Authentication response did not include an access token"
                )

            raise AuthenticationError(
                message=error_message, response=response
            ) from error

        return token
