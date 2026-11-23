"""The Data Explorer (the owner, 2026-11-17: "a pane called Data Explorer that allows us to quickly search
by column names, table name, connection to quickly find data"): one search over the connections' loaded
catalogs, the open tables, the variables and the blades. Two made-up SQLite connections (one loaded, one
offered for loading... then both), two grids, a variable; part matches, groups and counts, the SQL names,
the provider seam (a stand-in for Structures), the code a result is inserted as, and the agent's
explorer_search. Made-up data only."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.cli.commands import REGISTRY
from swissarmybench.domain import explorer as rules
from swissarmybench.domain.explorer import Result
from swissarmybench.services.explorer import Explorer, Found, apis_provider
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring
from tests.test_connection_tables import ok, sqlite_connection


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


# ===== the rules =====


def test_words_match_in_any_case_and_by_parts() -> None:
    words = rules.words_of("cust")
    assert rules.score("customer_id", words) == 1
    assert rules.score("CustomerKey", words) == 1
    assert rules.score("id_customer", words) == 2  # a part starts with it
    assert rules.score("Accustomed", words) == 3  # inside it
    assert rules.score("orders", words) is None
    # The separators taken out: customerid finds customer_id and CustomerID.
    assert rules.score("customer_id", ["customerid"]) == 0
    assert rules.score("Customer_Key", ["customerkey"]) == 0
    assert rules.parts("HTTPStatus2") == ["http", "status", "2"]


def test_words_may_spread_over_the_path_but_one_is_in_the_name() -> None:
    assert rules.score("customer_id", ["orders", "cust"], ["Shop", "main", "orders"]) is not None
    assert rules.score("customer_id", ["refunds", "cust"], ["Shop", "main", "orders"]) is None
    assert rules.score("orders", ["shop"], ["Shop", "main"]) is None  # only the path: not this table


def test_the_search_as_sent() -> None:
    q = rules.parse(" Cust ID ", "tables,columns", "Shop", None, "500")
    assert q.words == ("cust", "id") and q.kinds == {"tables", "columns"} and q.limit == rules.MAX_LIMIT
    assert rules.parse("", None).kinds == set(rules.KINDS)
    with pytest.raises(rules.ExplorerError, match="not a kind"):
        rules.parse("x", ["rows"])
    with pytest.raises(rules.ExplorerError, match="at most"):
        rules.parse("x" * 201)


def test_results_are_grouped_counted_and_cut_to_the_limit() -> None:
    made = [Result("columns", f"customer_{i}", ["Shop", "t"]) for i in range(30)]
    made += [Result("tables", "customers", ["Shop"]), Result("connections", "Customer Hub")]
    q = rules.parse("cust", limit=5)
    answer = rules.grouped(rules.ranked(made, q), q)
    assert [g["kind"] for g in answer["groups"]] == ["connections", "tables", "columns"]
    assert [g["count"] for g in answer["groups"]] == [1, 1, 30]
    assert len(answer["groups"][2]["results"]) == 5 and answer["total"] == 32


def test_the_code_a_result_goes_into_a_cell_as() -> None:
    assert rules.table_insert("[Shop].orders") == {
        "sql": "SELECT * FROM [Shop].orders",
        "python": 'sab.sql("SELECT * FROM [Shop].orders")',
    }
    assert rules.grid_insert("orders") == {"sql": "SELECT * FROM orders", "python": "orders"}
    assert rules.column_insert("Order Date", "orders") == {
        "sql": '"Order Date"',
        "python": 'orders["Order Date"]',
    }
    assert rules.variable_insert("SALES_REGION") == {"python": 'os.environ["SALES_REGION"]'}
    assert rules.blade_insert("Rates", "rates", "other") == {"python": 'rates = sab.blade("Rates")'}
    assert rules.blade_insert("Team vault", "get", "vault") == {"python": 'sab.blade("Team vault")'}


def test_a_provider_registered_later_joins_the_search() -> None:
    """The seam: a Structures document's paths (trees-apis registers the real one)."""

    async def structures(query: rules.Query) -> Found:
        return Found(
            [
                Result(
                    "structures",
                    "id",
                    ["orders.json", "$.orders[].customer"],
                    more={"pointer": "/orders/0/customer/id"},
                )
            ]
        )

    async def broken(query: rules.Query) -> Found:
        raise RuntimeError("a source that fails leaves the others")

    explorer = Explorer(ws=None)  # type: ignore[arg-type]
    explorer.register("structures", structures)
    explorer.register("broken", broken)
    found = asyncio.run(explorer.search({"q": "customer id"}))
    assert [g["kind"] for g in found["groups"]] == ["structures"]
    assert found["groups"][0]["results"][0]["path"] == ["orders.json", "$.orders[].customer"]
    assert asyncio.run(explorer.search({"q": "id", "kinds": "tables"}))["groups"] == []


