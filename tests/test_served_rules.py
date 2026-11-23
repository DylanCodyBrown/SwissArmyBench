"""Rules the pages used to copy, served as data instead (the front end / back end rule; the craft review of
2026-11-22, item 11): what the Connections pages draw for a connection's kind, what an In's source picker
offers on the Canvas, a vault secret's variable name. Made-up names only."""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import connection_usage as usage
from swissarmybench.domain.variable_refs import env_name_for_secret
from swissarmybench_streamlit.domain import canvas_wiring as wiring
from swissarmybench_streamlit.domain import widget_contract as contract
from swissarmybench_streamlit.domain.widget_contract import ContractError, Port
from tests.conftest import AUTH

# ===== a connection's kind, as the pages draw it =====


@pytest.mark.parametrize(
    ("connection", "dialect", "tables_kind", "group", "in_code", "actions", "query"),
    [
        (
            "database",
            "postgres",
            "database",
            "Databases",
            'sab.connection("Shop")  ·  %%sql Shop',
            [],
            {"dax": False, "type": "PostgreSQL"},
        ),
        (
            "database",
            "sqlserver",
            "database",
            "Databases",
            'sab.connection("Shop")  ·  %%sql Shop',
            ["import_relationships"],
            {"dax": False, "type": "PostgreSQL"},
        ),
        (
            "database",
            "dax",
            "powerbi",
            "Databases",
            'sab.dax("Shop/<dataset>", …)  ·  %%dax Shop/<dataset>',
            [],
            {"dax": True, "type": "PostgreSQL"},
        ),
        (
            "database",
            "dataverse",
            "dataverse_web",
            "Databases",
            'sab.connection("Shop")  ·  sab.read("Shop", table)  ·  %%sql Shop',
            ["sql_endpoint"],
            None,
        ),
        (
            "database",
            "sharepoint",
            "sharepoint",
            usage.LAKE_GROUP,
            'sab.connection("Shop")  ·  sab.read("Shop", table)',
            [],
            {"dax": False, "type": "PostgreSQL"},
        ),
        (
            "database",
            "onelake",
            "onelake",
            usage.LAKE_GROUP,
            'sab.connection("Shop")  ·  sab.read("Shop", table)  ·  %%sql Shop',
            [],
            {"dax": False, "type": "PostgreSQL"},
        ),
        ("file", None, "file", "Files", 'sab.connection("Shop")  ·  %%sql Shop', [], None),
        (
            "python",
            None,
            "python",
            "Your own code",
            'sab.connection("Shop")  ·  sab.read("Shop", table)',
            [],
            None,
        ),
        ("vault", None, None, "", 'sab.blade("Shop")', [], None),
    ],
)
def test_a_kinds_facts(
    connection: str,
    dialect: str | None,
    tables_kind: str | None,
    group: str,
    in_code: str,
    actions: list[str],
    query: dict[str, Any] | None,
) -> None:
    facts = usage.kind_facts("Shop", connection, dialect, tables_kind, "PostgreSQL")
    assert (facts["group"], facts["in_code"], facts["actions"], facts["query"]) == (
        group,
        in_code,
        actions,
        query,
    )
    assert facts["has_tables"] is (tables_kind is not None)
    assert facts["test_reads"] is (connection == "python" or usage.reads_by_code(dialect))


def test_the_other_facts_of_a_kind() -> None:
    assert usage.kind_facts("Finance Captive", "database", "postgres", "database")["in_code"] == (
        'sab.connection("Finance Captive")  ·  %%sql "Finance Captive"'  # a name with a space is quoted
    )
    api = usage.kind_facts("Orders", "python", None, "api")
    assert not api["on_connections_page"] and not api["has_tables"]  # an API has the APIs page
    assert usage.kind_facts("W", "database", "dax", "powerbi")["query"]["type"] == "Power BI workspace"
    assert usage.kind_facts("W", "database", "duckdb", "database")["query"]["type"] == "Database"
    assert usage.kind_facts("W", "database", "sqlserver", "database")["test_tells_about"]
    assert usage.group_facts("powerbi") == {"icon": "diagram", "relationships": True, "open_single": False}
    assert usage.group_facts("database") == {"icon": "folder", "relationships": False, "open_single": True}
    assert usage.secrets_legend("dax") == usage.secrets_legend("dataverse") == "App registration"
    assert usage.secrets_legend("postgres") == usage.secrets_legend(None) == "Passwords"


