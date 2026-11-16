"""The Dataverse connection (domain/dataverse.py), against a stand-in on this computer
(tests/dataverse_standin.py): no real tenant is reached, and every value is made up. Its tables are read
through the Web API (the metadata as the catalog, OData reads with paging and choice labels), SQL goes
through the read-only SQL endpoint (TDS), which cannot run here: its connection string, its token and
its refusals are checked with a stand-in for pyodbc."""

from __future__ import annotations

import json
import sys
import types
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters.blade_run import BladeRunError, run_code
from swissarmybench.client import sql_cell
from swissarmybench.domain import dataverse, errors
from swissarmybench.domain.blades import detect_settings, read_blade, read_code
from swissarmybench.domain.catalogs import select_sql
from swissarmybench.domain.connections import signs_in_interactively
from swissarmybench.server.blade_templates import BY_ID
from tests import dataverse_standin as made_up
from tests.conftest import AGENT, AUTH
from tests.fake_keyring import memory_keyring

NOT_TO_BE_SEEN = (made_up.SECRET, made_up.TOKEN, made_up.IDENTITY_HEADER)
STARTERS = Path(__file__).resolve().parents[1] / "src" / "swissarmybench" / "starters"
VAULT_CODE = f"""values = {{"crm-client-secret": "{made_up.SECRET}", "warehouse-password": "made-up"}}


def names():
    return list(values)


def get(name):
    return values[name]
"""


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


@pytest.fixture
def standin(monkeypatch: pytest.MonkeyPatch) -> Iterator[made_up.StandIn]:
    """Dataverse and Microsoft's sign-ins, stood in for on this computer (a child process gets the
    variables too)."""
    running = made_up.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    yield running
    running.stop()


def app_code(standin: made_up.StandIn) -> str:
    """The app registration's code, filled in for the stand-in's environment."""
    return (
        dataverse.APP.replace("https://your-org.crm.dynamics.com", standin.url)
        .replace("my-tenant-id", made_up.TENANT)
        .replace("my-client-id", made_up.CLIENT)
    )


def connect(standin: made_up.StandIn) -> Any:
    conn, _ = run_code(app_code(standin), "conn", {"client secret": made_up.SECRET}, "Sales CRM")
    return conn


def saved_connection(client: TestClient, standin: made_up.StandIn, **more: Any) -> str:
    """The vault, then a Dataverse connection whose client secret is that vault's entry."""
    vault: dict[str, Any] = {"name": "Team vault", "kind": "vault", "template": "azure_key_vault"}
    vault |= {"variable": "get", "code": VAULT_CODE, "vault_all": True, "vault_mapping": []}
    assert client.post("/connections", json=vault, headers=AUTH).status_code == 200
    body = {
        "code": app_code(standin),
        "secret": "client secret",
        "from": "vault",
        "vault": "Team vault",
        "vault_secret": "crm-client-secret",
    }
    code = client.post("/connections/source", json=body, headers=AUTH).json()["code"]
    template = BY_ID["dataverse"].to_json()
    saved = {"name": "Sales CRM", "kind": "sql", "template": "dataverse", "dialect": "dataverse"}
    saved |= {"code": code, "variable": "conn", "catalog": template["catalog"]} | more
    answer = client.post("/connections", json=saved, headers=AUTH)
    assert answer.status_code == 200, answer.text
    return str(code)


# ===== the form =====


