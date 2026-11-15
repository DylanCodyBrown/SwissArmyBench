"""The Power BI workspace connection, against a stand-in on this computer (tests/powerbi_standin.py): no
real tenant is reached, and every value is made up. The connection is per workspace (the owner,
2026-11-15): the stand-in's workspace holds three datasets, two of them with a Date table, one that
answers with an error. The app registration's three values come from a made-up key vault written in
plain Python, as the owner's connection is made from their vault."""

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
from swissarmygrid.domain import notebooks, powerbi
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


SALES = "Sales model"
BUDGET = "Budget model"


def filled(code: str) -> str:
    """The starter's code with the made-up workspace's id in it."""
    return code.replace("my-workspace-id", made_up.WORKSPACE)


def connect(code: str = POWERBI_VAULT, secrets: dict[str, str] | None = None) -> tuple[Any, dict[str, Any]]:
    return run_code(filled(code), "conn", SECRETS if secrets is None else secrets, "Finance")


def query(conn: Any, dax: str, dataset: str = SALES) -> tuple[list[str], list[tuple[Any, ...]]]:
    cursor = conn.cursor(dataset=dataset)
    cursor.execute(dax)
    return [d[0] for d in cursor.description], cursor.fetchall()


def saved_connection(client: TestClient, name: str = "Finance", **more: Any) -> None:
    """The vault, then a Power BI workspace whose three values are that vault's entries."""
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
        form["label"] == "Power BI workspace"
        and form["connection"] == "database"
        and form["dialect"] == "dax"
    )
    assert [f["name"] for f in form["fields"]] == ["workspace_id"]  # the workspace alone: no dataset id
    assert "dataset_id" not in form["code"]
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
        "workspace_id", "tenant_id", "client_id",
    ]  # fmt: skip
    assert "client_secret" not in {s.key for s in detect_settings(POWERBI_VAULT)}
    browser = read_code(POWERBI_BROWSER)
    assert browser.secrets == [] and "azure.identity" in browser.imports
    assert [(s.name, s.value) for s in detect_settings(POWERBI_BROWSER)][-1] == ("tenant_id", "organizations")


def test_a_browser_sign_in_waits_for_first_use() -> None:
    assert signs_in_interactively(POWERBI_BROWSER)
    assert not signs_in_interactively(POWERBI_VAULT) and not signs_in_interactively(POWERBI_TYPED)


# ===== the workspace's datasets =====


def test_one_connection_reaches_every_dataset_by_name_or_id(standin: made_up.StandIn) -> None:
    conn, _ = connect()
    assert conn.datasets() == [
        {"name": SALES, "id": made_up.DATASET},
        {"name": BUDGET, "id": made_up.BUDGET_DATASET},
        {"name": "Broken model", "id": made_up.BROKEN_DATASET},
    ]
    # By name (any case), by id, as a cursor of the connection or of the dataset: the same thing.
    by_name = conn.dataset("budget MODEL").cursor()
    by_name.execute("EVALUATE 'Department'")
    assert [d[0] for d in by_name.description] == ["DepartmentKey", "Department"]
    assert len(by_name.fetchall()) == 3
    assert len(query(conn, "EVALUATE 'Department'", made_up.BUDGET_DATASET)[1]) == 3
    # A table of that name in each: each dataset answers with its own.
    assert query(conn, "EVALUATE 'Date'", SALES)[0] == ["Date", "Year", "Month"]
    assert query(conn, "EVALUATE 'Date'", BUDGET)[0] == ["Date", "Quarter"]
    # Several datasets and none named: refused, naming them. An unknown one: what the workspace has.
    with pytest.raises(Exception, match=r"has 3 datasets: name the one to read.*Sales model, Budget model"):
        conn.cursor()
    with pytest.raises(Exception, match=r"has no dataset 'Nope'\. It has: Sales model, Budget model, Broken"):
        conn.dataset("Nope")
    # A workspace of one dataset needs no name.
    standin.models = [made_up.BUDGET_MODEL]
    alone, _ = connect()
    cursor = alone.cursor()
    cursor.execute("EVALUATE TOPN(2, 'Budget')")
    assert len(cursor.fetchall()) == 2
    # Two datasets with one name are told apart by their ids.
    twin = made_up.MadeUpModel("99999999-0000-4000-8000-000000000000", BUDGET, {}, [], [], [])
    standin.models = [made_up.BUDGET_MODEL, twin]
    assert [d["name"] for d in connect()[0].datasets()] == [
        "Budget model (55555555)",
        "Budget model (99999999)",
    ]


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
    # Making the connection lists the workspace's datasets (Power BI's own request): Test means it.
    listed = next(r for r in standin.requests if r["what"] == "datasets")
    assert listed["path"] == f"/v1.0/myorg/groups/{made_up.WORKSPACE}/datasets"
    assert listed["authorization"] == f"Bearer {made_up.TOKEN}"
    assert not standin.queries()  # no dataset is asked anything yet
    query(conn, "EVALUATE TOPN(3, 'Sales')")
    asked = next(r for r in standin.requests if r["what"] == "query")
    assert asked["authorization"] == f"Bearer {made_up.TOKEN}" and asked["dataset"] == SALES
    assert asked["body"] == {
        "queries": [{"query": "EVALUATE TOPN(3, 'Sales')"}],
        "serializerSettings": {"includeNulls": True},
    }
    query(conn, "EVALUATE TOPN(3, 'Budget')", BUDGET)
    assert len([r for r in standin.requests if r["what"] == "datasets"]) == 1  # listed once
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
    # A workspace this sign-in cannot find: what to check.
    with pytest.raises(
        BladeRunError,
        match=r"Listing the workspace's datasets was refused \(404\): PowerBIEntityNotFound Check the "
        r"workspace id, and that this sign-in is a member",
    ):
        run_code(filled(POWERBI_VAULT).replace(made_up.WORKSPACE, "no-such-workspace"), "conn", SECRETS)
    # A dataset that answers with an error: its own words.
    with pytest.raises(Exception, match=r"The query was refused \(400\): The dataset is being refreshed"):
        query(conn, "EVALUATE 'Anything'", "Broken model")
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