def test_the_listings_carry_the_facts_and_the_pages_name_no_kind(client: TestClient) -> None:
    types = client.get("/connections/types", headers=AUTH).json()["types"]
    assert types and all(t["secrets_legend"] in ("Passwords", "App registration") for t in types)
    assert {t["secrets_legend"] for t in types if t["dialect"] in ("dax", "dataverse")} == {
        "App registration"
    }


# ===== a vault secret's variable: the server's one rule, asked =====


def test_a_typed_secrets_variable_is_asked_never_worked_out_by_the_page(client: TestClient) -> None:
    names = ["Sql--Password", "warehouse-password", "9lives"]
    answered = client.post("/connections/vaults/secrets", json={"named": names}, headers=AUTH)
    assert answered.status_code == 200, answered.text
    assert {n["secret"]: n["env"] for n in answered.json()["names"]} == {
        n: env_name_for_secret(n) for n in names
    }


# ===== an In's source picker on the Canvas =====

TYPES = ["Table", "str", "int", "float", "bool", "date", "datetime", "dict", "list", "list[str]", "list[int]"]
TYPES += ["list[float]", "list[dict]", "File", "list[Table]"]
EVERY = {
    f"w{at}.out": {"type": kind, "instance": f"w{at}", "widget": "made_up", "port": "out"}
    for at, kind in enumerate(TYPES)
}
SAMPLE: dict[str, Any] = {
    "table": "orders",
    "endpoint": "GET /orders",
    "variable": "REGION",
    "page": "last_visit",
}


@pytest.mark.parametrize("wanted", TYPES)
def test_what_the_picker_offers_is_what_the_check_accepts(wanted: str) -> None:
    port = Port("source", "in", wanted)
    offered = wiring.sources(port, "w0", EVERY)
    context = wiring.Context(
        {ref: out["type"] for ref, out in EVERY.items() if out["instance"] != "w0"},
        {"GET /orders"},
        {"REGION"},
        {"orders"},
    )
    target = "Table" if wanted.startswith("list[Table") else wanted
    # The Outs offered are exactly those whose type fits (never its own instance's), and each is accepted.
    fitting = [r for r, o in EVERY.items() if o["instance"] != "w0" and contract.fits(o["type"], target)]
    assert offered["outs"] == fitting
    for ref in EVERY:
        if EVERY[ref]["instance"] == "w0":
            continue
        wire: dict[str, Any] = {"tables": [{"out": ref}]} if offered["kinds"] == ["tables"] else {"out": ref}
        if ref in offered["outs"]:
            wiring.check_in(port, wire, context)
        else:
            with pytest.raises(ContractError):
                wiring.check_in(port, wire, context)
    # Each kind of source: offered means accepted, not offered means refused (a typed value apart: a
    # table's is accepted by the check but never typed into the picker).
    if offered["kinds"] == ["tables"]:
        wiring.check_in(port, {"tables": [{"table": "orders"}, {"page": "last_visit"}]}, context)
        return
    for kind, value in SAMPLE.items():
        if kind in offered["kinds"]:
            wiring.check_in(port, {kind: value}, context)
        elif kind != "page":
            with pytest.raises(ContractError):
                wiring.check_in(port, {kind: value}, context)
    assert ("value" in offered["kinds"]) is (wanted != "Table")
    with pytest.raises(ContractError):
        wiring.check_in(port, {"tables": [{"table": "orders"}]}, context)
