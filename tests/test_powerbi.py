"""The Power BI dataset connection, against a stand-in on this computer (tests/powerbi_standin.py): no
real tenant is reached, and every value is made up. The app registration's three values come from a
made-up key vault written in plain Python, as the owner's connection is made from their vault."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from starlette.testclient import TestClient

from swissarmygrid.adapters.blade_run import BladeRunError, run_catalog, run_code
from swissarmygrid.client import blades_client, sql_cell
from swissarmygrid.domain import powerbi
from swissarmygrid.domain.blades import detect_settings, read_code
from swissarmygrid.domain.catalogs import count_sql, dax_column, dax_table, normalize_dialect, select_sql
from swissarmygrid.domain.connections import signs_in_interactively
from swissarmygrid.domain.relationships import Model, Relationship, conflicts, merge
from swissarmygrid.server.blade_templates import (
    BY_ID,
    POWERBI_BROWSER,
    POWERBI_CATALOG,
    POWERBI_TYPED,
    POWERBI_VAULT,
)
from tests import powerbi_standin as made_up
from tests.conftest import AGENT, AUTH
from tests.fake_keyring import memory_keyring

SECRETS = {"tenant id": made_up.TENANT, "client id": made_up.CLIENT, "client secret": made_up.SECRET}
NOT_TO_BE_SEEN = (made_up.SECRET, made_up.TENANT, made_up.CLIENT, made_up.TOKEN)

# The owner's vault, stood in for by plain Python: an app registration's three values, by name.
VAULT_CODE = f"""values = {{
    "powerbi-tenant-id": "{made_up.TENANT}",
    "powerbi-client-id": "{made_up.CLIENT}",
    "powerbi-client-secret": "{made_up.SECRET}",
    "warehouse-password": "made-up-not-used",
}}


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
    """Power BI and Microsoft's sign-in, stood in for on this computer; the connection's code is pointed
    at it by the two environment variables it reads (a child process gets them too)."""
    running = made_up.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    yield running
    running.stop()


def filled(code: str) -> str:
    """The starter's code with the made-up dataset's two ids in it."""
    return code.replace("my-workspace-id", made_up.WORKSPACE).replace("my-dataset-id", made_up.DATASET)


def connect(code: str = POWERBI_VAULT, secrets: dict[str, str] | None = None) -> tuple[Any, dict[str, Any]]:
    return run_code(filled(code), "conn", SECRETS if secrets is None else secrets, "Sales model")