def catalog_rows(
    standin: made_up.StandIn, dataset: str | None = SALES, command: str = POWERBI_CATALOG
) -> list[dict[str, Any]]:
    """The catalog command's rows: one dataset's (the schema), or with None every dataset's."""
    conn, names = connect()
    columns, rows = run_catalog(conn, names, "python", command, {}, "Finance")
    found = [dict(zip(columns, row, strict=True)) for row in rows]
    return [r for r in found if dataset is None or r["schema_name"] == dataset]


def test_the_catalog_is_the_workspace_each_dataset_a_schema(standin: made_up.StandIn) -> None:
    rows = catalog_rows(standin, None)
    assert list(dict.fromkeys(r["schema_name"] for r in rows)) == [SALES, BUDGET, "Broken model"]
    budget = [(r["table_name"], r["column_name"], r["data_type"]) for r in rows if r["schema_name"] == BUDGET]
    assert budget[:4] == [
        ("Budget", "BudgetKey", "Integer"),
        ("Budget", "DepartmentKey", "Integer"),
        ("Budget", "Month", "DateTime"),
        ("Budget", "Planned", "Decimal"),
    ]
    assert budget[-1] == ("Budget", "Total Planned", "measure, Decimal")
    # The dataset that could not be read: one row, no table, Power BI's own words. The others are whole.
    [broken] = [r for r in rows if r["schema_name"] == "Broken model"]
    assert broken["table_name"] == "" and broken["column_name"] == ""
    assert broken["description"].startswith("Could not be read: The query was refused (400): The dataset is")
    assert all(not r["description"] for r in rows if r is not broken)
    # Each dataset was asked by itself, one after another.
    assert standin.queries(BUDGET) == ["EVALUATE INFO.VIEW.COLUMNS()", "EVALUATE INFO.VIEW.MEASURES()"]


def test_the_catalog_reads_a_stated_number_of_datasets_and_says_which_it_left(
    standin: made_up.StandIn,
) -> None:
    assert "MAX_DATASETS = 25" in POWERBI_CATALOG and "MAX_SECONDS = 200" in POWERBI_CATALOG  # stated
    rows = catalog_rows(standin, None, POWERBI_CATALOG.replace("MAX_DATASETS = 25", "MAX_DATASETS = 1"))
    assert {r["schema_name"] for r in rows if r["table_name"]} == {SALES}
    left = {r["schema_name"]: r["description"] for r in rows if not r["table_name"]}
    assert left == {
        BUDGET: "Not read: the catalog reads a workspace's first 1 datasets.",
        "Broken model": "Not read: the catalog reads a workspace's first 1 datasets.",
    }
    assert not standin.queries(BUDGET) and not standin.queries("Broken model")  # never asked
    # Out of time: the datasets not reached say so; nothing is asked of them.
    rows = catalog_rows(standin, None, POWERBI_CATALOG.replace("MAX_SECONDS = 200", "MAX_SECONDS = -1"))
    assert {r["description"] for r in rows} == {"Not read: the catalog stops after -1 seconds."}
    # A workspace with no datasets at all says so.
    standin.models = []
    with pytest.raises(BladeRunError, match="has no datasets this sign-in may read"):
        catalog_rows(standin, None)


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
    assert standin.queries(SALES) == ["EVALUATE INFO.VIEW.COLUMNS()", "EVALUATE INFO.VIEW.MEASURES()"]


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
    refreshed = client.post("/blades/Finance/refresh", json={}, headers=AUTH)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["catalog"]["tables"] == 7 and refreshed.json()["catalog"]["dialect"] == "dax"
    # The tree's second level: the datasets, the one that could not be read marked with why.
    schemas = client.get("/catalogs/Finance/schemas", headers=AGENT).json()["schemas"]
    assert [(s["schema"], s["tables"]) for s in schemas] == [("Broken model", 0), (BUDGET, 3), (SALES, 4)]
    assert schemas[0]["note"].startswith("Could not be read: The query was refused (400)")
    assert "note" not in schemas[1] and "note" not in schemas[2]
    tables = client.get("/catalogs/Finance/tables?schema=Sales%20model", headers=AGENT).json()["tables"]
    assert [t["table"] for t in tables] == TABLES and tables[3]["columns"] == 9
    budget = client.get("/catalogs/Finance/tables?schema=Budget%20model", headers=AGENT).json()["tables"]
    assert [t["table"] for t in budget] == ["Budget", "Date", "Department"]
    assert client.get("/catalogs/Finance/tables?schema=Broken%20model", headers=AGENT).json()["tables"] == []
    sales = client.get("/catalogs/Finance/columns?schema=Sales%20model&table=Sales", headers=AGENT).json()
    assert sales["dialect"] == "dax" and sales["select"] == "EVALUATE TOPN(100, 'Sales')"
    assert {"column": "Total Sales", "type": "measure, Decimal"}.items() <= sales["columns"][7].items()
    found = client.get("/catalogs/Finance/search?q=total", headers=AGENT).json()
    assert [(c["schema"], c["column"]) for c in found["columns"]] == [
        (SALES, "Total Sales"),
        (BUDGET, "Total Planned"),
    ]  # a measure is found by name, in its dataset
    assert all(
        t["table"] for t in client.get("/catalogs/Finance/search?q=model", headers=AGENT).json()["tables"]
    )


