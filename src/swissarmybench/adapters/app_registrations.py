"""App registrations' files in the library (`app-registrations/<name>.toml` and `<name>.access.json`, written
atomically and only when their bytes change), and the read-only calls an access report makes: Microsoft's
sign-in (client credentials) and Power BI's REST reads (the workspaces it sees, their datasets, one COUNTROWS
through executeQueries: no row kept). The token lives in memory for the check only: never stored or logged.

POWERBI_LOGIN_URL and POWERBI_API_URL point the calls at a stand-in (tests), as the Power BI connection's do.

The other Microsoft kinds (MicrosoftProbe), each with its own scope and read-only: Azure SQL through
mssql-python (connect with the token, the databases it sees, SELECT TOP 0 on its tables: no row read),
Dataverse (WhoAmI, its security roles' names), SharePoint through Graph (the site, its lists and libraries:
names only), OneLake and Data Lake (one listing of the named path, not recursive). Their sign-in and
addresses move as the connections' own do: SWISSARMYBENCH_LOGIN_URL, DATAVERSE_LOGIN_URL,
SWISSARMYBENCH_GRAPH_URL, SWISSARMYBENCH_STORAGE_URL.
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

    def token(self, tenant: str, client: str, secret: str, scope: str = SCOPE, login: str = "") -> str:
        form = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "client_id": client, "client_secret": secret, "scope": scope}
        ).encode()
        answer = _call(f"{login or self.login}/{urllib.parse.quote(tenant)}/oauth2/v2.0/token", form)
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


def _login(kind: str) -> str:
    variable = "DATAVERSE_LOGIN_URL" if kind == "dataverse" else "SWISSARMYBENCH_LOGIN_URL"
    return os.environ.get(variable, "https://login.microsoftonline.com").rstrip("/")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


class MicrosoftProbe(PowerBIProbe):
    """The access report's reads for Azure SQL, Dataverse, SharePoint and the lakes, signed in as the
    registration with each kind's scope. Names only: never a row, a count or the token in an answer."""

    def ready(self, kind: str) -> str:
        """Why a kind's check cannot run here ("": it can): Azure SQL needs mssql-python in this Python."""
        if kind != "sqlserver":
            return ""
        import importlib

        try:
            importlib.import_module("mssql_python")
        except ImportError:
            return "mssql-python is not installed here, so the database is not reached from this computer"
        return ""

    def kind_token(self, kind: str, tenant: str, client: str, secret: str, scope: str) -> str:
        return self.token(tenant, client, secret, scope, _login(kind))

    def sql(
        self, token: str, server: str, database: str, tables: list[str]
    ) -> tuple[list[str], dict[str, str]]:
        """Connect with the token, the databases it sees, SELECT TOP 0 on each table: (databases, the tables
        refused with the server's words). Raises Refused when the connect itself is refused."""
        import importlib
        import struct

        try:
            driver = importlib.import_module("mssql_python")
        except ImportError as error:
            raise rules.Refused(rules.NOT_HERE, f"mssql-python is not installed here ({error})") from None
        text = f"Server={server};" + (f"Database={database};" if database else "") + "Encrypt=mandatory"
        sent = token.encode("utf-16-le")
        attrs = {1256: struct.pack(f"<I{len(sent)}s", len(sent), sent)}  # SQL_COPT_SS_ACCESS_TOKEN
        try:
            conn = driver.connect(text, attrs_before=attrs, timeout=TIMEOUT)
        except Exception as error:
            raise rules.Refused(0, str(error)[:2000]) from None
        refused: dict[str, str] = {}
        try:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT name FROM sys.databases ORDER BY name")
                databases = [str(r[0]) for r in cursor.fetchall()]
            except Exception as error:
                raise rules.Refused(0, str(error)[:2000]) from None
            for table in tables:
                quoted = ".".join("[" + p.replace("]", "]]") + "]" for p in table.split(".") if p)
                try:
                    cursor.execute(f"SELECT TOP 0 * FROM {quoted}")  # noqa: S608 (a quoted catalog name)
                    cursor.fetchall()
                except Exception as error:
                    refused[table] = str(error)[:300]
        finally:
            conn.close()
        return databases, refused

    def dataverse(self, token: str, url: str) -> list[str]:
        """WhoAmI, then its security roles' names. Raises Refused."""
        api = url.rstrip("/") + "/api/data/v9.2"
        me = _call(f"{api}/WhoAmI", headers=_bearer(token))
        user = str(me.get("UserId") or "")
        found = _call(
            f"{api}/systemusers({urllib.parse.quote(user)})/systemuserroles_association?$select=name",
            headers=_bearer(token),
        )
        return sorted(str(r.get("name")) for r in found.get("value", []) if r.get("name"))

    def sharepoint(self, token: str, site_url: str) -> tuple[list[str], list[str]]:
        """The site, then its lists' and libraries' names. Raises Refused."""
        graph = os.environ.get("SWISSARMYBENCH_GRAPH_URL", "https://graph.microsoft.com/v1.0").rstrip("/")
        parts = urllib.parse.urlsplit(site_url)
        site = _call(f"{graph}/sites/{parts.netloc}:{parts.path.rstrip('/')}", headers=_bearer(token))
        sid = urllib.parse.quote(str(site.get("id") or ""), safe=",")
        lists = _call(f"{graph}/sites/{sid}/lists?$select=id,displayName,list", headers=_bearer(token))
        drives = _call(f"{graph}/sites/{sid}/drives?$select=id,name", headers=_bearer(token))
        names = [
            str(item.get("displayName"))
            for item in lists.get("value", [])
            if not (item.get("list") or {}).get("hidden")
            and (item.get("list") or {}).get("template") != "documentLibrary"
        ]
        return sorted(names), sorted(str(d.get("name")) for d in drives.get("value", []))

    def lake(self, token: str, account: str, filesystem: str, directory: str) -> None:
        """One listing of the path (not recursive, its first page). Raises Refused."""
        moved = os.environ.get("SWISSARMYBENCH_STORAGE_URL")
        host = (
            "onelake.dfs.fabric.microsoft.com" if account == "onelake" else f"{account}.dfs.core.windows.net"
        )
        base = f"{moved.rstrip('/')}/{account}" if moved else f"https://{host}"
        query = urllib.parse.urlencode(
            {"resource": "filesystem", "recursive": "false", "directory": directory, "maxResults": "1"}
        )
        headers = _bearer(token) | {"x-ms-version": "2023-11-03"}
        _call(f"{base}/{urllib.parse.quote(filesystem)}?{query}", headers=headers)
