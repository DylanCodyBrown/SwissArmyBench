"""The access report reaches the other Microsoft kinds, read-only (the owner's G): Azure SQL (connect, the
databases it sees, SELECT TOP 0 on its tables) against the mssql-python stand-in of tests/test_sql_server.py,
Dataverse (WhoAmI, its roles' names) against tests/dataverse_standin.py, SharePoint (the site, its lists and
libraries) and OneLake and Data Lake (a listing of the named path) against tests/lake_standins.py. And a
connection of each of those kinds re-pointed to sign in with an app registration (signed_in_with). Made-up
values only; no secret or token is ever answered or kept."""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain import app_registrations as rules
from swissarmybench.domain import dataverse, lakes, sharepoint, sql_server
from swissarmybench.domain.blades import apply_settings, detect_settings
from swissarmybench.server.blade_templates import BY_ID
from tests import dataverse_standin as crm
from tests import lake_standins as lake
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring
from tests.test_sql_server import Error, FakeServer

DATA = {"name": "Contoso data", "tenant": "DATA_TENANT", "client": "DATA_CLIENT", "secret": "DATA_SECRET"}
CRM = {"name": "Contoso CRM", "tenant": "CRM_TENANT", "client": "CRM_CLIENT", "secret": "CRM_SECRET"}


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture
def standins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, Any, FakeServer]]:
    root = tmp_path / "lake"
    lake.make_lake(root)
    storage = lake.StandIn(root).start()
    environment = crm.StandIn().start()
    for name, value in (storage.environment() | environment.environment()).items():
        monkeypatch.setenv(name, value)
    # Power BI's reads go to the lake stand-in too (it knows no workspace): never to Microsoft.
    monkeypatch.setenv("POWERBI_LOGIN_URL", storage.url)
    monkeypatch.setenv("POWERBI_API_URL", storage.url)
    server = FakeServer()
    module = types.ModuleType("mssql_python")
    module.connect = server.connect  # type: ignore[attr-defined]
    module.Error = Error  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mssql_python", module)
    yield storage, environment, server
    storage.stop()
    environment.stop()


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def _placed(code: str, values: dict[str, str]) -> str:
    found = {s.key: s.id for s in detect_settings(code)}
    return apply_settings(code, {found[k]: {"text": v} for k, v in values.items() if k in found})


def test_each_kind_signs_in_with_the_registration_and_keeps_its_place() -> None:
    reg = rules.check(DATA)
    starters = {
        "sqlserver": _placed(sql_server.code("sql_login", "sql01"), {"database": "SalesDb"}),
        "dataverse": _placed(dataverse.MANAGED, {"url": "https://made-up.crm.dynamics.com"}),
        "sharepoint": _placed(
            sharepoint.LISTS_SIGN_INS[-1][2], {"site_url": "https://made-up.sharepoint.com/sites/x"}
        ),
        "sharepoint_docs": sharepoint.DOCS_SIGN_INS[-1][2],
        "datalake": _placed(
            lakes.DATALAKE_SIGN_INS[-1][2], {"account": "madeupstore", "container": "${LAKE_BOX}"}
        ),
        "onelake": lakes.ONELAKE_SIGN_INS[-1][2],
        "delta": lakes.DELTA_SIGN_INS[0][2],
    }
    for kind, code in starters.items():
        made = rules.signed_in_with(kind, code, reg)
        assert made is not None, kind
        keys = {s.key: s.text for s in detect_settings(made)}
        assert keys["tenant_id"] == "${DATA_TENANT}" and keys["client_id"] == "${DATA_CLIENT}", kind
        assert 'os.environ["DATA_SECRET"]' in made and 'secret("client secret")' not in made, kind
    sql = {
        s.key: s.text
        for s in detect_settings(rules.signed_in_with("sqlserver", starters["sqlserver"], reg) or "")
    }
    assert sql["server"] == "sql01" and sql["database"] == "SalesDb"
    box = {
        s.key: s.text
        for s in detect_settings(rules.signed_in_with("datalake", starters["datalake"], reg) or "")
    }
    assert box["container"] == "${LAKE_BOX}"  # a variable stays a variable
    assert rules.signed_in_with("delta", lakes.DELTA_LOCAL, reg) is None  # a folder: no app registration
    assert rules.signed_in_with("postgres", "conn = None", reg) is None
    assert rules.lake_place("delta", {"root": "abfss://box@acct.dfs.core.windows.net/lake"}) == (
        "acct",
        "box",
        "lake",
    )


def _connection(client: Any, name: str, template: str, code: str) -> None:
    starter = BY_ID[template]
    body = {
        "name": name,
        "kind": starter.kind or "sql",
        "template": template,
        "dialect": starter.dialect or template,
    }
    ok(client.post("/connections", json=body | {"code": code}, headers=AUTH))