# ===== over HTTP: two SQLite connections, two grids, a variable =====


def _search(client: Any, headers: dict[str, str] = AUTH, **params: Any) -> Any:
    return ok(client.get("/explorer/search", params=params, headers=headers))


def _names(answer: Any, kind: str) -> list[str]:
    group: dict[str, Any] = next((g for g in answer["groups"] if g["kind"] == kind), {"results": []})
    return [r["name"] for r in group["results"]]


def test_one_search_over_connections_grids_and_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SHOP_REGION", raising=False)
    with make_client(tmp_path) as client:
        sqlite_connection(
            client,
            tmp_path,
            "Shop",
            {
                "orders": ("order_id INTEGER, customer_id INTEGER, amount REAL", [(1, 1, 9.5)]),
                "customers": ("CustomerKey INTEGER, name TEXT", [(1, "Ada")]),
            },
        )
        sqlite_connection(
            client, tmp_path, "Ledger", {"invoices": ("invoice_id INTEGER, customer_id INTEGER", [(7, 1)])}
        )
        ok(client.post("/datasets/sales/paste", content=b"region\tcustomer_id\nNorth\t1\n", headers=AUTH))
        ok(client.post("/datasets/regions/paste", content=b"Region\tTarget\nNorth\t5\n", headers=AUTH))
        ok(client.put("/variables", json={"name": "SHOP_REGION", "value": "North"}, headers=AUTH))

        # Ledger's catalog not loaded yet: it is offered, Shop's is searched once loaded.
        ok(client.get("/connections/Shop/tree", headers=AUTH))
        first = _search(client, q="cust")
        assert [o["connection"] for o in first["offers"]] == ["Ledger"]
        assert _names(first, "tables") == ["customers"]
        customers = next(g for g in first["groups"] if g["kind"] == "tables")["results"][0]
        assert customers["sql"] == "[Shop].customers" and customers["path"] == ["Shop", "main"]
        assert customers["insert"] == {
            "sql": "SELECT * FROM [Shop].customers",
            "python": 'sab.sql("SELECT * FROM [Shop].customers")',
        }
        columns = next(g for g in first["groups"] if g["kind"] == "columns")
        assert sorted(columns["results"][i]["name"] for i in range(columns["count"])) == [
            "CustomerKey",
            "customer_id",
            "customer_id",
        ]
        typed = {(r["path"][-1], r["name"]): r.get("type") for r in columns["results"]}
        assert typed[("orders", "customer_id")] == "INTEGER"
        assert typed[("sales", "customer_id")] in ("BIGINT", "INTEGER", "VARCHAR")

        ok(client.get("/connections/Ledger/tree", headers=AUTH))
        both = _search(client, q="customer_id", kinds="columns")
        assert both["offers"] == [] and [g["kind"] for g in both["groups"]] == ["columns"]
        assert sorted(r["connection"] or "" for r in both["groups"][0]["results"]) == ["", "Ledger", "Shop"]

        # Show tables with this column: every table that has it, in any case, across connections.
        same = _search(client, column="CUSTOMER_ID")
        assert sorted(r["path"][-1] for r in same["groups"][0]["results"]) == ["invoices", "orders", "sales"]

        # The connection picker, the open tables, the variable (its source, never its value).
        shop = _search(client, q="o", connection="shop", kinds="tables")
        assert _names(shop, "tables") == ["orders", "customers"]
        regions = _search(client, q="region")
        assert _names(regions, "tables") == ["regions"]
        grid = next(g for g in regions["groups"] if g["kind"] == "tables")["results"][0]
        assert grid["source"] == "grid" and grid["grid"] and grid["insert"]["python"] == "regions"
        variable = next(g for g in regions["groups"] if g["kind"] == "variables")["results"][0]
        assert variable["name"] == "SHOP_REGION" and "North" not in str(variable)
        assert _names(_search(client, q="sho", kinds="connections"), "connections") == ["Shop"]

        # An empty search lists what is there (no catalogs' columns).
        listed = _search(client)
        assert {g["kind"] for g in listed["groups"]} >= {"connections", "tables", "variables"}
        assert "columns" not in {g["kind"] for g in listed["groups"]}

        # The agent's explorer_search: the same answer, names and types only.
        agent = _search(client, AGENT, q="cust")
        assert agent["total"] == _search(client, q="cust")["total"]
        assert "explorer_search" in REGISTRY
        bad = client.get("/explorer/search", params={"kinds": "rows"}, headers=AGENT)
        assert bad.status_code == 400 and "not a kind" in bad.text