def test_the_datasets_are_listed_from_the_catalog_or_from_power_bi(
    client: TestClient, standin: made_up.StandIn
) -> None:
    saved_connection(client)
    # A page that only lists (the Workbench's DAX picker) never asks Power BI: none until the catalog.
    before = len(standin.requests)
    quiet = client.get("/connections/Finance/datasets?live=0", headers=AUTH).json()
    assert quiet == {"connection": "Finance", "datasets": [], "from": "none"}
    assert len(standin.requests) == before
    # No catalog yet: asked of Power BI, names and ids, each named as a DAX cell names it.
    asked = client.get("/connections/Finance/datasets", headers=AGENT)
    assert asked.status_code == 200, asked.text
    assert asked.json() == {
        "connection": "Finance",
        "from": "powerbi",
        "datasets": [
            {"name": SALES, "id": made_up.DATASET, "cell": "Finance/Sales model"},
            {"name": BUDGET, "id": made_up.BUDGET_DATASET, "cell": "Finance/Budget model"},
            {"name": "Broken model", "id": made_up.BROKEN_DATASET, "cell": "Finance/Broken model"},
        ],
    }
    # With the catalog loaded: from it (nothing is asked of Power BI), the unread one with its note.
    assert client.post("/blades/Finance/refresh", json={}, headers=AUTH).status_code == 200
    before = len(standin.requests)
    listed = client.get("/connections/Finance/datasets", headers=AUTH).json()
    assert listed["from"] == "catalog" and len(standin.requests) == before
    assert client.get("/connections/Finance/datasets?live=0", headers=AUTH).json() == listed
    assert [d["cell"] for d in listed["datasets"]] == [
        "Finance/Broken model", "Finance/Budget model", "Finance/Sales model",
    ]  # fmt: skip
    assert (
        listed["datasets"][0]["note"].startswith("Could not be read") and "note" not in listed["datasets"][1]
    )
    # The agent's command asks Power BI itself.
    live = client.get("/connections/Finance/datasets?live=1", headers=AGENT).json()
    assert live["from"] == "powerbi" and len(standin.requests) > before
    for answer in (asked.text, listed, live):
        assert not any(value in str(answer) for value in NOT_TO_BE_SEEN)


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
        pointed = call("POST", "/connections/source", body | {"connection": "Finance"})
        code = pointed["code"]
    assert 'tenant_id = secret("powerbi_tenant_id")' in code
    assert 'client_id = secret("powerbi_client_id")' in code
    assert 'client_secret = secret("powerbi_client_secret")' in code  # the name an Azure Function reads too
    draft = {"name": "Finance", "kind": "sql", "template": "powerbi", "dialect": "dax", "code": code}
    draft |= {"variable": "conn", "catalog": BY_ID["powerbi"].to_json()["catalog"]}
    # Test connection (nothing saved): the vault runs first, the sign-in carries its three values.
    tested = call("POST", "/connections/test", draft)
    assert tested["ok"] is True and tested["type"].endswith("PowerBI")
    assert tested["found"] == "signed in and found 3 datasets"  # what Test says it did
    token = next(r for r in standin.requests if r["what"] == "token")
    assert (token["tenant"], token["form"]["client_id"], token["form"]["client_secret"]) == (
        made_up.TENANT, made_up.CLIENT, made_up.SECRET,
    )  # fmt: skip
    call("POST", "/connections", draft)
    # Everything the page and the agent can then ask about it.
    shown = call("GET", "/connections/Finance", headers=AGENT)
    assert shown["secrets"] == ["powerbi_tenant_id", "powerbi_client_id", "powerbi_client_secret"]
    assert shown["summary"]["vaults"] == ["Team vault"]
    call("GET", "/connections", headers=AGENT)
    call("GET", "/blades", headers=AGENT)
    call("GET", "/connections/vaults", headers=AGENT)
    call("POST", "/blades/Finance/test", {}, AGENT)
    call("GET", "/connections/Finance/datasets?live=1", headers=AGENT)
    call("POST", "/blades/Finance/refresh", {}, AGENT)
    call("GET", "/connections/Finance/datasets", headers=AGENT)
    call("GET", "/catalogs/Finance/schemas", headers=AGENT)
    call("POST", "/connections/Finance/open", {"schema": SALES, "table": "Customer"}, AGENT)
    call("POST", "/connections/Finance/preview", {"schema": BUDGET, "table": "Budget"}, AGENT)
    call("POST", "/connections/Finance/relationships", {"dataset": SALES}, AGENT)
    # A refusal, too: a query Power BI turns down, and a sign-in Microsoft turns down.
    refused = client.post("/connections/Finance/open", json={"schema": SALES, "table": "Nope"}, headers=AGENT)
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
    tested = client.post("/blades/Finance/test", json={}, headers=AUTH)
    assert tested.status_code == 422
    assert "The sign-in was refused (401): AADSTS7000215" in tested.text
    assert "made-up-stale-secret-0009" not in tested.text


# ===== open as grid =====