def test_the_form_asks_for_the_address_and_signs_in_three_ways(client: TestClient) -> None:
    types_ = {t["id"]: t for t in client.get("/connections/types", headers=AUTH).json()["types"]}
    form = types_["dataverse"]
    assert (form["label"], form["connection"], form["dialect"]) == ("Dataverse", "database", "dataverse")
    assert [(f["name"], f["value"], f["placeholder"]) for f in form["fields"]] == [
        ("address", "https://your-org.crm.dynamics.com", True)
    ]
    assert [w["label"] for w in form["sign_ins"]] == [
        "As you (Azure command line or browser)",
        "Managed identity (in Azure: a Function App, App Service or VM)",
        "App registration, its secret from a key vault",
    ]
    codes = [w["code"] for w in form["sign_ins"]]
    for at, way in enumerate(form["sign_ins"]):  # each way's mark is in its own code only
        assert [way["mark"] in c for c in codes].index(True) == at and sum(
            way["mark"] in c for c in codes
        ) == 1
    assert form["code"] == dataverse.YOU and form["secrets"] == []
    assert form["secrets_from"] == "vault only"
    assert form["catalog"] == {"language": "python", "command": "catalog = conn.catalog()"}
    # Its packages, offered as the other connections offer theirs: azure-identity, and pyodbc for SQL.
    assert {p["pip"] for p in form["packages"]} >= {"azure-identity", "pyodbc"}


def test_each_way_to_sign_in_asks_only_for_what_it_needs() -> None:
    assert [s.name for s in detect_settings(dataverse.YOU)] == ["address"]
    assert [s.key for s in detect_settings(dataverse.MANAGED)] == ["url", "client_id"]
    assert [s.key for s in detect_settings(dataverse.APP)] == ["url", "tenant_id", "client_id"]
    app = read_code(dataverse.APP)
    assert app.secrets == ["client secret"] and app.variable == "conn"
    assert read_code(dataverse.MANAGED).secrets == [] and read_code(dataverse.YOU).secrets == []
    assert "azure.identity" in read_code(dataverse.YOU).imports
    assert "azure.identity" not in read_code(dataverse.MANAGED).imports + read_code(dataverse.APP).imports
    # As you may open a browser window: its catalog waits for first use, never at start-up.
    assert signs_in_interactively(dataverse.YOU)
    assert not signs_in_interactively(dataverse.MANAGED) and not signs_in_interactively(dataverse.APP)


def test_the_client_secret_is_never_typed_into_the_app(client: TestClient, standin: made_up.StandIn) -> None:
    template = BY_ID["dataverse"].to_json()
    draft = {"name": "Sales CRM", "kind": "sql", "template": "dataverse", "dialect": "dataverse"}
    draft |= {"code": app_code(standin), "variable": "conn", "catalog": template["catalog"]}
    typed = draft | {"secrets": {"client secret": made_up.SECRET}}
    for path in ("/connections/test", "/connections"):
        refused = client.post(path, json=typed, headers=AGENT)
        assert refused.status_code in (400, 422) and "comes from a key vault" in refused.text
        assert made_up.SECRET not in refused.text
    saved_connection(client, standin)
    refused = client.put("/blades/Sales%20CRM/secrets", json={"client secret": made_up.SECRET}, headers=AUTH)
    assert refused.status_code in (400, 422) and "never saved here" in refused.text


# ===== signing in =====


def test_an_app_registration_signs_in_with_the_environments_own_scope(standin: made_up.StandIn) -> None:
    conn = connect(standin)
    token = next(r for r in standin.requests if r["what"] == "token")
    assert token["tenant"] == made_up.TENANT
    assert token["form"] == {
        "grant_type": "client_credentials",
        "client_id": made_up.CLIENT,
        "client_secret": made_up.SECRET,
        "scope": f"{standin.url}/.default",
    }
    assert standin.gets()[0]["path"] == "/api/data/v9.2/WhoAmI"  # it reached the environment at once
    assert conn.access_token() == made_up.TOKEN
    assert len([r for r in standin.requests if r["what"] == "token"]) == 1  # signed in once


