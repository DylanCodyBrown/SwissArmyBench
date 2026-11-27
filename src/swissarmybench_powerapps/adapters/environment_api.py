"""The environment's connectivity service: a connector's definition (operations, inputs, outputs), read the
way the Power Apps CLI itself reads it (`GET https://api.powerplatform.com/connectivity/connectors/<name>
?api-version=1&$filter=environment eq '<id>'`, its `properties.swagger`), with the Power Platform CLI's
own sign-in (`pac auth token`: a Power Platform API token for the selected profile).

The token is held in memory for this one request and never logged, shown, written or put on a command
line. Called only on the user's action (or the agent's command): never in the background.
`SWISSARMYBENCH_POWERPLATFORM_API` points at a stand-in (tests only).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE = "https://api.powerplatform.com"
TIMEOUT_SECONDS = 30.0


class EnvironmentApiError(Exception):
    """The service could not be asked, or did not answer with a definition (said plainly)."""


def _base() -> str:
    return os.environ.get("SWISSARMYBENCH_POWERPLATFORM_API", DEFAULT_BASE).rstrip("/")


def connector_address(name: str, environment_id: str) -> str:
    query = "api-version=1&$filter=" + urllib.parse.quote(f"environment eq '{environment_id}'", safe="=")
    return f"{_base()}/connectivity/connectors/{urllib.parse.quote(name, safe='')}?{query}"


def fetch_connector(name: str, environment_id: str, token: str) -> dict[str, Any]:
    """The service's answer for one connector (its properties.swagger is the definition)."""
    request = urllib.request.Request(  # noqa: S310 (https, or a test's stand-in)
        connector_address(name, environment_id),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as answer:  # noqa: S310
            data = json.loads(answer.read(20_000_000).decode("utf-8"))
    except urllib.error.HTTPError as error:
        words = {
            401: "the sign-in was refused (pac auth create signs in again)",
            403: "not allowed",
            404: "no such connector",
        }
        raise EnvironmentApiError(
            f"The environment's connectors service answered {error.code}: "
            f"{words.get(error.code, error.reason)}."
        ) from None
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise EnvironmentApiError(
            f"The environment's connectors service could not be reached: {error}"
        ) from None
    if not isinstance(data, dict):
        raise EnvironmentApiError("The environment's connectors service did not answer with a connector.")
    return data