def test_the_access_report_reaches_azure_sql_dataverse_sharepoint_and_the_lakes(
    tmp_path: Path, standins: tuple[Any, Any, FakeServer]
) -> None:
    _storage, environment, server = standins
    server.result = ([("name", str)], [("SalesDb",), ("master",)])
    with make_client(tmp_path) as client:
        ctx: Any = client.app.state.ctx  # type: ignore[attr-defined]

        async def tables(name: str) -> list[tuple[str, str, str]]:
            return [("SalesDb", "dbo", "Sales")] if name == "Sales SQL" else []

        ctx.app_registrations.tables_of = tables
        for name, value, where in (
            ("DATA_TENANT", lake.TENANT, "value"),
            ("DATA_CLIENT", lake.CLIENT, "value"),
            ("DATA_SECRET", lake.SECRET, "keyring"),
            ("CRM_TENANT", crm.TENANT, "value"),
            ("CRM_CLIENT", crm.CLIENT, "value"),
            ("CRM_SECRET", crm.SECRET, "keyring"),
        ):
            ok(client.put("/variables", json={"name": name, "value": value, "from": where}, headers=AUTH))
        data, people = rules.check(DATA), rules.check(CRM)
        ok(client.post("/app-registrations", json=DATA, headers=AGENT))
        ok(client.post("/app-registrations", json=CRM, headers=AGENT))
        site = f"https://{lake.SITE_HOST}{lake.SITE_PATH}"
        made = {
            "Sales SQL": (
                "azuresql",
                _placed(
                    sql_server.code("sql_login", "made-up.database.windows.net"), {"database": "SalesDb"}
                ),
                data,
            ),
            "Team site": ("sharepoint", _placed(sharepoint.LISTS, {"site_url": site}), data),
            "Sales lake": (
                "datalake",
                _placed(
                    lakes.DATALAKE_SIGN_INS[0][2],
                    {"account": lake.ACCOUNT, "container": lake.CONTAINER, "folder_in_container": "lake"},
                ),
                data,
            ),
            "Sales house": (
                "onelake",
                _placed(
                    lakes.ONELAKE_SIGN_INS[0][2], {"workspace": lake.WORKSPACE, "item": "Sales.Lakehouse"}
                ),
                data,
            ),
            "CRM": ("dataverse", _placed(dataverse.MANAGED, {"url": environment.url}), people),
        }
        for name, (template, code, reg) in made.items():
            _connection(client, name, template, rules.signed_in_with(template, code, reg) or "")

        report = ok(client.post("/app-registrations/Contoso%20data/check", headers=AGENT))["report"]
        by = {(i.get("connection"), i["target"]): i for i in report["items"]}
        assert by[("Sales SQL", "SalesDb on made-up.database.windows.net")]["mark"] == "✓"
        assert by[("Sales SQL", "databases it sees: SalesDb, master")]["mark"] == "✓"
        assert by[("Sales SQL", "dbo.Sales")]["mark"] == "✓"
        assert any(s.startswith("SELECT TOP 0 * FROM [dbo].[Sales]") for s, _ in server.statements)
        assert by[("Team site", site)]["mark"] == "✓"
        assert by[("Team site", "lists: Customers, Tasks")]["mark"] == "✓"
        assert by[("Team site", "libraries: Documents")]["mark"] == "✓"
        assert by[("Sales lake", f"{lake.ACCOUNT}/{lake.CONTAINER}/lake")]["mark"] == "✓"
        assert by[("Sales house", f"{lake.WORKSPACE}/Sales.Lakehouse")]["mark"] == "✓"
        text = str(report)
        assert lake.SECRET not in text and lake.TOKEN not in text
        line = ok(client.get("/connections/Team%20site/access", headers=AGENT))["access"][0]["line"]
        assert line.startswith("✓ 4")  # the sign-in, the site, its lists and its libraries

        crm_report = ok(client.post("/app-registrations/Contoso%20CRM/check", headers=AGENT))["report"]
        by = {(i.get("connection"), i["target"]): i for i in crm_report["items"]}
        assert by[("CRM", environment.url)]["mark"] == "✓"
        assert by[("CRM", "roles: Basic User, Sales Reader")]["mark"] == "✓"
        assert crm.SECRET not in str(crm_report) and crm.TOKEN not in str(crm_report)

        # Refusals in plain words with their fix: a table the database refuses, a path that is not there.
        answer = server.answer

        def refusing(sql: str, params: tuple[Any, ...], cursor: Any) -> Any:
            if sql.startswith("SELECT TOP 0"):
                return Error("The SELECT permission was denied on the object 'Sales'.")
            return answer(sql, params, cursor)

        server.answer = refusing  # type: ignore[method-assign]
        ok(
            client.put(
                "/variables", json={"name": "LAKE_DIR", "value": "nowhere", "from": "value"}, headers=AUTH
            )
        )
        moved = _placed(
            lakes.DATALAKE_SIGN_INS[0][2],
            {"account": lake.ACCOUNT, "container": lake.CONTAINER, "folder_in_container": "${LAKE_DIR}"},
        )
        _connection(client, "Gone lake", "datalake", rules.signed_in_with("datalake", moved, data) or "")
        report = ok(client.post("/app-registrations/Contoso%20data/check", headers=AGENT))["report"]
        by = {(i.get("connection"), i["target"]): i for i in report["items"]}
        assert by[("Sales SQL", "dbo.Sales")]["mark"] == "✗"
        assert by[("Sales SQL", "dbo.Sales")]["fix"] == "Grant it SELECT on the table"
        gone = by[("Gone lake", f"{lake.ACCOUNT}/{lake.CONTAINER}/nowhere")]
        assert gone["mark"] == "✗" and gone["reason"] == "the path does not exist"