def test_a_table_opens_as_a_grid_its_first_rows_counted_then_all(
    client: TestClient, standin: made_up.StandIn
) -> None:
    saved_connection(client, row_limit=10)
    where = {"schema": SALES, "table": "Sales"}
    opened = client.post("/connections/Finance/open", json=where, headers=AGENT)
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
        "connection": "Finance", "database": "", "schema": SALES, "table": "Sales", "shown": 10, "total": 40,
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
    every = client.post("/connections/Finance/open", json=where | {"all": True}, headers=AUTH)
    grid = client.get(f"/grids/{every.json()['grid']}", headers=AUTH).json()
    assert grid["row_count"] == 40 and grid["opened"] is None
    assert standin.queries()[-1] == "EVALUATE 'Sales'"
    preview = client.post(
        "/connections/Finance/preview", json={"schema": SALES, "table": "Customer"}, headers=AUTH
    ).json()
    assert preview["columns"] == ["CustomerKey", "Customer Name", "Region"] and len(preview["rows"]) == 8
    assert preview["rows"][2][2] is None  # a customer with no region
    # In a notebook the table's cell reads it again the way the docs teach: sag.dax, on its dataset.
    cells = {t["name"]: t for t in client.get("/workbench/tables", headers=AUTH).json()["tables"]}
    assert "Sales = sag.dax('Finance/Sales model', \"\"\"\nEVALUATE 'Sales'\n" in cells["Sales"]["loaded"]
    # The second dataset's table: its rows come from that dataset, the count too.
    second = client.post(
        "/connections/Finance/open", json={"schema": BUDGET, "table": "Budget"}, headers=AUTH
    )
    assert second.status_code == 200, second.text
    assert (second.json()["dataset"], second.json()["shown"], second.json()["total"]) == ("Budget", 10, 24)
    assert standin.queries(BUDGET) == [
        "EVALUATE TOPN(10, 'Budget')",
        """EVALUATE ROW("n", COUNTROWS('Budget'))""",
    ]
    # A dataset is needed where the workspace has several, and an unknown one says what there is.
    refused = client.post("/connections/Finance/open", json={"table": "Sales"}, headers=AUTH)
    assert refused.status_code == 422 and "has 3 datasets: name the one to read" in refused.text
    refused = client.post(
        "/connections/Finance/open", json={"schema": "Nope", "table": "Sales"}, headers=AUTH
    )
    assert refused.status_code == 422 and "has no dataset 'Nope'. It has: Sales model" in refused.text


def test_a_table_two_datasets_share_opens_under_its_datasets_name_too(
    client: TestClient, standin: made_up.StandIn
) -> None:
    assert powerbi.grid_name(SALES, "Date") == "Date"  # its own name
    assert powerbi.grid_name(SALES, "Date", {"date"}) == "Sales_model_Date"  # shared: the dataset's first
    assert powerbi.grid_name(SALES, "Order Lines", {"date"}) == "Order_Lines"  # only the shared one
    assert powerbi.grid_name("", "Date", {"date"}) == "Date"  # a connection that is one dataset
    saved_connection(client)
    assert client.post("/blades/Finance/refresh", json={}, headers=AUTH).status_code == 200  # the catalog

    def open_table(dataset: str, table: str) -> dict[str, Any]:
        answer = client.post(
            "/connections/Finance/open", json={"schema": dataset, "table": table}, headers=AUTH
        )
        assert answer.status_code == 200, answer.text
        opened: dict[str, Any] = answer.json()
        return opened

    sales_date, budget_date = open_table(SALES, "Date"), open_table(BUDGET, "Date")
    assert sales_date["dataset"] == "Sales_model_Date" and budget_date["dataset"] == "Budget_model_Date"
    assert sales_date["grid"] != budget_date["grid"]  # two grids, neither replaced the other
    columns = [c["name"] for c in client.get(f"/grids/{budget_date['grid']}", headers=AUTH).json()["columns"]]
    assert columns == ["Date", "Quarter"]  # the Budget model's own Date table
    columns = [c["name"] for c in client.get(f"/grids/{sales_date['grid']}", headers=AUTH).json()["columns"]]
    assert columns == ["Date", "Year", "Month"]
    # A name only one dataset has stays as it is.
    assert open_table(SALES, "Customer")["dataset"] == "Customer"
    assert open_table(BUDGET, "Department")["dataset"] == "Department"
    names = {d["name"] for d in client.get("/datasets", headers=AUTH).json()["datasets"]}
    assert {
        "Sales_model_Date",
        "Budget_model_Date",
        "Customer",
        "Department",
    } <= names and "Date" not in names


# ===== a DAX cell =====