def test_a_managed_identity_signs_in_by_azures_own_request(standin: made_up.StandIn) -> None:
    code = dataverse.MANAGED.replace("https://your-org.crm.dynamics.com", standin.url)
    conn, _ = run_code(code, "conn", {}, "Sales CRM")
    asked = next(r for r in standin.requests if r["what"] == "managed identity")
    assert asked["query"] == {"api-version": "2019-08-01", "resource": standin.url}
    assert conn.tables()[0]["table"] == "account"
    with_client = code.replace('client_id = ""', 'client_id = "made-up-identity-0007"')
    run_code(with_client, "conn", {}, "Sales CRM")
    assert [r for r in standin.requests if r["what"] == "managed identity"][-1]["query"]["client_id"] == (
        "made-up-identity-0007"
    )


def test_refusals_are_said_plainly_and_never_hold_the_secret(
    standin: made_up.StandIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(BladeRunError) as wrong:
        run_code(app_code(standin), "conn", {"client secret": "made-up-wrong-secret"}, "Sales CRM")
    message = str(wrong.value)
    assert "The sign-in was refused (401): AADSTS7000215" in message and "client secret" in message
    assert "made-up-wrong-secret" not in message
    plain = app_code(standin).replace(standin.url, standin.url.replace("http://", "ftp://"))
    with pytest.raises(BladeRunError, match=r"address is https://<name>\.crm\.dynamics\.com"):
        run_code(plain, "conn", {"client secret": made_up.SECRET}, "Sales CRM")
    # Plain http only to this computer: the token never travels unencrypted.
    far = app_code(standin).replace(standin.url, "http://crm.example.com")
    with pytest.raises(BladeRunError, match="address is https://"):
        run_code(far, "conn", {"client secret": made_up.SECRET}, "Sales CRM")
    monkeypatch.delenv("IDENTITY_ENDPOINT")  # outside Azure: no managed identity to ask
    code = dataverse.MANAGED.replace("https://your-org.crm.dynamics.com", standin.url)
    monkeypatch.setattr("urllib.request.OpenerDirector.open", _unreachable)
    with pytest.raises(BladeRunError, match="signs in only inside Azure"):
        run_code(code, "conn", {}, "Sales CRM")


def _unreachable(*args: Any, **kwargs: Any) -> Any:
    import urllib.error

    raise urllib.error.URLError("timed out")


# ===== the catalog: the metadata =====


def test_the_metadata_becomes_one_schema_of_tables_and_typed_columns(standin: made_up.StandIn) -> None:
    rows = connect(standin).catalog()
    asked = standin.gets()[-1]
    assert asked["path"] == "/api/data/v9.2/EntityDefinitions"
    assert asked["query"]["$filter"] == "IsPrivate eq false"
    assert asked["query"]["$expand"].startswith("Attributes($select=LogicalName,AttributeType,")
    assert {r["table_schema"] for r in rows} == {"dbo"}
    assert sorted({r["table_name"] for r in rows}) == [
        "account",
        "contact",
        "opportunity",
    ]  # not the private one
    # Each table's display name: a row with no column. Each column: its type and display name.
    assert {r["table_name"]: r["description"] for r in rows if not r["column_name"]} == {
        "account": "Account", "contact": "Contact", "opportunity": "Opportunity",
    }  # fmt: skip
    account = {
        r["column_name"]: (r["data_type"], r["description"]) for r in rows if r["table_name"] == "account"
    }
    assert account["revenue"] == ("Money", "Annual Revenue")
    assert account["industrycode"] == ("Picklist", "Industry")
    assert account["primarycontactid"] == ("Lookup", "Primary Contact")
    assert account["primarycontactidname"] == ("String", "")  # a lookup's name, as the SQL endpoint has it
    # Never read: a choice's own name column, an image.
    assert "statecodename" not in account and "entityimage" not in account
    assert list(account)[1:4] == ["accountid", "accountnumber", "createdon"]  # by name (the table row first)


def test_the_catalog_loads_and_its_tables_carry_their_display_names(
    client: TestClient, standin: made_up.StandIn
) -> None:
    saved_connection(client, standin)
    refreshed = client.post("/blades/Sales%20CRM/refresh", json={}, headers=AUTH)
    assert refreshed.status_code == 200, refreshed.text
    assert (
        refreshed.json()["catalog"]["tables"] == 3 and refreshed.json()["catalog"]["dialect"] == "dataverse"
    )
    schemas = client.get("/catalogs/Sales%20CRM/schemas", headers=AGENT).json()["schemas"]
    assert [s["schema"] for s in schemas] == ["dbo"]
    tables = client.get("/catalogs/Sales%20CRM/tables?schema=dbo", headers=AGENT).json()["tables"]
    assert [(t["table"], t.get("title")) for t in tables] == [
        ("account", "Account"), ("contact", "Contact"), ("opportunity", "Opportunity"),
    ]  # fmt: skip
    columns = client.get("/catalogs/Sales%20CRM/columns?schema=dbo&table=account", headers=AGENT).json()
    assert columns["select"].startswith("SELECT TOP 100 [accountid], [accountnumber]")
    assert columns["select"].endswith("\nFROM [account]")  # its one schema is never named
    found = client.get("/catalogs/Sales%20CRM/search?q=revenue", headers=AGENT).json()
    assert [(c["table"], c["column"]) for c in found["columns"]] == [("account", "revenue")]


def test_the_sql_endpoints_dialect_is_t_sql_with_no_schema() -> None:
    assert (
        select_sql("dataverse", "", "dbo", "account", ["name"], 10) == "SELECT TOP 10 [name]\nFROM [account]"
    )
    assert select_sql("dataverse", "", "dbo", "account", [], None) == "SELECT *\nFROM [account]"


# ===== reading a table: OData, paging, labels =====


def test_a_read_is_odata_select_filter_order_and_top(standin: made_up.StandIn) -> None:
    namespace: dict[str, Any] = {"secret": str}
    exec(compile(dataverse.APP.split("\nconn = ")[0], "<dataverse>", "exec"), namespace)  # noqa: S102
    query_of = namespace["query_of"]
    assert query_of("accounts") == "accounts"
    assert (
        query_of(
            "accounts",
            ["name", "_primarycontactid_value"],
            "revenue gt 100000 and name eq 'A B'",
            "name desc",
            50,
            True,
        )
        == "accounts?$select=name,_primarycontactid_value"
        "&$filter=revenue%20gt%20100000%20and%20name%20eq%20'A%20B'&$orderby=name%20desc&$top=50&$count=true"
    )
    conn = connect(standin)
    rows, total = conn.rows("Account", columns=["name", "revenue"], filter="revenue gt 1000000", limit=3,
                            order_by="revenue desc")  # fmt: skip
    assert rows == [
        {"name": "Maple Row Grocers", "revenue": 1440000.5},
        {"name": "Lantern Consulting", "revenue": 1320000.5},
        {"name": "Juniper Accounting", "revenue": 1080000.5},
    ]
    assert total == 3  # the count the read asked for: every row the filter matches (one has no revenue)
    read = standin.gets()[-1]
    assert read["path"] == "/api/data/v9.2/accounts"
    assert read["query"] == {
        "$select": "name,revenue", "$filter": "revenue gt 1000000", "$orderby": "revenue desc",
        "$top": "3", "$count": "true",
    }  # fmt: skip
    assert 'odata.include-annotations="OData.Community.Display.V1.FormattedValue"' in read["prefer"]
    # By its logical name, its entity set or its display name; an unknown one says what there is.
    assert conn.table("opportunities")["table"] == conn.table("OPPORTUNITY")["table"] == "opportunity"
    with pytest.raises(RuntimeError, match=r"no table 'nope'.*It has: account, contact, opportunity"):
        conn.rows("nope")
    with pytest.raises(RuntimeError, match="account has no column 'nope'"):
        conn.rows("account", columns=["nope"])


def test_paging_follows_next_link_until_the_rows_asked_for(standin: made_up.StandIn) -> None:
    conn = connect(standin)
    standin.page_cap = 1000  # a page smaller than asked, as Dataverse may give
    rows, total = conn.rows("opportunity", limit=2500)
    reads = [r for r in standin.gets() if r["path"].endswith("/opportunities")]
    assert len(rows) == 2500 and len(reads) == 3  # 1,000 + 1,000 + 500 of the third page
    assert [r["query"].get("$skiptoken") for r in reads] == [None, "1000", "2000"]
    assert rows[0]["name"] == "Order 00001" and rows[-1]["name"] == "Order 02500"
    # More than 5,000: the count stops there, so Dataverse's own count says how many there are.
    assert total == made_up.OPPORTUNITIES
    standin.page_cap = 5000
    every, total = conn.rows("opportunity")
    assert len(every) == total == made_up.OPPORTUNITIES
    last = [r for r in standin.gets() if r["path"].endswith("/opportunities")][-1]
    assert "odata.maxpagesize=5000" in last["prefer"] and "$top" not in last["query"]
    # A filtered read of more than 5,000 has no count to give.
    _, total = conn.rows("opportunity", filter="closeprobability ge 0", limit=10)
    assert total is None


def test_a_next_link_outside_the_environment_is_never_followed(standin: made_up.StandIn) -> None:
    conn = connect(standin)
    with pytest.raises(RuntimeError, match="an address outside"):
        conn.get("https://elsewhere.example.com/api/data/v9.2/accounts", "Reading the table")


def test_choice_columns_read_as_their_labels_and_numbers_and_dates_as_themselves(
    standin: made_up.StandIn,
) -> None:
    conn = connect(standin)
    first = conn.rows("account", limit=1)[0][0]
    assert first["industrycode"] == "Consulting" and first["statecode"] == "Active"
    assert first["primarycontactid"] == "0000000c-0000-4000-8000-000000000002"  # a lookup: its id
    assert first["primarycontactidname"] == "Cleo Carver"  # and its name beside it
    assert first["revenue"] == 120000.5 and first["numberofemployees"] == 5  # never "$120,000.50"
    assert first["donotemail"] is False  # a Yes/No stays true or false
    assert first["createdon"] == datetime(2026, 1, 6, 9, 30, tzinfo=UTC)
    contacts = conn.read("contact", columns=["fullname", "gendercode", "birthdate", "parentcustomeridname"])
    assert isinstance(contacts, pd.DataFrame) and len(contacts) == 30
    assert contacts["gendercode"].tolist()[:3] == ["Female", "Male", "Female"]
    assert contacts["gendercode"].isna().sum() == 4  # no choice made: nothing, not a made-up label
    assert contacts["parentcustomeridname"].tolist()[0] == "Bluefin Outfitters"
    opportunities = conn.rows("opportunity", columns=["salesstage", "statecode"], limit=3)[0]
    assert opportunities == [
        {"salesstage": "Develop", "statecode": "Won"},
        {"salesstage": "Propose", "statecode": "Lost"},
        {"salesstage": "Close", "statecode": "Open"},
    ]


def test_a_fetchxml_query_reads_its_rows(standin: made_up.StandIn) -> None:
    conn = connect(standin)
    found = conn.fetch(
        '<fetch top="2"><entity name="opportunity"><attribute name="name"/><attribute name="statecode"/>'
        '<attribute name="parentaccountid"/>'
        '<filter><condition attribute="statecode" operator="eq" value="1"/>'
        '</filter><order attribute="estimatedvalue" descending="true"/></entity></fetch>'
    )
    assert list(found.columns) == ["name", "parentaccountid", "parentaccountidname", "statecode"]
    assert found["statecode"].tolist() == ["Won", "Won"] and len(found) == 2
    assert "fetchXml" in standin.gets()[-1]["query"]
    with pytest.raises(RuntimeError, match="names its table"):
        conn.fetch("<fetch><entity/></fetch>")


def test_test_signs_in_counts_the_tables_and_shows_first_rows(
    client: TestClient, standin: made_up.StandIn
) -> None:
    saved_connection(client, standin)
    tested = client.post("/blades/Sales%20CRM/test", json={}, headers=AGENT)
    assert tested.status_code == 200, tested.text
    said = tested.json()
    assert said["found"] == "signed in and found 3 tables" and said["type"] == "Dataverse"
    assert said["preview"]["table"] == "account" and said["preview"]["total"] == 12
    assert said["preview"]["columns"][:2] == ["accountid", "accountnumber"]
    assert len(said["preview"]["rows"]) == 12


# ===== Open as grid, the preview, and the agent's own reads =====


def test_a_table_opens_as_a_grid_through_the_web_api(client: TestClient, standin: made_up.StandIn) -> None:
    saved_connection(client, standin, row_limit=1000)
    opened = client.post(
        "/connections/Sales%20CRM/open", json={"schema": "dbo", "table": "opportunity"}, headers=AGENT
    )
    assert opened.status_code == 200, opened.text
    assert (opened.json()["dataset"], opened.json()["shown"], opened.json()["total"]) == (
        "opportunity", 1000, made_up.OPPORTUNITIES,
    )  # fmt: skip
    grid = client.get(f"/grids/{opened.json()['grid']}", headers=AUTH).json()
    assert grid["row_count"] == 1000 and grid["opened"]["total"] == made_up.OPPORTUNITIES
    columns = {c["name"]: c["type"] for c in grid["columns"]}
    assert columns["estimatedvalue"] == "DOUBLE" and columns["estimatedclosedate"].startswith("TIMESTAMP")
    assert columns["salesstage"] == "VARCHAR"  # a choice: its labels
    # Through the Web API: no SQL was sent, and the read asked Dataverse for the first 1,000 only.
    read = next(r for r in standin.gets() if r["path"].endswith("/opportunities"))
    assert read["query"]["$top"] == "1000"
    # A notebook reads it again with sab.read: the table's cell says so.
    cells = {t["name"]: t for t in client.get("/workbench/tables", headers=AUTH).json()["tables"]}
    assert "opportunity = sab.read('Sales CRM', 'opportunity')" in cells["opportunity"]["loaded"]
    whole = client.post("/connections/Sales%20CRM/open", json={"table": "account"}, headers=AUTH).json()
    assert (whole["shown"], whole["total"]) == (12, 12)
    preview = client.post("/connections/Sales%20CRM/preview", json={"table": "contact"}, headers=AUTH).json()
    assert preview["columns"][:2] == ["birthdate", "contactid"] and len(preview["rows"]) == 30
    refused = client.post("/connections/Sales%20CRM/open", json={"table": "nope"}, headers=AUTH)
    assert refused.status_code == 422 and "has no table 'nope'" in refused.text


def test_no_secret_in_any_answer_log_or_file(
    client: TestClient, standin: made_up.StandIn, tmp_path: Path
) -> None:
    answers: list[str] = []

    def call(method: str, path: str, body: Any = None, headers: dict[str, str] = AUTH) -> Any:
        answer = client.request(method, path, json=body, headers=headers)
        assert answer.status_code == 200, (path, answer.text)
        answers.append(answer.text)
        return answer.json()

    code = saved_connection(client, standin)
    assert 'client_secret = secret("crm_client_secret")' in code  # the vault's entry, by name
    call("GET", "/connections", headers=AGENT)
    call("GET", "/connections/Sales%20CRM", headers=AGENT)
    call("GET", "/blades", headers=AGENT)
    call("POST", "/blades/Sales%20CRM/test", {}, AGENT)
    call("POST", "/blades/Sales%20CRM/refresh", {}, AGENT)
    call("POST", "/connections/Sales%20CRM/open", {"table": "account"}, AGENT)
    call("POST", "/connections/Sales%20CRM/preview", {"table": "contact"}, AGENT)
    template = BY_ID["dataverse"].to_json()
    draft = {
        "name": "Sales CRM",
        "kind": "sql",
        "template": "dataverse",
        "dialect": "dataverse",
        "code": code,
    }
    call("POST", "/connections/test", draft | {"variable": "conn", "catalog": template["catalog"]}, AGENT)
    refused = client.post("/connections/Sales%20CRM/open", json={"table": "nope"}, headers=AGENT)
    answers.append(refused.text)
    for text in answers:
        assert not any(value in text for value in NOT_TO_BE_SEEN), text[:300]
    for file in (tmp_path / "state").rglob("*"):
        if file.is_file() and not file.name.startswith("team_vault"):  # the made-up vault's own code
            text = file.read_text(encoding="utf-8", errors="replace")
            assert not any(value in text for value in NOT_TO_BE_SEEN), file


# ===== SQL: the read-only SQL endpoint (TDS), with a stand-in for pyodbc =====


class FakeCursor:
    def __init__(self, refusal: str | None) -> None:
        self.refusal, self.rowcount, self.sent = refusal, -1, ""
        self.description: list[tuple[Any, ...]] | None = None

    def execute(self, sql: str, *parameters: Any) -> None:
        if self.refusal:
            raise RuntimeError(self.refusal)
        self.sent = sql
        self.description = [("name", None, None, None, None, None, None)]

    def fetchall(self) -> list[tuple[Any, ...]]:
        return [("Bluefin Outfitters",)]

    def close(self) -> None:
        pass


@pytest.fixture
def pyodbc(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """pyodbc, stood in for: what connect() was given, and the refusal its queries meet (if any)."""
    seen = types.SimpleNamespace(calls=[], refusal=None, connect_refusal=None)

    def connect(text: str, attrs_before: dict[int, bytes] | None = None) -> Any:
        seen.calls.append((text, attrs_before))
        if seen.connect_refusal:
            raise RuntimeError(seen.connect_refusal)
        made = types.SimpleNamespace(cursor=lambda: FakeCursor(seen.refusal), close=lambda: None)
        return made

    monkeypatch.setitem(sys.modules, "pyodbc", types.SimpleNamespace(connect=connect))
    return seen


TDS_DISABLED = (
    "('42000', '[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]TDS protocol endpoint is "
    "disabled for this organization. (40000) (SQLExecDirectW)')"
)


def test_sql_goes_to_port_5558_with_the_token_beside_the_connection_string(
    standin: made_up.StandIn, pyodbc: types.SimpleNamespace
) -> None:
    conn = connect(standin)
    cursor = conn.cursor()
    cursor.execute("SELECT TOP 1 name FROM account")
    assert cursor.fetchall() == [("Bluefin Outfitters",)] and cursor.description[0][0] == "name"
    text, attrs = pyodbc.calls[0]
    assert (
        text == "Driver={ODBC Driver 18 for SQL Server};Server=127.0.0.1,5558;"
        "Encrypt=yes;TrustServerCertificate=no;"
    )
    assert "UID=" not in text and "PWD=" not in text and "Authentication=" not in text
    sent = made_up.TOKEN.encode("utf-16-le")
    assert attrs == {1256: len(sent).to_bytes(4, "little") + sent}  # SQL_COPT_SS_ACCESS_TOKEN
    conn.cursor()
    assert len(pyodbc.calls) == 1  # connected once
    conn.close()


def test_the_sql_endpoint_being_off_is_said_plainly_with_the_read_instead(
    standin: made_up.StandIn, pyodbc: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = connect(standin)
    pyodbc.refusal = TDS_DISABLED
    with pytest.raises(RuntimeError) as off:
        conn.cursor().execute("SELECT name FROM account")
    assert "SQL endpoint (TDS) is off in this environment" in str(off.value)
    assert '"Enable TDS endpoint" in the Power Platform admin center' in str(off.value)
    # In a SQL cell: the line that reads the table through the Web API instead.
    found = sql_cell.Connection(
        "Sales CRM", "database", conn, "a Dataverse environment", language="dataverse"
    )
    with pytest.raises(sql_cell.SqlCellError) as cell:
        sql_cell.run(found, "SELECT name, revenue\nFROM [dbo].[account] WHERE revenue > 10")
    said = str(cell.value)
    assert said.endswith('Read it instead: account = sab.read("Sales CRM", "account")')
    # The error panel: what it means, and a cell that reads it instead.
    explained = errors.explain({"type": "UsageError", "message": f"SQL cell: {said}"})
    assert "SQL endpoint is off" in explained["explanation"]
    assert explained["fixes"] == [
        {
            "kind": "cell",
            "title": "Read the table instead",
            "text": 'account = sab.read("Sales CRM", "account")',
        }
    ]
    # Other refusals: in plain words too.
    pyodbc.connect_refusal = (
        "('01000', \"[01000] [unixODBC][Driver Manager]Can't open lib 'ODBC Driver 18'\")"
    )
    conn.sql = None
    with pytest.raises(RuntimeError, match="needs Microsoft's ODBC Driver 18"):
        conn.cursor()


def test_the_line_that_reads_instead_names_the_first_table() -> None:
    assert dataverse.read_instead("Sales CRM", "select * from contact c join account a on 1=1") == (
        'contact = sab.read("Sales CRM", "contact")'
    )
    assert dataverse.read_instead('My "CRM"', "SELECT 1") == 'account = sab.read("My \\"CRM\\"", "account")'


# ===== the starter pack =====


def starter(file: str, conn: Any) -> Any:
    blade = read_blade((STARTERS / f"{file}.blade.py").read_text(encoding="utf-8"))
    made, names = run_code(blade["code"], blade["variable"], {}, blade["name"])
    names["sab"] = type("sab", (), {"connection": staticmethod(lambda name: conn)})
    return made


def test_the_fetchxml_starter_reads_through_the_connection(standin: made_up.StandIn) -> None:
    fetch_xml = starter("dataverse_fetchxml_query", connect(standin))
    found = fetch_xml(
        '<fetch top="3"><entity name="account"><attribute name="name"/><attribute name="industrycode"/>'
        "</entity></fetch>"
    )
    assert found.to_dict("records") == [
        {"industrycode": "Consulting", "name": "Bluefin Outfitters"},
        {"industrycode": "Retail", "name": "Copper Kettle Foods"},
        {"industrycode": "Transport", "name": "Driftwood Freight"},
    ]
    with pytest.raises(RuntimeError, match="names its table"):
        fetch_xml("<fetch/>")
    with pytest.raises(RuntimeError, match="is not a Dataverse connection"):
        starter("dataverse_fetchxml_query", object())("<fetch/>")


def test_the_choice_options_starter_gives_each_number_and_label(standin: made_up.StandIn) -> None:
    choice_options = starter("dataverse_choice_options", connect(standin))
    found = choice_options("opportunity", "salesstage")
    assert found.to_dict("records") == [
        {"value": 0, "label": "Qualify"}, {"value": 1, "label": "Develop"},
        {"value": 2, "label": "Propose"}, {"value": 3, "label": "Close"},
    ]  # fmt: skip
    assert choice_options("Account", "statecode")["label"].tolist() == ["Active", "Inactive"]
    with pytest.raises(RuntimeError, match="is a Money column, not a choice"):
        choice_options("opportunity", "estimatedvalue")
    with pytest.raises(RuntimeError, match="has no column 'nope'"):
        choice_options("opportunity", "nope")


def test_the_starter_and_its_catalog_are_json_safe() -> None:
    assert json.loads(json.dumps(BY_ID["dataverse"].to_json()))["id"] == "dataverse"