def test_the_popped_out_windows_old_address_is_the_data_page(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        page = client.get("/workbench?panel=explorer", follow_redirects=False)
        assert page.status_code == 302 and page.headers["location"] == "/workspace?open=data"
        assert client.get("/workbench", follow_redirects=True).url.path == "/blazor/notebooks"


# ===== the Data page's browse (the owner, 2026-11-17: "a standalone DATA rail icon and page") =====


def test_the_browse_rules() -> None:
    q = rules.browse_query()
    assert q.browse and q.empty and q.kinds == set(rules.KINDS)
    assert rules.shows("connections", rules.browse_query("columns"))
    assert not rules.shows("blades", rules.browse_query("tables"))
    assert rules.imports_relationships("powerbi", "powerbi")
    assert rules.imports_relationships("database", "sqlserver")
    assert not rules.imports_relationships("database", "sqlite")
    assert rules.blade_is_table({"blade_kind": "other"})
    assert rules.blade_is_table({"kind": "sql", "table": "orders"})  # a blade that names its table
    assert not rules.blade_is_table({"blade_kind": "other", "web_call": True})
    assert not rules.blade_is_table({"blade_kind": "vault"})
    tree = {
        "state": {"state": "loaded"},
        "group": "dataset",
        "groups": [
            {
                "database": "",
                "schema": "Sales model",
                "tables": [{"database": "", "schema": "Sales model", "table": "Orders", "sql": "[F].Orders"}],
            }
        ],
    }
    node = rules.connection_node({"name": "F", "tables_kind": "powerbi", "type": "Power BI"}, tree)
    assert node["relationships"] and node["loaded"] and node["count"] == 1 and node["group"] == "dataset"
    table = node["groups"][0]["tables"][0]
    assert table["sql"] == "[F].Orders" and table["path"] == ["F", "Sales model"]
    assert table["insert"]["sql"] == "SELECT * FROM [F].Orders" and table["source"] == "catalog"
    failed = rules.connection_node({"name": "G", "tables_kind": "database"}, None, "no driver")
    assert failed["state"] == {"state": "failed", "error": "no driver"} and not failed["loaded"]
    code = rules.table_code("[F].Orders")
    assert code["sql"] == "%%sql\nSELECT *\nFROM [F].Orders\nLIMIT 100"
    assert code["python"] == 'df = sab.sql("SELECT * FROM [F].Orders LIMIT 100")'


def test_the_browse_over_http_and_the_agents_commands(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        sqlite_connection(
            client,
            tmp_path,
            "Shop",
            {
                "orders": ("order_id INTEGER, customer_id INTEGER, amount REAL", [(1, 1, 9.5)]),
                "customers": ("CustomerKey INTEGER, name TEXT", [(1, "Ada")]),
            },
        )
        sqlite_connection(client, tmp_path, "Ledger", {"invoices": ("invoice_id INTEGER", [(7,)])})
        ok(client.post("/datasets/sales/paste", content=b"region\tcustomer_id\nNorth\t1\n", headers=AUTH))
        ok(
            client.post(
                "/structures/paste", json={"text": '{"crates": [{"id": 1}]}', "name": "plums"}, headers=AUTH
            )
        )
        ok(client.get("/connections/Shop/tree", headers=AUTH))

        tree = ok(client.get("/explorer/browse", headers=AUTH))
        by = {c["name"]: c for c in tree["connections"]}
        assert set(by) == {"Shop", "Ledger"}
        # Shop's tables in its schema; Ledger's catalog not loaded: a look never loads it (Load does).
        assert by["Shop"]["state"]["state"] == "loaded" and by["Shop"]["count"] == 2
        assert [g["schema"] for g in by["Shop"]["groups"]] == ["main"]
        assert sorted(t["name"] for t in by["Shop"]["groups"][0]["tables"]) == ["customers", "orders"]
        assert not by["Ledger"]["loaded"] and by["Ledger"]["groups"] == []
        assert not by["Shop"]["relationships"]
        sections = {s["kind"]: s for s in tree["sections"]}
        assert [s["kind"] for s in tree["sections"]] == ["open", "structures"]
        sales = sections["open"]["items"][0]
        assert sales["name"] == "sales" and [c["name"] for c in sales["children"]] == [
            "region",
            "customer_id",
        ]
        plums = sections["structures"]["items"][0]
        assert plums["name"] == "plums" and [c["pointer"] for c in plums["children"]] == [
            "$.crates",
            "$.crates[].id",
        ]
        assert "North" not in str(tree)  # names only, never a value

        # The filters: a kind, a connection.
        only = ok(client.get("/explorer/browse", params={"kinds": "structures"}, headers=AUTH))
        assert only["connections"] == [] and [s["kind"] for s in only["sections"]] == ["structures"]
        shop = ok(client.get("/explorer/browse", params={"connection": "shop"}, headers=AUTH))
        assert [c["name"] for c in shop["connections"]] == ["Shop"] and shop["sections"] == []

        # Load (the catalog loads in the background), then Ledger has its table.
        ok(client.post("/connections/Ledger/catalog", headers=AUTH))
        ok(client.get("/connections/Ledger/tree", headers=AUTH))
        ledger = ok(client.get("/explorer/browse", params={"connection": "Ledger"}, headers=AUTH))
        assert ledger["connections"][0]["groups"][0]["tables"][0]["name"] == "invoices"

        # The detail side: a table's columns, its SQL name and its code.
        detail = ok(
            client.get(
                "/explorer/table",
                params={"connection": "shop", "schema": "main", "table": "orders"},
                headers=AUTH,
            )
        )
        assert detail["sql"] == "[Shop].orders" and detail["where"] == ["Shop", "main"]
        assert [(c["name"], c["type"]) for c in detail["columns"]] == [
            ("order_id", "INTEGER"),
            ("customer_id", "INTEGER"),
            ("amount", "REAL"),
        ]
        assert detail["code"]["sql"].startswith("%%sql\nSELECT *\nFROM [Shop].orders")
        assert not detail["relationships"]
        missing = client.get("/explorer/table", params={"connection": "Shop"}, headers=AUTH)
        assert missing.status_code == 400

        # The agent: the same answers, by its commands.
        assert {"explorer_browse", "explorer_table"} <= set(REGISTRY)
        agent = ok(client.get("/explorer/browse", headers=AGENT))
        assert [c["name"] for c in agent["connections"]] == [c["name"] for c in tree["connections"]]
        assert (
            ok(client.get("/explorer/table", params=detail["place"] | {"connection": "Shop"}, headers=AGENT))[
                "sql"
            ]
            == "[Shop].orders"
        )


# ===== Structures and APIs (the trees-apis branch's, registered in bootstrap) =====


def test_a_structures_keys_by_their_paths() -> None:
    value = {"orders": [{"customer": {"id": 1, "Full Name": "Ada"}}, {"customer": {"id": 2}, "extra": True}]}
    found = {p.pointer: p for p in rules.structure_paths(value)}
    assert list(found) == [
        "$.orders",
        "$.orders[].customer",
        "$.orders[].customer.id",
        '$.orders[].customer["Full Name"]',
        "$.orders[].extra",
    ]
    assert found["$.orders[].customer.id"].parts == ("orders", 0, "customer", "id")
    assert found["$.orders[].extra"].parts == ("orders", 1, "extra")
    assert found["$.orders[].extra"].type == "boolean"
    assert rules.parent_pointer("$.orders[].customer.id") == "$.orders[].customer"
    assert rules.parent_pointer("$.orders") == "$"
    assert len(rules.structure_paths({f"k{i}": i for i in range(50)}, limit=10)) == 10


def test_an_apis_table_returning_calls_and_their_columns() -> None:
    listed = {
        "api": "Orders API",
        "operation": "listOrders",
        "method": "GET",
        "path": "/orders",
        "as_table": True,
        "columns": {"customer_id": "BIGINT", "total": "DOUBLE"},
    }
    calls = [
        {"name": "Orders API listOrders", "web_call": listed},
        {"name": "Orders API getOrder", "web_call": {"api": "Orders API", "operation": "getOrder"}},
        {
            "name": "Orders API pushOrders",
            "web_call": {
                "api": "Orders API",
                "operation": "pushOrders",
                "as_table": True,
                "mode": "write rows",
            },
        },
    ]
    explorer = Explorer(ws=None)  # type: ignore[arg-type]
    explorer.register("apis", apis_provider(lambda: calls))
    found = asyncio.run(explorer.search({"q": "order"}))
    call = next(g for g in found["groups"] if g["kind"] == "apis")["results"]
    assert [r["name"] for r in call] == ["listOrders"]
    assert call[0]["sql"] == "[Orders API].listOrders" and call[0]["detail"] == "GET /orders"
    assert call[0]["insert"]["sql"] == "SELECT * FROM [Orders API].listOrders"
    columns = asyncio.run(explorer.search({"q": "cust", "kinds": "columns"}))["groups"][0]["results"]
    assert [(c["name"], c["type"], c["path"]) for c in columns] == [
        ("customer_id", "BIGINT", ["Orders API", "listOrders"])
    ]


def test_an_open_structures_paths_over_http(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        text = '{"orders": [{"customer": {"id": 1}}]}'
        opened = ok(client.post("/structures/paste", json={"text": text, "name": "shop"}, headers=AUTH))
        found = _search(client, q="customer id", kinds="structures")
        results = found["groups"][0]["results"]
        assert [(r["name"], r["pointer"], r["parts"]) for r in results] == [
            ("id", "$.orders[].customer.id", ["orders", 0, "customer", "id"])
        ]
        assert results[0]["structure"] == opened["id"] and results[0]["path"][1] == "$.orders[].customer"
        names = _search(client, kinds="structures")["groups"][0]["results"]
        assert [r["name"] for r in names] == [opened["name"]]