def query(conn: Any, dax: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    conn.execute(dax)
    return [d[0] for d in conn.description], conn.fetchall()


def saved_connection(client: TestClient, name: str = "Sales model", **more: Any) -> None:
    """The vault, then a Power BI dataset whose three values are that vault's entries."""
    vault: dict[str, Any] = {"name": "Team vault", "kind": "vault", "template": "azure_key_vault"}
    vault |= {"variable": "get", "code": VAULT_CODE, "vault_all": True, "vault_mapping": []}
    assert client.post("/connections", json=vault, headers=AUTH).status_code == 200
    code = filled(POWERBI_VAULT)
    for secret, in_vault in (
        ("tenant id", "powerbi-tenant-id"),
        ("client id", "powerbi-client-id"),
        ("client secret", "powerbi-client-secret"),
    ):
        body = {
            "code": code,
            "secret": secret,
            "from": "vault",
            "vault": "Team vault",
            "vault_secret": in_vault,
        }
        code = client.post("/connections/source", json=body, headers=AUTH).json()["code"]
    template = BY_ID["powerbi"].to_json()
    body = {"name": name, "kind": "sql", "template": "powerbi", "dialect": "dax", "code": code}
    body |= {"variable": "conn", "catalog": template["catalog"]} | more
    saved = client.post("/connections", json=body, headers=AUTH)
    assert saved.status_code == 200, saved.text


# ===== the dialect =====


def test_dax_names_are_quoted_dax_style() -> None:
    assert dax_table("Sales") == "'Sales'" and dax_table("Bob's Orders") == "'Bob''s Orders'"
    assert dax_column("Unit Price", "Order Lines") == "'Order Lines'[Unit Price]"
    assert dax_column("Total Sales") == "[Total Sales]"  # a measure has no table in front
    assert dax_column("Net [USD]", "Sales") == "'Sales'[Net [USD]]]"  # a closing bracket doubled
    assert normalize_dialect("Power BI") == "dax" and normalize_dialect("DAX") == "dax"


def test_open_as_grid_and_the_count_are_dax() -> None:
    assert select_sql("dax", "", "", "Order Lines", [], 10_000) == "EVALUATE TOPN(10000, 'Order Lines')"
    # A catalog lists a table's measures beside its columns: none is picked, the table comes whole.
    assert select_sql("dax", "", "", "Sales", ["Amount", "Total Sales"]) == "EVALUATE TOPN(100, 'Sales')"
    assert select_sql("dax", "", "", "Sales", [], None) == "EVALUATE 'Sales'"  # every row
    assert count_sql("dax", "", "", "Sales") == """EVALUATE ROW("n", COUNTROWS('Sales'))"""
    assert count_sql("sqlite", "", "", "orders") == 'SELECT COUNT(*) FROM "orders"'  # the others: as before


# ===== the starter =====


def test_the_starter_signs_in_three_ways_the_vault_first(client: TestClient) -> None:
    types = {t["id"]: t for t in client.get("/connections/types", headers=AUTH).json()["types"]}
    form = types["powerbi"]
    assert (
        form["label"] == "Power BI dataset" and form["connection"] == "database" and form["dialect"] == "dax"
    )
    assert [f["name"] for f in form["fields"]] == ["workspace_id", "dataset_id"]
    assert all(f["placeholder"] for f in form["fields"])
    # The default: an app registration whose three values are each read by name (a vault's entries).
    assert form["secrets"] == ["tenant id", "client id", "client secret"]
    assert form["secrets_from"] == "vault" and types["postgres"]["secrets_from"] == ""
    assert [w["label"] for w in form["sign_ins"]] == [
        "App registration, from a key vault",
        "App registration, ids typed here",
        "Browser sign-in, as yourself",
    ]
    assert form["sign_ins"][0]["code"] == form["code"] == POWERBI_VAULT
    # Each way's mark is found only in its own code (the form shows the way a saved one uses).
    codes = [w["code"] for w in form["sign_ins"]]
    for at, way in enumerate(form["sign_ins"]):
        assert [way["mark"].lower() in c.lower() for c in codes].index(True) == at
    # No package to install: its web requests are the standard library's.
    assert form["install_here"] is None and form["packages"] == []
    assert form["catalog"] == {"language": "python", "command": POWERBI_CATALOG}


def test_the_ids_may_be_typed_and_the_secret_is_never_a_setting() -> None:
    typed = read_code(POWERBI_TYPED)
    assert typed.secrets == ["client secret"] and typed.variable == "conn"
    assert [s.name for s in detect_settings(POWERBI_TYPED)] == [
        "workspace_id", "dataset_id", "tenant_id", "client_id",
    ]  # fmt: skip
    assert "client_secret" not in {s.key for s in detect_settings(POWERBI_VAULT)}
    browser = read_code(POWERBI_BROWSER)
    assert browser.secrets == [] and "azure.identity" in browser.imports
    assert [(s.name, s.value) for s in detect_settings(POWERBI_BROWSER)][-1] == ("tenant_id", "organizations")


def test_a_browser_sign_in_waits_for_first_use() -> None:
    assert signs_in_interactively(POWERBI_BROWSER)
    assert not signs_in_interactively(POWERBI_VAULT) and not signs_in_interactively(POWERBI_TYPED)


# ===== answers as tables =====


def test_the_sign_in_carries_the_app_registration_and_the_query_carries_its_token(
    standin: made_up.StandIn,
) -> None:
    conn, _ = connect()
    token = next(r for r in standin.requests if r["what"] == "token")
    assert token["tenant"] == made_up.TENANT
    assert token["form"] == {
        "grant_type": "client_credentials",
        "client_id": made_up.CLIENT,
        "client_secret": made_up.SECRET,
        "scope": "https://analysis.windows.net/powerbi/api/.default",
    }
    asked = next(r for r in standin.requests if r["what"] == "query")
    assert asked["authorization"] == f"Bearer {made_up.TOKEN}"
    assert asked["body"] == {
        "queries": [{"query": 'EVALUATE ROW("ok", 1)'}],  # making the connection reaches the dataset
        "serializerSettings": {"includeNulls": True},
    }
    query(conn, "EVALUATE TOPN(3, 'Sales')")
    assert (
        len([r for r in standin.requests if r["what"] == "token"]) == 1
    )  # the token is kept, not asked again


def test_an_answer_becomes_a_table_clean_names_types_and_nulls(standin: made_up.StandIn) -> None:
    conn, _ = connect()
    columns, rows = query(conn, "EVALUATE 'Sales'")
    assert columns == [
        "SalesKey",
        "CustomerKey",
        "ProductKey",
        "Order Date",
        "Ship Date",
        "Quantity",
        "Amount",
    ]
    assert len(rows) == 40
    first = dict(zip(columns, rows[0], strict=True))
    assert first["SalesKey"] == 1 and isinstance(first["SalesKey"], int)
    assert first["Amount"] == 24.5 and isinstance(first["Amount"], float)
    assert first["Order Date"] == datetime(2026, 1, 2)  # Power BI's text date, as a date
    tenth = dict(zip(columns, rows[9], strict=True))
    assert tenth["Ship Date"] is None and isinstance(rows[10][4], datetime)  # a null stays a null
    assert dict(zip(columns, rows[12], strict=True))["Amount"] is None
    # A measure's column ([Total Sales]) and a table's (Customer[Region]) both lose their brackets.
    columns, rows = query(
        conn, """EVALUATE SUMMARIZECOLUMNS('Customer'[Region], "Total Sales", [Total Sales])"""
    )
    assert columns == ["Region", "Total Sales"] and {r[0] for r in rows} == {"North", "South", "East", None}
    # As a frame (what a cell gives): dates are dates, a column with a gap is still numbers.
    frame = pd.DataFrame.from_records(
        query(conn, "EVALUATE 'Sales'")[1], columns=query(conn, "EVALUATE 'Sales'")[0]
    )
    assert str(frame["Order Date"].dtype).startswith("datetime64") and frame["Amount"].isna().sum() == 3
    assert str(frame["Ship Date"].dtype).startswith("datetime64") and frame["Quantity"].dtype == "int64"


def test_a_name_two_tables_share_keeps_its_table(standin: made_up.StandIn) -> None:
    _, names = connect()
    assert names["clean_names"](["Sales[CustomerKey]", "Customer[CustomerKey]", "[Total]"]) == [
        "Sales[CustomerKey]", "Customer[CustomerKey]", "Total",
    ]  # fmt: skip
    assert names["dates"](["2026-01-31T00:00:00", "not a date"]) == ["2026-01-31T00:00:00", "not a date"]
    assert names["dates"](["2026-01-31T08:30:00.5Z", None]) == [datetime(2026, 1, 31, 8, 30, 0, 500000), None]


def test_a_refused_query_says_what_power_bi_said(
    standin: made_up.StandIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn, _ = connect()
    with pytest.raises(Exception, match=r"The query was refused \(400\): Cannot find table 'Nope'\."):
        query(conn, "EVALUATE 'Nope'")
    # A wrong client secret: Microsoft's own words, its first line, and never the secret itself.
    wrong = SECRETS | {"client secret": "made-up-wrong-secret"}
    with pytest.raises(BladeRunError) as refused:
        connect(secrets=wrong)
    message = str(refused.value)
    assert "The sign-in was refused (401): AADSTS7000215: Invalid client secret provided." in message
    assert "Check the tenant id, the client id and the client secret." in message
    assert "made-up-wrong-secret" not in message and "Trace ID" not in message
    # A dataset this sign-in cannot find: what to check.
    with pytest.raises(
        BladeRunError, match=r"\(404\): PowerBIEntityNotFound Check the workspace id and the dataset"
    ):
        run_code(filled(POWERBI_VAULT).replace(made_up.DATASET, "no-such-dataset"), "conn", SECRETS)
    # Nothing listening at all (the wrong address): said plainly.
    monkeypatch.setenv("POWERBI_LOGIN_URL", "http://127.0.0.1:9")
    with pytest.raises(BladeRunError, match=r"The sign-in could not reach 127\.0\.0\.1:9"):
        connect()


def test_an_answer_at_power_bis_limit_is_refused_not_passed_off_as_whole(standin: made_up.StandIn) -> None:
    code = filled(POWERBI_VAULT)
    assert "MAX_ROWS = 100_000" in code and "MAX_VALUES = 1_000_000" in code  # the documented limits
    conn, _ = run_code(code.replace("MAX_ROWS = 100_000", "MAX_ROWS = 40"), "conn", SECRETS)
    with pytest.raises(Exception, match=r"at most 40 rows or 1,000,000 values .* \(40 rows of 7 columns\)"):
        query(conn, "EVALUATE 'Sales'")
    assert len(query(conn, "EVALUATE TOPN(39, 'Sales')")[1]) == 39  # under it: whole
    conn, _ = run_code(code.replace("MAX_VALUES = 1_000_000", "MAX_VALUES = 70"), "conn", SECRETS)
    with pytest.raises(Exception, match="so it is not whole: ask for fewer rows or columns"):
        query(conn, "EVALUATE TOPN(10, 'Sales')")  # 10 rows of 7 columns: 70 values


# ===== the catalog =====

TABLES = ["Customer", "Date", "Product", "Sales"]


def catalog_rows(standin: made_up.StandIn) -> list[dict[str, Any]]:
    conn, names = connect()
    columns, rows = run_catalog(conn, names, "python", POWERBI_CATALOG, {}, "Sales model")
    return [dict(zip(columns, row, strict=True)) for row in rows]


def test_the_catalog_lists_tables_columns_with_types_and_measures(standin: made_up.StandIn) -> None:
    rows = catalog_rows(standin)
    assert sorted({r["table_name"] for r in rows}) == TABLES  # not the date table Power BI made itself
    sales = [(r["column_name"], r["data_type"]) for r in rows if r["table_name"] == "Sales"]
    assert sales == [
        ("SalesKey", "Integer"),
        ("CustomerKey", "Integer"),
        ("ProductKey", "Integer"),
        ("Order Date", "DateTime"),
        ("Ship Date", "DateTime"),
        ("Quantity", "Integer"),
        ("Amount", "Decimal"),
        ("Total Sales", "measure, Decimal"),  # a measure: on its own table, marked
        ("Order Count", "measure, Integer"),
    ]
    assert standin.queries()[1:] == ["EVALUATE INFO.VIEW.COLUMNS()", "EVALUATE INFO.VIEW.MEASURES()"]


def test_an_older_model_is_read_by_ids_and_one_that_hides_its_description_by_statistics(
    standin: made_up.StandIn,
) -> None:
    named = catalog_rows(standin)
    standin.view_forms = False  # INFO.VIEW is not known: the numbered form, ids resolved, types named
    assert catalog_rows(standin) == named
    standin.info_forms = False  # no leave to read the model: its columns' statistics, no types, no measures
    plain = catalog_rows(standin)
    assert sorted({r["table_name"] for r in plain}) == TABLES
    assert [r["column_name"] for r in plain] == [
        r["column_name"] for r in named if "measure" not in r["data_type"]
    ]
    assert {r["data_type"] for r in plain} == {""}


def test_the_catalog_loads_and_reads_like_a_databases(client: TestClient, standin: made_up.StandIn) -> None:
    saved_connection(client)
    refreshed = client.post("/blades/Sales%20model/refresh", json={}, headers=AUTH)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["catalog"]["tables"] == 4 and refreshed.json()["catalog"]["dialect"] == "dax"
    tables = client.get("/catalogs/Sales%20model/tables?schema=", headers=AGENT).json()["tables"]
    assert [t["table"] for t in tables] == TABLES and tables[3]["columns"] == 9
    sales = client.get("/catalogs/Sales%20model/columns?schema=&table=Sales", headers=AGENT).json()
    assert sales["dialect"] == "dax" and sales["select"] == "EVALUATE TOPN(100, 'Sales')"
    assert {"column": "Total Sales", "type": "measure, Decimal"}.items() <= sales["columns"][7].items()
    found = client.get("/catalogs/Sales%20model/search?q=total", headers=AGENT).json()
    assert [c["column"] for c in found["columns"]] == ["Total Sales"]  # a measure is found by name


# ===== made from the vault =====


def test_the_connection_is_made_from_the_vault_and_no_secret_is_ever_answered(
    client: TestClient, standin: made_up.StandIn, tmp_path: Path
) -> None:
    answers: list[str] = []

    def call(method: str, path: str, body: Any = None, headers: dict[str, str] = AUTH) -> Any:
        answer = client.request(method, path, json=body, headers=headers)
        answers.append(answer.text)
        assert answer.status_code == 200, answer.text
        return answer.json()

    vault: dict[str, Any] = {"name": "Team vault", "kind": "vault", "template": "azure_key_vault"}
    vault |= {"variable": "get", "code": "", "vault_all": True, "vault_mapping": []}
    # The vault's code is the owner's own and holds the made-up values: it is saved, not answered below.
    assert client.post("/connections", json=vault | {"code": VAULT_CODE}, headers=AUTH).status_code == 200
    # The form's "Entry in the vault" picker: the vault's secrets, by name only.
    listed = call("POST", "/connections/vaults/secrets", {"name": "Team vault"})
    assert [n["secret"] for n in listed["names"]] == [
        "powerbi-client-id", "powerbi-client-secret", "powerbi-tenant-id", "warehouse-password",
    ]  # fmt: skip
    # Picking an entry for each of the three writes its name into the code, never its value.
    code = filled(POWERBI_VAULT)
    for secret, picked in (
        ("tenant id", "powerbi-tenant-id"),
        ("client id", "powerbi-client-id"),
        ("client secret", "powerbi-client-secret"),
    ):
        body = {
            "code": code,
            "secret": secret,
            "from": "vault",
            "vault": "Team vault",
            "vault_secret": picked,
        }
        pointed = call("POST", "/connections/source", body | {"connection": "Sales model"})
        code = pointed["code"]
    assert 'tenant_id = secret("powerbi_tenant_id")' in code
    assert 'client_id = secret("powerbi_client_id")' in code
    assert 'client_secret = secret("powerbi_client_secret")' in code  # the name an Azure Function reads too
    draft = {"name": "Sales model", "kind": "sql", "template": "powerbi", "dialect": "dax", "code": code}
    draft |= {"variable": "conn", "catalog": BY_ID["powerbi"].to_json()["catalog"]}
    # Test connection (nothing saved): the vault runs first, the sign-in carries its three values.
    tested = call("POST", "/connections/test", draft)
    assert tested["ok"] is True and tested["type"].endswith("PowerBI")
    token = next(r for r in standin.requests if r["what"] == "token")
    assert (token["tenant"], token["form"]["client_id"], token["form"]["client_secret"]) == (
        made_up.TENANT, made_up.CLIENT, made_up.SECRET,
    )  # fmt: skip
    call("POST", "/connections", draft)
    # Everything the page and the agent can then ask about it.
    shown = call("GET", "/connections/Sales%20model", headers=AGENT)
    assert shown["secrets"] == ["powerbi_tenant_id", "powerbi_client_id", "powerbi_client_secret"]
    assert shown["summary"]["vaults"] == ["Team vault"]
    call("GET", "/connections", headers=AGENT)
    call("GET", "/blades", headers=AGENT)
    call("GET", "/connections/vaults", headers=AGENT)
    call("POST", "/blades/Sales%20model/test", {}, AGENT)
    call("POST", "/blades/Sales%20model/refresh", {}, AGENT)
    call("POST", "/connections/Sales%20model/open", {"table": "Customer"}, AGENT)
    call("POST", "/connections/Sales%20model/preview", {"table": "Sales"}, AGENT)
    call("POST", "/connections/Sales%20model/relationships", {}, AGENT)
    # A refusal, too: a query Power BI turns down, and a sign-in Microsoft turns down.
    refused = client.post("/connections/Sales%20model/open", json={"table": "Nope"}, headers=AGENT)
    assert refused.status_code == 422 and "Cannot find table 'Nope'" in refused.text
    answers.append(refused.text)
    wrong = draft | {"code": code.replace(made_up.WORKSPACE, "another-workspace")}
    refused = client.post("/connections/test", json=wrong, headers=AGENT)
    assert refused.status_code == 422 and "PowerBIEntityNotFound" in refused.text
    answers.append(refused.text)
    for text in answers:
        for value in NOT_TO_BE_SEEN:
            assert value not in text
    # Nor in the audit log, nor in the saved connection's own file.
    for file in (tmp_path / "state").rglob("*"):
        if file.is_file() and not file.name.startswith("team_vault"):  # the made-up vault's own code
            text = file.read_text(encoding="utf-8", errors="replace")
            assert not any(value in text for value in NOT_TO_BE_SEEN), file


def test_a_wrong_secret_in_the_vault_is_refused_without_showing_it(
    client: TestClient, standin: made_up.StandIn
) -> None:
    saved_connection(client)
    wrong = VAULT_CODE.replace(made_up.SECRET, "made-up-stale-secret-0009")
    vault: dict[str, Any] = {"name": "Team vault", "kind": "vault", "template": "azure_key_vault"}
    vault |= {"variable": "get", "code": wrong, "vault_all": True, "vault_mapping": []}
    assert client.put("/connections/Team%20vault", json=vault, headers=AUTH).status_code == 200
    tested = client.post("/blades/Sales%20model/test", json={}, headers=AUTH)
    assert tested.status_code == 422
    assert "The sign-in was refused (401): AADSTS7000215" in tested.text
    assert "made-up-stale-secret-0009" not in tested.text


# ===== open as grid =====


def test_a_table_opens_as_a_grid_its_first_rows_counted_then_all(
    client: TestClient, standin: made_up.StandIn
) -> None:
    saved_connection(client, row_limit=10)
    opened = client.post("/connections/Sales%20model/open", json={"table": "Sales"}, headers=AGENT)
    assert opened.status_code == 200, opened.text
    assert (
        opened.json()["shown"] == 10 and opened.json()["total"] == 40 and opened.json()["dataset"] == "Sales"
    )
    assert standin.queries()[-2:] == [
        "EVALUATE TOPN(10, 'Sales')",
        """EVALUATE ROW("n", COUNTROWS('Sales'))""",
    ]
    grid = client.get(f"/grids/{opened.json()['grid']}", headers=AUTH).json()
    assert grid["row_count"] == 10
    assert grid["opened"] == {
        "connection": "Sales model", "database": "", "schema": "", "table": "Sales", "shown": 10, "total": 40,
    }  # fmt: skip
    columns = {c["name"]: c["type"] for c in grid["columns"]}
    assert list(columns) == [
        "SalesKey",
        "CustomerKey",
        "ProductKey",
        "Order Date",
        "Ship Date",
        "Quantity",
        "Amount",
    ]
    assert columns["SalesKey"] == "BIGINT" and columns["Amount"] == "DOUBLE"
    assert columns["Order Date"].startswith("TIMESTAMP")
    every = client.post("/connections/Sales%20model/open", json={"table": "Sales", "all": True}, headers=AUTH)
    grid = client.get(f"/grids/{every.json()['grid']}", headers=AUTH).json()
    assert grid["row_count"] == 40 and grid["opened"] is None
    assert standin.queries()[-1] == "EVALUATE 'Sales'"
    preview = client.post(
        "/connections/Sales%20model/preview", json={"table": "Customer"}, headers=AUTH
    ).json()
    assert preview["columns"] == ["CustomerKey", "Customer Name", "Region"] and len(preview["rows"]) == 8
    assert preview["rows"][2][2] is None  # a customer with no region
    # The table's cell in a notebook loads it with the DAX it was opened with.
    origin = client.get(f"/grids/{opened.json()['grid']}", headers=AUTH).json()
    assert origin["dataset"] == "Sales"


# ===== a DAX cell =====


@pytest.fixture
def cell(standin: made_up.StandIn, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A notebook's Python, with the server stood in for as tests/test_sql_cell.py does."""
    listed = [{"name": "Sales model", "kind": "sql", "connection": "database", "dialect": "dax"}]
    listed[0] |= {"template": "powerbi"}
    monkeypatch.setattr(
        blades_client, "_call", lambda method, path, *_: {"connections": listed, "blades": listed}
    )
    monkeypatch.setattr(blades_client, "blade", lambda name: connect()[0])
    monkeypatch.setattr(sql_cell, "_connections", {})
    monkeypatch.setattr(sql_cell, "_default", [])
    yield


def test_a_sql_cell_on_the_dataset_holds_dax_and_gives_a_frame(cell: None) -> None:
    frame = sql_cell.sql("Sales model", "EVALUATE TOPN(5, 'Customer')")
    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == ["CustomerKey", "Customer Name", "Region"] and len(frame) == 5
    # With the uses line a cell keeps (a DAX comment too) and a closing semicolon.
    text = "-- uses Customer @cell3\n"
    text += """EVALUATE SUMMARIZECOLUMNS('Customer'[Region], "Total Sales", [Total Sales]);"""
    totals = sql_cell.sql("Sales model", text)
    assert list(totals.columns) == ["Region", "Total Sales"] and len(totals) == 4
    assert sql_cell.connection("Sales model").describe == "a Power BI dataset (DAX)"
    assert sql_cell.listing() == [("Sales model", "a Power BI dataset (DAX)")]


def test_the_magic_keeps_the_result_and_says_power_bis_refusal_in_one_line(cell: None) -> None:
    class Shell:
        def __init__(self) -> None:
            self.user_ns: dict[str, Any] = {}

    shell = Shell()
    result = sql_cell._cell(shell, '"Sales model" -> customers', "EVALUATE 'Customer'")
    assert len(result) == 8 and shell.user_ns["customers"] is result
    with pytest.raises(
        Exception, match=r"Sales model: PowerBIError: The query was refused .* Cannot find table"
    ):
        sql_cell._cell(shell, '"Sales model"', "EVALUATE 'Nope'")


def test_the_uses_line_reads_dax_without_breaking() -> None:
    from swissarmygrid.domain.table_cells import names_used, uses_line, with_uses

    dax = (
        """EVALUATE\nSUMMARIZECOLUMNS('Customer'[Region], "Total Sales", [Total Sales])  -- Sales by region"""
    )
    # A measure's name in brackets is not the table Sales; 'Customer' is quoted, as SQL's text is.
    assert names_used(dax, sql=True) == ["EVALUATE", "SUMMARIZECOLUMNS", "Region"]
    assert with_uses(dax, {"Sales": 3, "Customer": 4}, sql=True) == dax  # no table named: nothing added
    bare = "EVALUATE TOPN(10, Sales)"  # DAX allows a one-word table without quotes
    assert uses_line(bare, {"Sales": 3}, sql=True) == "-- uses Sales @cell3"  # a comment in DAX too
    assert with_uses(bare, {"Sales": 3}, sql=True).splitlines() == ["-- uses Sales @cell3", bare]
    # SQL Server's one-word bracketed names are still names.
    assert "orders" in names_used("SELECT * FROM [orders] JOIN [Order Lines] ON 1 = 1", sql=True)
    assert "Lines" not in names_used("SELECT * FROM [Order Lines]", sql=True)


# ===== the dataset's relationships =====

VIEW_ROWS = [
    {"[FromTable]": ft, "[FromColumn]": fc, "[ToTable]": tt, "[ToColumn]": tc, "[IsActive]": active}
    | {"[FromCardinality]": "Many", "[ToCardinality]": "One"}
    | {"[CrossFilteringBehavior]": "BothDirections" if both else "OneDirection"}
    for ft, fc, tt, tc, active, both in made_up.RELATIONSHIPS
]


def as_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    columns = [key.strip("[]") for key in rows[0]]
    return {"columns": columns, "rows": [list(row.values()) for row in rows]}


def test_the_datasets_relationships_become_the_apps_model() -> None:
    model, skipped = powerbi.relationships_model("Sales model", 0, [as_table(VIEW_ROWS)])
    assert skipped == 1  # the one to the date table Power BI made by itself
    assert model.name == "Sales model"
    assert model.relationships == (
        Relationship("Sales", ("CustomerKey",), "Customer", ("CustomerKey",), "many-to-one"),
        Relationship(
            "Sales", ("ProductKey",), "Product", ("ProductKey",), "many-to-one", "filters both ways"
        ),
        Relationship("Sales", ("Order Date",), "Date", ("Date",), "many-to-one"),
        Relationship("Sales", ("Ship Date",), "Date", ("Date",), "many-to-one", active=False),
    )
    assert model.sources["Sales"] == "Sales model (Power BI)"
    # Tables are named as they open as grids; the other cardinalities map the same way.
    odd: list[dict[str, Any]] = [
        {"FromTable": "Order Lines", "FromColumn": "Order Id", "ToTable": "Orders (2026)", "ToColumn": "Id"}
        | {"FromCardinality": "One", "ToCardinality": "One", "IsActive": True},
        {"FromTable": "Tags", "FromColumn": "Tag", "ToTable": "Order Lines", "ToColumn": "Tag"}
        | {"FromCardinality": "Many", "ToCardinality": "Many", "IsActive": "true"},
        {"FromTable": "Regions", "FromColumn": "Id", "ToTable": "Stores", "ToColumn": "Region"}
        | {"FromCardinality": "One", "ToCardinality": "Many", "IsActive": 1},
    ]
    found, _ = powerbi.relationships_model("Shop", 0, [as_table(odd)])
    assert [(r.from_table, r.to_table, r.kind, r.active) for r in found.relationships] == [
        ("Order_Lines", "Orders_2026", "one-to-one", True),
        ("Tags", "Order_Lines", "many-to-many", True),
        ("Regions", "Stores", "one-to-many", True),
    ]
    with pytest.raises(powerbi.PowerBIError, match="came back without fromtable: it gave name"):
        powerbi.relationships_model("Shop", 0, [{"columns": ["Name"], "rows": [["x"]]}])


def test_the_numbered_form_gives_the_same_model() -> None:
    named, _ = powerbi.relationships_model("Sales model", 0, [as_table(VIEW_ROWS)])
    numbered = [
        as_table(made_up.evaluate(f"EVALUATE INFO.{f}()")) for f in ("RELATIONSHIPS", "TABLES", "COLUMNS")
    ]
    model, skipped = powerbi.relationships_model("Sales model", 1, numbered)
    assert model == named and skipped == 1
    with pytest.raises(powerbi.PowerBIError, match=r"a table or column .* it did not list"):
        powerbi.relationships_model(
            "Sales model", 1, [numbered[0], numbered[1], as_table([{"ID": 1, "Name": "x"}])]
        )


def test_import_its_relationships_merges_into_the_current_model(
    client: TestClient, standin: made_up.StandIn
) -> None:
    saved_connection(client)
    # What is already known: one of the same joins, held to be one-to-one, and a join of another table.
    known = {
        "name": "Mine",
        "relationships": [
            {
                "from": "Sales",
                "from_columns": ["CustomerKey"],
                "to": "Customer",
                "to_columns": ["CustomerKey"],
            }
            | {"kind": "one-to-one"},
            {"from": "Returns", "from_columns": ["SalesKey"], "to": "Sales", "to_columns": ["SalesKey"]},
        ],
    }
    assert client.post("/relationships", json={"model": known}, headers=AUTH).status_code == 200
    imported = client.post(
        "/connections/Sales%20model/relationships", json={}, headers=AGENT
    )  # the agent may
    assert imported.status_code == 200, imported.text
    answer = imported.json()
    assert answer["changed"] == ["Sales -> Customer: one-to-one becomes many-to-one"]  # the dataset's wins
    assert answer["tables"] == ["Customer", "Date", "Product", "Sales"] and answer["skipped"] == 1
    assert len(answer["imported"]) == 4
    assert standin.queries()[-1] == "EVALUATE INFO.VIEW.RELATIONSHIPS()"
    current = client.get("/relationships", headers=AUTH).json()
    assert current == answer["model"] and current["name"] == "Mine + Sales model"
    joins = {(r["from"], r["from_columns"][0], r["to"]): r for r in current["relationships"]}
    assert len(joins) == 5 and joins[("Returns", "SalesKey", "Sales")]["kind"] == "many-to-one"  # kept
    assert joins[("Sales", "CustomerKey", "Customer")]["kind"] == "many-to-one"
    assert joins[("Sales", "Ship Date", "Date")]["active"] is False  # inactive stays inactive
    assert "active" not in joins[("Sales", "Order Date", "Date")]
    assert joins[("Sales", "ProductKey", "Product")]["note"] == "filters both ways"
    assert current["tables"]["Sales"]["source"] == "Sales model (Power BI)"
    # A second import changes nothing; an older model answers through the numbered form, the same.
    standin.view_forms = False
    again = client.post("/connections/Sales%20model/relationships", json={}, headers=AUTH).json()
    assert again["changed"] == [] and again["imported"] == answer["imported"]
    assert standin.queries()[-3:] == [
        "EVALUATE INFO.RELATIONSHIPS()", "EVALUATE INFO.TABLES()", "EVALUATE INFO.COLUMNS()",
    ]  # fmt: skip
    assert len(client.get("/relationships", headers=AUTH).json()["relationships"]) == 5
    # The Diagram draws them once the tables are open.
    for table in TABLES:
        assert (
            client.post("/connections/Sales%20model/open", json={"table": table}, headers=AUTH).status_code
            == 200
        )
    erd = client.get("/relationships/erd", headers=AUTH).json()
    assert set(erd["tables"]) == set(TABLES) and "Sales" in erd["mermaid"]
    dashed = [line.strip() for line in erd["mermaid"].splitlines() if ".." in line]
    assert len(dashed) == 1 and dashed[0].endswith(': "inactive"')  # the Ship Date join: dashed, said so
    assert {dashed[0].split()[0], dashed[0].split()[2]} == {"Sales", "Date"}
    # Neither form answered: Power BI's own refusal, from the first one tried.
    standin.info_forms = False
    refused = client.post("/connections/Sales%20model/relationships", json={}, headers=AUTH)
    assert refused.status_code == 422 and "Failed to resolve name 'INFO.VIEW.RELATIONSHIPS'" in refused.text


def test_only_a_power_bi_dataset_has_relationships_to_import(client: TestClient, tmp_path: Path) -> None:
    file = tmp_path / "orders.csv"
    file.write_text("order_id\n1\n", encoding="utf-8")
    body = {"name": "Orders", "kind": "other", "template": "csv"}
    body |= {"code": f'from pathlib import Path\npath = Path(r"{file}")'}
    assert client.post("/connections", json=body, headers=AUTH).status_code == 200
    refused = client.post("/connections/Orders/relationships", json={}, headers=AUTH)
    assert refused.status_code == 400 and "is not a Power BI dataset" in refused.text


def test_merging_keeps_the_existing_rules() -> None:
    mine = Model("Mine", relationships=(Relationship("Sales", ("Ship Date",), "Date", ("Date",)),))
    theirs, _ = powerbi.relationships_model("Sales model", 0, [as_table(VIEW_ROWS)])
    assert conflicts(mine, theirs) == ["Sales -> Date: many-to-one becomes many-to-one (inactive)"]
    assert len(merge(mine, theirs).relationships) == 4  # the same join is replaced, not doubled
