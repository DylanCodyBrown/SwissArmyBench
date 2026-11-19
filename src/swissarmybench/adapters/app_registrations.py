"""App registrations' files in the library (`app-registrations/<name>.toml` and `<name>.access.json`, written
atomically and only when their bytes change), and the read-only calls an access report makes: Microsoft's
sign-in (client credentials) and Power BI's REST reads (the workspaces it sees, their datasets, one COUNTROWS
through executeQueries: no row kept). The token lives in memory for the check only: never stored or logged.

POWERBI_LOGIN_URL and POWERBI_API_URL point the calls at a stand-in (tests), as the Power BI connection's do.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench.domain import app_registrations as rules

SCOPE = "https://analysis.windows.net/powerbi/api/.default"
TIMEOUT = 30


class RegistrationFiles:
    def __init__(self, root: Callable[[], Path], ensure: Callable[[], Any] = lambda: None) -> None:
        self._root = root
        self._ensure = ensure

    def folder(self) -> Path:
        return self._root() / rules.FOLDER

    def all(self) -> list[rules.Registration]:
        out = []
        for path in sorted(self.folder().glob("*.toml")) if self.folder().is_dir() else []:
            try:
                out.append(rules.read(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):  # a broken file is left alone, not listed
                continue
        return out

    def save(self, reg: rules.Registration) -> bool:
        self._ensure()
        self.folder().mkdir(parents=True, exist_ok=True)
        return bool(
            write_atomic(self.folder() / rules.file_name(reg.name), rules.write(reg), if_changed=True)
        )

    def remove(self, name: str) -> bool:
        gone = False
        for suffix in (".toml", ".access.json"):
            path = self.folder() / rules.file_name(name).replace(".toml", suffix)
            if path.exists():
                path.unlink()
                gone = True
        return gone

    def report(self, name: str) -> rules.Report | None:
        path = self.folder() / rules.file_name(name).replace(".toml", ".access.json")
        try:
            return rules.read_report(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save_report(self, report: rules.Report) -> bool:
        self.folder().mkdir(parents=True, exist_ok=True)
        path = self.folder() / rules.file_name(report.registration).replace(".toml", ".access.json")
        return bool(write_atomic(path, rules.write_report(report), if_changed=True))


def _call(url: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(url, data=data, headers=headers or {})  # noqa: S310 (https or a stand-in)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310
            return json.loads(answer.read() or b"{}")
    except urllib.error.HTTPError as error:
        raise rules.Refused(error.code, error.read().decode("utf-8", "replace")[:2000]) from None


class PowerBIProbe:
    """The access report's Power BI reads, signed in as the registration."""

    def __init__(self) -> None:
        self.login = os.environ.get("POWERBI_LOGIN_URL", "https://login.microsoftonline.com").rstrip("/")
        self.api = os.environ.get("POWERBI_API_URL", "https://api.powerbi.com").rstrip("/")

    def token(self, tenant: str, client: str, secret: str) -> str:
        form = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "client_id": client, "client_secret": secret, "scope": SCOPE}
        ).encode()
        answer = _call(f"{self.login}/{urllib.parse.quote(tenant)}/oauth2/v2.0/token", form)
        return str(answer.get("access_token") or "")

    def workspaces(self, token: str) -> list[dict[str, str]]:
        answer = _call(f"{self.api}/v1.0/myorg/groups", headers={"Authorization": f"Bearer {token}"})
        return [{"id": str(w.get("id")), "name": str(w.get("name"))} for w in answer.get("value", [])]

    def datasets(self, token: str, workspace: str) -> list[dict[str, str]]:
        url = f"{self.api}/v1.0/myorg/groups/{urllib.parse.quote(workspace)}/datasets"
        answer = _call(url, headers={"Authorization": f"Bearer {token}"})
        return [{"id": str(d.get("id")), "name": str(d.get("name"))} for d in answer.get("value", [])]

    def can_query(self, token: str, workspace: str, dataset: str, table: str) -> None:
        """One COUNTROWS through executeQueries; its answer is not kept. Raises Refused."""
        url = f"{self.api}/v1.0/myorg/groups/{workspace}/datasets/{dataset}/executeQueries"
        dax = 'EVALUATE ROW("n", COUNTROWS(\'' + table.replace("'", "''") + "'))"
        body = json.dumps(
            {"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}}
        ).encode()
        _call(url, body, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