@pytest.fixture
def cell(standin: made_up.StandIn, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A notebook's Python, with the server stood in for as tests/test_sql_cell.py does."""
    listed: list[dict[str, Any]] = [
        {"name": "Finance", "kind": "sql", "connection": "database", "dialect": "dax", "template": "powerbi"},
        {"name": "Warehouse", "kind": "sql", "connection": "database", "dialect": "sqlite"},
    ]
    monkeypatch.setattr(
        blades_client, "_call", lambda method, path, *_: {"connections": listed, "blades": listed}
    )

    def made(name: str) -> Any:
        if name == "Warehouse":
            import sqlite3

            return sqlite3.connect(":memory:")
        return connect()[0]

    monkeypatch.setattr(blades_client, "blade", made)
    monkeypatch.setattr(sql_cell, "_connections", {})
    monkeypatch.setattr(sql_cell, "_workspaces", {})
    monkeypatch.setattr(sql_cell, "_default", [])
    yield


def test_sag_dax_names_the_dataset_after_the_connection_and_gives_a_frame(
    cell: None, standin: made_up.StandIn
) -> None:
    frame = sql_cell.dax("Finance/Sales model", "EVALUATE TOPN(5, 'Customer')")
    assert isinstance(frame, pd.DataFrame)
    assert list(frame.columns) == ["CustomerKey", "Customer Name", "Region"] and len(frame) == 5
    # A closing semicolon and a comment line are fine.
    text = "-- Sales by region\n"
    text += """EVALUATE SUMMARIZECOLUMNS('Customer'[Region], "Total Sales", [Total Sales]);"""
    totals = sql_cell.dax("Finance/Sales model", text)
    assert list(totals.columns) == ["Region", "Total Sales"] and len(totals) == 4
    # Another dataset of the same workspace, by name (any case) or id: signed in once for them all.
    budget = sql_cell.dax("finance/budget model", "EVALUATE 'Department'")
    assert list(budget.columns) == ["DepartmentKey", "Department"]
    assert len(sql_cell.dax(f"Finance/{made_up.BUDGET_DATASET}", "EVALUATE 'Department'")) == 3
    assert len([r for r in standin.requests if r["what"] == "token"]) == 1
    assert len([r for r in standin.requests if r["what"] == "datasets"]) == 1
    # sag.sql on a dataset is the same call underneath.
    assert len(sql_cell.sql("Finance/Sales model", "EVALUATE TOPN(5, 'Customer')")) == 5
    found = sql_cell.connection("Finance/Sales model")
    assert (found.name, found.describe, found.language) == (
        "Finance/Sales model", "a Power BI dataset (DAX)", "dax",
    )  # fmt: skip
    assert sql_cell.listing() == [
        ("Finance", "a Power BI workspace: a DAX cell names a dataset, %%dax Finance/<dataset>"),
        ("Warehouse", "database (sqlite SQL)"),
    ]
    import swissarmygrid as sag

    assert sag.dax is sql_cell.dax and "dax" in sag.__all__


def test_a_workspace_with_several_datasets_wants_one_named(cell: None, standin: made_up.StandIn) -> None:
    with pytest.raises(sql_cell.SqlCellError) as refused:
        sql_cell.dax("Finance", "EVALUATE 'Sales'")
    assert str(refused.value) == (
        "Finance is a Power BI workspace with 3 datasets: name one, as Finance/Sales model. "
        "It has: Sales model, Budget model, Broken model."
    )
    with pytest.raises(
        sql_cell.SqlCellError, match=r"Finance: The workspace has no dataset 'Nope'\. It has:"
    ):
        sql_cell.dax("Finance/Nope", "EVALUATE 'Sales'")
    # DAX is for a Power BI dataset only; a database's name takes no dataset.
    with pytest.raises(sql_cell.SqlCellError, match="Warehouse is not a Power BI workspace's dataset"):
        sql_cell.dax("Warehouse", "EVALUATE 'Sales'")
    with pytest.raises(sql_cell.SqlCellError, match="Warehouse is not a Power BI workspace: name it alone"):
        sql_cell.sql("Warehouse/main", "SELECT 1")
    with pytest.raises(sql_cell.SqlCellError, match="The cell has no DAX to run"):
        sql_cell.dax("Finance/Sales model", "  ")
    # A workspace of one dataset: the connection's name is enough.
    standin.models = [made_up.SALES_MODEL]
    sql_cell._workspaces.clear()
    assert len(sql_cell.dax("Finance", "EVALUATE 'Customer'")) == 8
    assert sql_cell.connection("Finance").name == "Finance/Sales model"


def test_the_magic_keeps_the_result_and_says_power_bis_refusal_in_one_line(cell: None) -> None:
    class Shell:
        def __init__(self) -> None:
            self.user_ns: dict[str, Any] = {}

        def find_cell_magic(self, name: str) -> None:
            return None

        def find_line_magic(self, name: str) -> None:
            return None

        def register_magic_function(self, fn: Any, magic_kind: str, magic_name: str) -> None:
            self.user_ns[f"%{magic_kind}:{magic_name}"] = fn

    shell = Shell()
    assert "%%dax" in sql_cell.register(shell)  # beside %%sql, in any Jupyter with the client
    run = shell.user_ns["%cell:dax"]
    result = run('"Finance/Sales model" -> customers', "EVALUATE 'Customer'")  # the line a DAX cell runs as
    assert len(result) == 8 and shell.user_ns["customers"] is result
    assert len(run("Finance/Sales\\ model", "EVALUATE 'Customer'")) == 8
    with pytest.raises(
        Exception, match=r"Finance/Sales model: PowerBIError: The query was refused .* Cannot find table"
    ):
        run('"Finance/Sales model"', "EVALUATE 'Nope'")
    # Refusals in one line, said as a DAX cell's.
    with pytest.raises(
        Exception, match=r"DAX cell: Finance is a Power BI workspace with 3 datasets: name one"
    ):
        run("Finance", "EVALUATE 'Customer'")
    with pytest.raises(Exception, match=r"DAX cell: Warehouse is not a Power BI workspace's dataset"):
        run("Warehouse", "EVALUATE 'Customer'")
    with pytest.raises(Exception, match=r"DAX cell: Name the dataset: %%dax <connection>/<dataset>"):
        run("", "EVALUATE 'Customer'")
    # A %%sql cell on a dataset (a notebook saved before DAX cells) still runs.
    assert len(shell.user_ns["%cell:sql"]('"Finance/Sales model"', "EVALUATE 'Customer'")) == 8


def test_a_dax_cell_is_a_code_cell_that_starts_with_its_dax_line() -> None:
    assert "dax" in notebooks.KINDS
    cell = notebooks.Cell("dax", "EVALUATE TOPN(10, 'Sales')", "Finance/Sales model", number=3)
    assert notebooks.dax_line("Finance/Sales model") == "%%dax 'Finance/Sales model'"
    assert (
        notebooks.dax_line("Finance/Sales") == "%%dax Finance/Sales" and notebooks.dax_line(None) == "%%dax"
    )
    assert notebooks.code_of(cell) == "%%dax 'Finance/Sales model'\nEVALUATE TOPN(10, 'Sales')"
    text = notebooks.write_notebook([cell, notebooks.Cell("sql", "SELECT 1", "Warehouse")])
    import json

    raw = json.loads(text)["cells"][0]
    assert raw["cell_type"] == "code"  # plain Jupyter with the client runs it as it is
    assert raw["source"] == ["%%dax 'Finance/Sales model'\n", "EVALUATE TOPN(10, 'Sales')"]
    assert raw["metadata"]["swissarmygrid"] == {
        "kind": "dax",
        "connection": "Finance/Sales model",
        "number": 3,
    }
    back = notebooks.read_notebook(text)
    assert [(c.kind, c.connection, c.source) for c in back] == [
        ("dax", "Finance/Sales model", "EVALUATE TOPN(10, 'Sales')"),
        ("sql", "Warehouse", "SELECT 1"),
    ]
    # A cell saved before DAX cells, `%%sql Finance/Sales model`, opens as a DAX cell: only a
    # workspace's dataset is named with a slash. A SQL cell on a plain connection stays one.
    old = json.loads(text)
    old["cells"][0]["source"] = ["%%sql 'Finance/Sales model'\n", "EVALUATE 'Sales'"]
    old["cells"][0]["metadata"] = {"swissarmygrid": {"kind": "sql", "connection": "Finance/Sales model"}}
    assert [(c.kind, c.connection) for c in notebooks.read_notebook(json.dumps(old))] == [
        ("dax", "Finance/Sales model"),
        ("sql", "Warehouse"),
    ]
    # Read by its first line alone (a notebook written in Jupyter, no marks).
    plain = json.loads(text)
    for one in plain["cells"]:
        one["metadata"] = {}
    assert [c.kind for c in notebooks.read_notebook(json.dumps(plain))] == ["dax", "sql"]
    # The page's cells: a DAX cell's connection may be long (a connection, a slash, a dataset's name).
    long_name = "Finance/" + "A long dataset name " * 5
    sent = notebooks.read_cells(
        [{"kind": "dax", "source": "EVALUATE 'Sales'", "connection": long_name.strip()}]
    )
    assert sent[0].kind == "dax" and sent[0].connection == long_name.strip()
    with pytest.raises(notebooks.NotebookError, match='"code", "sql", "dax", "html" or "markdown"'):
        notebooks.read_cells([{"kind": "m", "source": ""}])
    assert powerbi.split_name("Finance/Sales model") == ("Finance", "Sales model")
    assert powerbi.split_name("Finance") == ("Finance", "") and powerbi.split_name("F/a/b") == ("F", "a/b")
    assert powerbi.joined_name("Finance", "Sales model") == "Finance/Sales model"
    assert powerbi.joined_name("Finance", "") == "Finance"


def test_a_script_keeps_a_dax_cell_as_python_under_its_marker() -> None:
    from swissarmygrid.domain.table_cells import arrange_script, parse_script

    script = (
        "import swissarmygrid as sag\n"
        "# %% [1] [dax] Sales by region\n"
        'by_region = sag.dax("Finance/Sales model", """\n'
        "EVALUATE SUMMARIZECOLUMNS('Customer'[Region], \"Total Sales\", [Total Sales])\n"
        '""")\n'
    )
    parsed = parse_script(script)
    assert parsed.cells[-1].title == "[dax] Sales by region" and parsed.cells[-1].number == 1
    assert arrange_script(script, [])[0] == script  # the file runs as plain Python, and is kept as written
    compile(script, "script.py", "exec")


def test_a_dax_cell_gets_no_uses_line() -> None:
    """DAX names its dataset's own tables, never the kernel's: `Sales` in a DAX cell is not the open
    table Sales, so the app writes no uses line on it (a SQL cell beside it gets one)."""
    from swissarmygrid.domain.table_cells import PlanCell, TableSpec, arrange

    cells = [
        PlanCell(1, "code", "Sales = 1"),
        PlanCell(2, "dax", "EVALUATE TOPN(10, Sales)"),
        PlanCell(3, "sql", "SELECT * FROM Sales"),
    ]
    spec = TableSpec(
        "Sales", 'import duckdb\n\nSales = duckdb.sql("""\nSELECT * FROM Sales\n""").df()', "", 1
    )
    arranged = {c.number: c for c in arrange(cells, [spec], 4).cells if c.kind in ("dax", "sql")}
    assert arranged[2].uses is None and arranged[2].source == "EVALUATE TOPN(10, Sales)"
    assert arranged[3].uses is not None and arranged[3].uses.startswith("-- uses Sales @cell")


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
    model, skipped = powerbi.relationships_model("Finance", 0, [as_table(VIEW_ROWS)], SALES)
    assert skipped == 1  # the one to the date table Power BI made by itself
    assert model.name == "Finance Sales model"
    assert model.relationships == (
        Relationship("Sales", ("CustomerKey",), "Customer", ("CustomerKey",), "many-to-one"),
        Relationship(
            "Sales", ("ProductKey",), "Product", ("ProductKey",), "many-to-one", "filters both ways"
        ),
        Relationship("Sales", ("Order Date",), "Date", ("Date",), "many-to-one"),
        Relationship("Sales", ("Ship Date",), "Date", ("Date",), "many-to-one", active=False),
    )
    assert model.sources["Sales"] == "Finance/Sales model (Power BI)"
    # A table another dataset of the workspace has too is named as it opens as a grid.
    shared, _ = powerbi.relationships_model("Finance", 0, [as_table(VIEW_ROWS)], SALES, {"date"})
    assert [(r.from_table, r.to_table) for r in shared.relationships][2:] == [
        ("Sales", "Sales_model_Date"), ("Sales", "Sales_model_Date"),
    ]  # fmt: skip
    assert sorted(shared.sources) == ["Customer", "Product", "Sales", "Sales_model_Date"]
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
    named, _ = powerbi.relationships_model("Finance", 0, [as_table(VIEW_ROWS)], SALES)
    numbered = [
        as_table(made_up.evaluate(f"EVALUATE INFO.{f}()")) for f in ("RELATIONSHIPS", "TABLES", "COLUMNS")
    ]
    model, skipped = powerbi.relationships_model("Finance", 1, numbered, SALES)
    assert model == named and skipped == 1
    with pytest.raises(powerbi.PowerBIError, match=r"a table or column .* it did not list"):
        powerbi.relationships_model(
            "Finance", 1, [numbered[0], numbered[1], as_table([{"ID": 1, "Name": "x"}])]
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
    # Several datasets and none named: refused, naming them.
    unnamed = client.post("/connections/Finance/relationships", json={}, headers=AGENT)
    assert unnamed.status_code == 400
    assert unnamed.text == (
        "Finance has several datasets: name the one to import. It has: Sales model, Budget model, "
        "Broken model."
    )
    imported = client.post(
        "/connections/Finance/relationships", json={"dataset": SALES}, headers=AGENT
    )  # the agent may
    assert imported.status_code == 200, imported.text
    answer = imported.json()
    assert answer["dataset"] == SALES
    assert answer["changed"] == ["Sales -> Customer: one-to-one becomes many-to-one"]  # the dataset's wins
    assert answer["tables"] == ["Customer", "Date", "Product", "Sales"] and answer["skipped"] == 1
    assert len(answer["imported"]) == 4
    assert standin.queries()[-1] == "EVALUATE INFO.VIEW.RELATIONSHIPS()"
    current = client.get("/relationships", headers=AUTH).json()
    assert current == answer["model"] and current["name"] == "Mine + Finance Sales model"
    joins = {(r["from"], r["from_columns"][0], r["to"]): r for r in current["relationships"]}
    assert len(joins) == 5 and joins[("Returns", "SalesKey", "Sales")]["kind"] == "many-to-one"  # kept
    assert joins[("Sales", "CustomerKey", "Customer")]["kind"] == "many-to-one"
    assert joins[("Sales", "Ship Date", "Date")]["active"] is False  # inactive stays inactive
    assert "active" not in joins[("Sales", "Order Date", "Date")]
    assert joins[("Sales", "ProductKey", "Product")]["note"] == "filters both ways"
    assert current["tables"]["Sales"]["source"] == "Finance/Sales model (Power BI)"
    # A second import changes nothing; an older model answers through the numbered form, the same.
    standin.view_forms = False
    again = client.post(
        "/connections/Finance/relationships", json={"dataset": made_up.DATASET}, headers=AUTH
    ).json()  # by its id
    assert again["changed"] == [] and again["imported"] == answer["imported"]
    assert standin.queries()[-3:] == [
        "EVALUATE INFO.RELATIONSHIPS()", "EVALUATE INFO.TABLES()", "EVALUATE INFO.COLUMNS()",
    ]  # fmt: skip
    assert len(client.get("/relationships", headers=AUTH).json()["relationships"]) == 5
    # The Diagram draws them once the tables are open.
    for table in TABLES:
        where = {"schema": SALES, "table": table}
        assert client.post("/connections/Finance/open", json=where, headers=AUTH).status_code == 200
    erd = client.get("/relationships/erd", headers=AUTH).json()
    assert set(erd["tables"]) == set(TABLES) and "Sales" in erd["mermaid"]
    dashed = [line.strip() for line in erd["mermaid"].splitlines() if ".." in line]
    assert len(dashed) == 1 and dashed[0].endswith(': "inactive"')  # the Ship Date join: dashed, said so
    assert {dashed[0].split()[0], dashed[0].split()[2]} == {"Sales", "Date"}
    # Neither form answered: Power BI's own refusal, from the first one tried.
    standin.info_forms = False
    refused = client.post("/connections/Finance/relationships", json={"dataset": SALES}, headers=AUTH)
    assert refused.status_code == 422 and "Failed to resolve name 'INFO.VIEW.RELATIONSHIPS'" in refused.text
    # The dataset that answers with an error says so; nothing changes.
    refused = client.post(
        "/connections/Finance/relationships", json={"dataset": "Broken model"}, headers=AUTH
    )
    assert refused.status_code == 422 and "The dataset is being refreshed" in refused.text
    assert len(client.get("/relationships", headers=AUTH).json()["relationships"]) == 5


def test_each_datasets_relationships_come_by_themselves_named_as_the_grids_are(
    client: TestClient, standin: made_up.StandIn
) -> None:
    saved_connection(client)
    assert client.post("/blades/Finance/refresh", json={}, headers=AUTH).status_code == 200  # the catalog
    budget = client.post("/connections/Finance/relationships", json={"dataset": BUDGET}, headers=AUTH)
    assert budget.status_code == 200, budget.text
    # Only the Budget model's two; its Date table is named as it opens as a grid (both datasets have one).
    assert [(r["from"], r["from_columns"], r["to"]) for r in budget.json()["imported"]] == [
        ("Budget", ["DepartmentKey"], "Department"),
        ("Budget", ["Month"], "Budget_model_Date"),
    ]
    assert budget.json()["tables"] == ["Budget", "Budget_model_Date", "Department"]
    assert standin.queries(BUDGET)[-1] == "EVALUATE INFO.VIEW.RELATIONSHIPS()"
    assert "EVALUATE INFO.VIEW.RELATIONSHIPS()" not in standin.queries(SALES)  # the other was not asked
    sales = client.post("/connections/Finance/relationships", json={"dataset": SALES}, headers=AUTH).json()
    assert sales["tables"] == ["Customer", "Product", "Sales", "Sales_model_Date"]
    model = client.get("/relationships", headers=AUTH).json()
    assert len(model["relationships"]) == 6 and model["name"] == "Finance Budget model + Finance Sales model"
    assert model["tables"]["Budget_model_Date"]["source"] == "Finance/Budget model (Power BI)"
    assert model["tables"]["Sales_model_Date"]["source"] == "Finance/Sales model (Power BI)"
    # The joins match the grids: each Date opens under the name the model has for it.
    for dataset, table in ((BUDGET, "Budget"), (BUDGET, "Date"), (SALES, "Sales"), (SALES, "Date")):
        where = {"schema": dataset, "table": table}
        assert client.post("/connections/Finance/open", json=where, headers=AUTH).status_code == 200
    erd = client.get("/relationships/erd", headers=AUTH).json()
    assert set(erd["tables"]) == {"Budget", "Budget_model_Date", "Sales", "Sales_model_Date"}


def test_a_connection_saved_for_one_dataset_still_works(client: TestClient, standin: made_up.StandIn) -> None:
    """Before 2026-11-15 the connection was per dataset: its saved code makes one dataset, with no
    list of datasets. It is a workspace of one: no dataset is named anywhere."""
    saved_connection(client)
    saved = client.get("/blades/Finance", headers=AUTH).json()
    old = saved["code"] + '\ndataset_id = "' + made_up.DATASET + '"\nconn = conn.dataset(dataset_id)\n'
    body = {"name": "Old model", "kind": "sql", "template": "powerbi", "dialect": "dax", "code": old}
    body |= {"variable": "conn", "row_limit": 10}
    assert client.post("/connections", json=body, headers=AUTH).status_code == 200
    form = client.get("/connections/Old%20model", headers=AUTH).json()
    assert [f["name"] for f in form["fields"]] == ["workspace_id", "dataset_id"]  # its own code's fields
    listed = client.get("/connections/Old%20model/datasets", headers=AUTH).json()
    assert listed["datasets"] == [{"name": "", "cell": "Old model"}]
    opened = client.post("/connections/Old%20model/open", json={"table": "Customer"}, headers=AUTH)
    assert opened.status_code == 200 and opened.json()["dataset"] == "Customer"
    imported = client.post("/connections/Old%20model/relationships", json={}, headers=AUTH)
    assert imported.status_code == 200 and len(imported.json()["imported"]) == 4
    assert client.get("/relationships", headers=AUTH).json()["tables"]["Sales"]["source"] == (
        "Old model (Power BI)"
    )


def test_only_a_power_bi_dataset_has_relationships_to_import(client: TestClient, tmp_path: Path) -> None:
    file = tmp_path / "orders.csv"
    file.write_text("order_id\n1\n", encoding="utf-8")
    body = {"name": "Orders", "kind": "other", "template": "csv"}
    body |= {"code": f'from pathlib import Path\npath = Path(r"{file}")'}
    assert client.post("/connections", json=body, headers=AUTH).status_code == 200
    refused = client.post("/connections/Orders/relationships", json={}, headers=AUTH)
    assert refused.status_code == 400 and "is not a Power BI workspace" in refused.text
    refused = client.get("/connections/Orders/datasets", headers=AUTH)
    assert refused.status_code == 400 and "is not a Power BI workspace" in refused.text


def test_merging_keeps_the_existing_rules() -> None:
    mine = Model("Mine", relationships=(Relationship("Sales", ("Ship Date",), "Date", ("Date",)),))
    theirs, _ = powerbi.relationships_model("Finance", 0, [as_table(VIEW_ROWS)], SALES)
    assert conflicts(mine, theirs) == ["Sales -> Date: many-to-one becomes many-to-one (inactive)"]
    assert len(merge(mine, theirs).relationships) == 4  # the same join is replaced, not doubled


def test_the_agents_commands_list_datasets_import_one_and_add_a_dax_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The golden rule: what the page does with a workspace, the agent does by a command."""
    from swissarmygrid.cli import api, commands

    sent: list[tuple[str, str, Any]] = []

    def call(method: str, path: str, body: Any = None) -> Any:
        sent.append((method, path, body))
        return {"result": {}}

    monkeypatch.setattr(api, "call", call)
    commands.REGISTRY["connections_datasets"].run({"name": "Finance"})
    commands.REGISTRY["connections_import_relationships"].run({"name": "Finance", "dataset": SALES})
    commands.REGISTRY["connections_import_relationships"].run({"name": "Old model"})
    added = {"dataset": "Finance/Sales model", "source": "EVALUATE 'Sales'"}
    commands.REGISTRY["workbench_dax_add"].run(added)
    assert sent == [
        ("GET", "/connections/Finance/datasets?live=1", None),
        ("POST", "/connections/Finance/relationships", {"dataset": SALES}),
        ("POST", "/connections/Old%20model/relationships", {}),
        ("POST", "/workbench/window", {"command": "cell.addDax", "args": added}),
    ]
    run = {a.name: a.help for a in commands.REGISTRY["workbench_run"].args}
    assert "dax" in run["kind"] and "Finance/Sales model" in run["connection"]
