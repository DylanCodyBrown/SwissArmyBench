"""The sandbox's gaps the owner approved (2026-11-21): sortable sandbox tables, the Sandbox a real connection
kind (its card, the tables contract, [Sandbox] in DuckDB SQL, its own colour, never exported as a connection),
sandbox variants (a designation, the origin kept, several of one origin named apart, never written back),
Mocked as a connection, a sandbox grid edited (typed; counted in the change log; Reset undoes it),
and Try it's body kept as an endpoint's example. Rules first, then the routes. Made-up data only."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import local_api as api_rules
from swissarmybench.domain import sandbox as rules
from swissarmybench.domain.sandbox import SandboxError
from tests.conftest import AGENT, AUTH, make_client
from tests.test_local_api import API_PY

ORDERS = "order_id,region,amount\n1,West,10.5\n2,East,7.25\n3,West,3.0\n4,North,12.0\n"


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def _project(client: TestClient, tmp_path: Path) -> Path:
    target = tmp_path / "shop"
    ok(client.post("/project/new", json={"path": str(target)}, headers=AUTH))
    return target


def _orders_grid(client: TestClient, tmp_path: Path) -> str:
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    return str(ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))["grid"])


def _rows(client: TestClient, grid: str) -> list[list[Any]]:
    return list(ok(client.get(f"/grids/{grid}/rows?start=0&end=50", headers=AUTH))["rows"])


# ===== the rules =====


def test_sorting_by_each_key_and_ties_by_name() -> None:
    tables = [
        {"name": "b", "rows": 2, "source_words": "From x", "added_at": "2026-01-02", "changed_at": None},
        {
            "name": "A",
            "rows": 9,
            "source_words": "Made empty",
            "added_at": "2026-01-01",
            "changed_at": "2026-03",
        },
        {"name": "c", "rows": 2, "source_words": "From a", "added_at": "2026-01-03", "changed_at": "2026-02"},
    ]

    def names(by: str, desc: bool = False) -> list[str]:
        return [str(t["name"]) for t in rules.sort_tables(tables, by, desc)]

    assert names("name") == ["A", "b", "c"]
    assert names("rows") == ["b", "c", "A"] and names("rows", True) == ["A", "b", "c"]
    assert names("source") == ["c", "b", "A"]
    assert names("created") == ["A", "b", "c"]
    assert names("changed") == ["b", "c", "A"]  # never changed: when it came in
    assert rules.check_sort(None) == ("name", False)
    assert rules.check_sort("changed", "desc") == ("changed", True)
    with pytest.raises(SandboxError, match="Sort by one of"):
        rules.check_sort("colour")
    with pytest.raises(SandboxError, match="asc or desc"):
        rules.check_sort("rows", "up")


def test_variants_are_named_apart_with_their_designation() -> None:
    assert rules.variant_name("orders", []) == ("orders_sandbox", "orders · sandbox")
    assert rules.variant_name("orders", ["orders_sandbox"]) == ("orders_sandbox_2", "orders · sandbox 2")
    assert rules.variant_name("orders", ["ORDERS_SANDBOX", "orders_sandbox_2"])[0] == "orders_sandbox_3"
    assert rules.variant_name("orders", [], "West orders test") == ("West_orders_test", "West orders test")
    assert rules.variant_name("2026 sales", [])[0] == "t_2026_sales_sandbox"
    record = rules.variant_record(
        {"kind": "grid", "table": "orders", "connection": "Warehouse"},
        "orders · sandbox",
        "2026-11-21T14:02:00",
    )
    assert rules.origin_words(record) == "A sandbox variant of orders (Warehouse), copied 2026-11-21 14:02"
    structure = rules.variant_record({"kind": "structure", "structure": "shop", "path": "$.orders"}, "x", "")
    assert rules.origin_words(structure) == "A sandbox variant of the structure shop at $.orders"


def test_an_edit_names_its_row_by_every_value_and_casts_to_its_type() -> None:
    s = rules.edit_update("orders", ["order_id", "region"], [1, "West"], "region", "East", "VARCHAR")
    assert s.sql == (
        'UPDATE "orders" SET "region" = CAST(? AS VARCHAR) WHERE rowid = (SELECT rowid FROM "orders" WHERE '
        '"order_id" IS NOT DISTINCT FROM ? AND "region" IS NOT DISTINCT FROM ? LIMIT 1)'
    )
    assert s.params == ["East", 1, "West"]
    assert rules.edit_delete("orders", ["a"], [None]).params == [None]
    assert rules.edit_insert("orders", {"a": (1, "BIGINT")}).sql == (
        'INSERT INTO "orders" ("a") VALUES (CAST(? AS BIGINT))'
    )
    assert rules.cell_value("", "DOUBLE") is None and rules.cell_value("", "VARCHAR") == ""
    assert rules.cell_value("yes", "BOOLEAN") is True
    assert rules.editable_type("amount", "decimal(18,2)") == "DECIMAL(18,2)"
    # A LIST, STRUCT or MAP: a JSON value, cast from JSON to its own type (the owner approved, 2026-11-21).
    assert (
        rules.editable_type("pt", 'STRUCT(x INTEGER, "label" VARCHAR)')
        == 'STRUCT(x INTEGER, "label" VARCHAR)'
    )
    assert rules.edit_insert("t", {"tags": ('["a"]', "VARCHAR[]")}).sql == (
        'INSERT INTO "t" ("tags") VALUES (CAST(?::JSON AS VARCHAR[]))'
    )
    assert rules.cell_value(["a", "b"], "VARCHAR[]") == '["a", "b"]'
    assert rules.cell_value('{"k": 1}', "MAP(VARCHAR, INTEGER)") == '{"k": 1}'
    assert rules.cell_value(" ", "INTEGER[]") is None
    with pytest.raises(SandboxError, match="is not JSON: this column takes a list, written in JSON as"):
        rules.cell_value("a, b", "VARCHAR[]")
    with pytest.raises(SandboxError, match="through the API"):
        rules.editable_type("tags", "STRUCT(a INTEGER); DROP TABLE t")
    assert rules.not_a("amount", "abc", "DOUBLE") == "'abc' is not a number: amount is DOUBLE."


def test_a_kept_example_is_byte_stable_and_beside_api_py() -> None:
    api = api_rules.parse(API_PY)
    body = {"order_id": 9, "region": "West", "amount": 1.5}
    assert api_rules.check_example(api, "POST /orders", body) == body
    with pytest.raises(api_rules.ApiFileError, match="takes no body"):
        api_rules.check_example(api, "GET /orders/{region}", body)
    with pytest.raises(api_rules.ApiFileError, match="no endpoint"):
        api_rules.check_example(api, "POST /gone", body)
    text = api_rules.examples_text({"POST /orders": body})
    assert api_rules.examples_text(api_rules.read_examples(text)) == text
    document = api_rules.with_examples(api_rules.openapi(api), {"POST /orders": body})
    assert (
        document["paths"]["/orders"]["post"]["requestBody"]["content"]["application/json"]["example"] == body
    )
    assert api_rules.EXAMPLES_FILE == ".sab/api_examples.json"


# ===== the routes =====


def test_variants_sorting_and_the_change_log_from_a_grid_edit(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        _project(client, tmp_path)
        origin_grid = _orders_grid(client, tmp_path)
        # Make a sandbox variant: its designation, its origin; a second one named apart.
        first = ok(client.post("/sandbox/tables/variant", json={"table": "orders"}, headers=AUTH))
        assert first["added"] == "orders_sandbox" and first["title"] == "orders · sandbox"
        second = ok(client.post("/sandbox/tables/variant", json={"table": "orders"}, headers=AGENT))
        assert second["added"] == "orders_sandbox_2" and second["title"] == "orders · sandbox 2"
        own = ok(
            client.post(
                "/sandbox/tables/variant", json={"table": "orders", "name": "West test"}, headers=AUTH
            )
        )
        assert own["added"] == "West_test"
        listed = ok(client.get("/sandbox", headers=AUTH))
        by = {t["name"]: t for t in listed["tables"]}
        assert listed["type"] == "sandbox" and by["orders_sandbox"]["type"] == "sandbox"
        assert by["orders_sandbox"]["variant"]["origin"] == {"kind": "grid", "table": "orders"}
        assert by["orders_sandbox"]["origin_words"].startswith("A sandbox variant of orders, copied ")
        assert by["West_test"]["title"] == "West test"
        missing = client.post("/sandbox/tables/variant", json={"table": "gone"}, headers=AUTH)
        assert missing.status_code == 404
        # Edit a variant in its grid: the row it shows, typed, counted.
        grid = ok(client.post("/sandbox/tables/open", json={"table": "orders_sandbox"}, headers=AUTH))["grid"]
        # Sorted in its grid (a step on its view): row 0 is the largest amount (order 4).
        client.post(f"/grids/{grid}/header-sort", json={"keys": [["amount", "desc"]]}, headers=AUTH)
        assert _rows(client, grid)[0][0] == 4
        edit = {"table": "orders_sandbox", "op": "update", "row": 0, "column": "amount", "value": "99.5"}
        done = ok(client.post("/sandbox/edit", json=edit, headers=AUTH))
        assert done["rows"] == 1 and done["log"]["orders_sandbox"]["updated"] == 1
        assert _rows(client, grid)[0][:3] == [4, "North", 99.5]  # its grid followed, its sort kept
        bad = client.post("/sandbox/edit", json=edit | {"value": "abc"}, headers=AUTH)
        assert bad.status_code == 400 and "'abc' is not a number: amount is DOUBLE." in bad.text
        added = {"table": "orders_sandbox", "op": "insert", "values": {"order_id": "5", "region": "South"}}
        assert ok(client.post("/sandbox/edit", json=added, headers=AUTH))["rows"] == 1
        gone = ok(
            client.post(
                "/sandbox/edit",
                json={"table": "orders_sandbox", "op": "delete", "rows": [1, 2]},
                headers=AUTH,
            )
        )
        assert gone["rows"] == 2
        log = ok(client.get("/sandbox", headers=AUTH))["log"]["orders_sandbox"]
        assert log == {"inserted": 1, "updated": 1, "deleted": 2}
        # The origin is never written: the open table is as it came in.
        assert [r[2] for r in _rows(client, origin_grid)] == [
            10.5,
            7.25,
            3.0,
            12.0,
        ]
        # Sorted lists: by rows, then by last changed (the edited one last changed).
        by_rows = ok(client.get("/sandbox?sort=rows&order=desc", headers=AUTH))
        assert by_rows["sort"]["by"] == "rows" and by_rows["tables"][-1]["name"] == "orders_sandbox"
        changed = ok(client.get("/sandbox?sort=changed&order=desc", headers=AUTH))["tables"]
        assert changed[0]["name"] == "orders_sandbox" and changed[0]["changed_at"]
        assert client.get("/sandbox?sort=colour", headers=AUTH).status_code == 400
        # Reset undoes the grid's edits.
        ok(client.post("/sandbox/reset", json={"table": "orders_sandbox"}, headers=AUTH))
        assert sorted(r[2] for r in _rows(client, grid)) == [3.0, 7.25, 10.5, 12.0]
        # Its read-only cell loads it as DuckDB SQL names it; its origin's words carry its designation.
        cells = {t["name"]: t for t in ok(client.get("/workbench/tables", headers=AUTH))["tables"]}
        text = json.dumps(cells["sandbox_orders_sandbox"])
        assert "sab.sql(" in text and "SELECT * FROM [Sandbox].orders_sandbox" in text


def test_list_struct_and_map_cells_are_edited_as_json_and_checked_against_their_type(tmp_path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table(
        {
            "id": [1, 2],
            "tags": [["red"], []],
            "pt": [{"x": 1, "label": "a"}, {"x": 2, "label": "b"}],
            "m": pa.array([[("k", 1)], []], type=pa.map_(pa.string(), pa.int32())),
        }
    )
    pq.write_table(table, tmp_path / "shapes.parquet")
    with make_client(tmp_path) as client:
        _project(client, tmp_path)
        ok(
            client.post(
                "/sandbox/tables",
                json={"from": "file", "path": str(tmp_path / "shapes.parquet")},
                headers=AUTH,
            )
        )
        values = {"tags": ["blue", "green"], "pt": '{"x": 7, "label": "z"}', "m": {"q": 3}}
        ok(
            client.post(
                "/sandbox/edit",
                json={"table": "shapes", "op": "update", "where": {"id": 2}, "values": values},
                headers=AUTH,
            )
        )
        ok(
            client.post(
                "/sandbox/edit",
                json={"table": "shapes", "op": "insert", "values": {"id": 3, "tags": '["x"]'}},
                headers=AGENT,
            )
        )
        got = ok(
            client.post(
                "/sandbox/data",
                json={"op": "sql", "connection": "Sandbox", "sql": "SELECT * FROM shapes ORDER BY id"},
                headers=AUTH,
            )
        )
        assert got["rows"][1] == [2, ["blue", "green"], {"x": 7, "label": "z"}, {"q": 3}]
        assert got["rows"][2][:2] == [3, ["x"]]
        wrong = client.post(
            "/sandbox/edit",
            json={"table": "shapes", "op": "update", "where": {"id": 1}, "values": {"pt": {"y": 1}}},
            headers=AUTH,
        )
        assert wrong.status_code == 400 and "pt is STRUCT(" in wrong.json()["error"], wrong.text
        assert 'unknown key "y"' in wrong.json()["error"]
        not_json = client.post(
            "/sandbox/edit",
            json={"table": "shapes", "op": "update", "where": {"id": 1}, "values": {"tags": "red, blue"}},
            headers=AUTH,
        )
        assert not_json.status_code == 400 and "is not JSON" in not_json.json()["error"]
        assert ok(client.get("/sandbox", headers=AUTH))["log"]["shapes"] == {
            "inserted": 1,
            "updated": 1,
            "deleted": 0,
        }


def test_an_edit_on_a_row_that_changed_says_so(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        _project(client, tmp_path)
        cols = [{"name": "id", "type": "integer", "key": True}, {"name": "note", "type": "text"}]
        ok(
            client.post(
                "/sandbox/tables", json={"from": "columns", "name": "notes", "columns": cols}, headers=AUTH
            )
        )
        refused = client.post(
            "/sandbox/edit",
            json={"table": "notes", "op": "update", "row": 0, "column": "note", "value": "x"},
            headers=AUTH,
        )
        assert refused.status_code == 404 and "Open notes in Grids first" in refused.text
        ok(
            client.post(
                "/sandbox/edit", json={"table": "notes", "op": "insert", "values": {"id": 1}}, headers=AUTH
            )
        )
        dup = client.post(
            "/sandbox/edit", json={"table": "notes", "op": "insert", "values": {"id": 1}}, headers=AUTH
        )
        assert dup.status_code == 400  # the key is taken: nothing written
        ok(client.post("/sandbox/tables/open", json={"table": "notes"}, headers=AUTH))
        # Changed by an API since it was shown: the grid shows it again, nothing written.
        ok(
            client.post(
                "/sandbox/data",
                json={"op": "update", "table": "notes", "values": {"id": 2}, "where": {"id": 1}},
                headers=AUTH,
            )
        )
        # (the grid followed at once, so the edit below names the row as it is now)
        ok(
            client.post(
                "/sandbox/edit",
                json={"table": "notes", "op": "update", "row": 0, "column": "note", "value": "hi"},
                headers=AUTH,
            )
        )
        where = {"table": "notes", "op": "update", "where": {"id": 2}, "values": {"note": "by key"}}
        assert ok(client.post("/sandbox/edit", json=where, headers=AGENT))["rows"] == 1
        read = ok(client.post("/sandbox/data", json={"op": "table", "table": "notes"}, headers=AUTH))
        assert read["rows"] == [{"id": 2, "note": "by key"}]
        past = client.post(
            "/sandbox/edit", json={"table": "notes", "op": "delete", "rows": [7]}, headers=AUTH
        )
        assert past.status_code == 404 and "has no row 8" in past.text


def _shop(client: TestClient, tmp_path: Path) -> None:
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as made_up:
        made_up.execute("CREATE TABLE customers (customer_id INTEGER, city TEXT)")
        made_up.executemany("INSERT INTO customers VALUES (?, ?)", [(1, "Springfield"), (2, "Shelbyville")])
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{database}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    shop = {"name": "Shop", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code}
    ok(client.post("/connections", json=shop, headers=AUTH))


def test_mocked_as_a_connection(tmp_path: Path) -> None:
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    with make_client(tmp_path) as client:
        _project(client, tmp_path)
        _shop(client, tmp_path)
        ok(client.post("/sandbox/tables", json={"from": "file", "path": str(csv)}, headers=AUTH))
        ok(
            client.post(
                "/sandbox/tables",
                json={"from": "connection", "connection": "Shop", "table": "customers"},
                headers=AUTH,
            )
        )
        listed = ok(client.get("/sandbox", headers=AUTH))
        assert "Shop" in listed["mock_choices"]
        by = {t["name"]: t for t in listed["tables"]}
        assert by["orders"]["mockable"] and not by["customers"]["mockable"]
        mocked = ok(
            client.post("/sandbox/tables/mock", json={"table": "orders", "connection": "Shop"}, headers=AGENT)
        )
        assert mocked["client"]["connection"] == "Shop" and mocked["client"]["dialect"] == "sqlite"
        # Its mock client is Shop's now: its kind and dialect, its tables.
        client_of = ok(
            client.post("/sandbox/data", json={"op": "client", "connection": "Shop"}, headers=AUTH)
        )
        assert set(client_of["tables"]) == {"orders", "customers"} and client_of["dialect"] == "sqlite"
        assert ok(client.get("/sandbox", headers=AUTH))["tables"][1]["mocked"] in (True, False)
        refused = client.post(
            "/sandbox/tables/mock", json={"table": "customers", "connection": "Shop"}, headers=AUTH
        )
        assert refused.status_code == 409 and "was read from Shop" in refused.text
        unknown = client.post(
            "/sandbox/tables/mock", json={"table": "orders", "connection": "Nope"}, headers=AUTH
        )
        assert unknown.status_code == 404
        assert (
            client.post(
                "/sandbox/tables/mock", json={"table": "orders", "connection": "Sandbox"}, headers=AUTH
            ).status_code
            == 400
        )
        back = ok(
            client.post("/sandbox/tables/mock", json={"table": "orders", "connection": None}, headers=AUTH)
        )
        assert back["client"] == {"kind": "duckdb"} and not back["mocked"]


def test_the_sandbox_is_a_connection_kind_with_its_card_colour_and_tables(tmp_path: Path) -> None:
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    with make_client(tmp_path) as client:
        no_project = ok(client.get("/connections/usage", headers=AUTH))["connections"]
        assert not [c for c in no_project if c["name"] == "Sandbox"]
        _project(client, tmp_path)
        ok(client.post("/sandbox/tables", json={"from": "file", "path": str(csv)}, headers=AUTH))
        cards = ok(client.get("/connections/usage", headers=AGENT))["connections"]
        [card] = [c for c in cards if c["name"] == "Sandbox"]
        assert card["connection"] == "sandbox" and card["tables"] == 1
        assert card["words"].startswith("Local test data, never live")
        # The tables contract: listed and read like any connection's; named in DuckDB SQL.
        tree = ok(client.get("/connections/Sandbox/tree", headers=AGENT))
        assert tree["kind"] == "sandbox" and [t["table"] for t in tree["groups"][0]["tables"]] == ["orders"]
        assert tree["groups"][0]["tables"][0]["sql"] == "[Sandbox].orders"
        made = ok(
            client.post(
                "/datasets/n/query", json={"sql": "SELECT count(*) AS n FROM [Sandbox].orders"}, headers=AUTH
            )
        )
        assert _rows(client, made["grid"]) == [[4]]
        # Its own colour, never one of the palette's, never chosen.
        colours = {c["name"]: c for c in ok(client.get("/connection-colours", headers=AUTH))["connections"]}
        assert colours["Sandbox"]["colour"] == rules.COLOUR and colours["Sandbox"]["fixed"]
        palette = {p["colour"] for p in ok(client.get("/connection-colours", headers=AUTH))["palette"]}
        assert rules.COLOUR not in palette
        set_it = client.put("/connection-colours/Sandbox", json={"colour": "#0e7c7b"}, headers=AUTH)
        assert set_it.status_code == 400 and "its own" in set_it.text


def test_the_sandbox_is_never_exported_as_a_connection(tmp_path: Path) -> None:
    from swissarmybench.services.script_export import ScriptExports

    exports = ScriptExports.__new__(ScriptExports)
    assert exports.connections_code(["Sandbox"]) == {
        "text": "",
        "requirements": [],
        "variables": [],
        "notes": [],
    }


def test_a_structure_becomes_a_sandbox_variant(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        _project(client, tmp_path)
        text = json.dumps({"orders": [{"id": 1, "region": "West"}, {"id": 2, "region": "East"}]})
        opened = ok(client.post("/structures/paste", json={"text": text, "name": "shop"}, headers=AUTH))
        sid = opened.get("id") or opened["structure"]["id"]
        made = ok(
            client.post(
                "/sandbox/tables/variant",
                json={"from": "structure", "structure": sid, "path": "$.orders"},
                headers=AUTH,
            )
        )
        assert made["added"] == "shop_sandbox" and made["rows"] == 2
        [t] = ok(client.get("/sandbox", headers=AUTH))["tables"]
        assert t["origin_words"].startswith("A sandbox variant of the structure shop at $.orders")
        assert t["source_words"] == "From the structure shop"
        browse = ok(client.get("/explorer/browse", headers=AUTH))
        [item] = next(s for s in browse["sections"] if s["kind"] == "sandbox")["items"]
        assert item["variant"] and item["icon"] == "branch" and item["title"] == "shop · sandbox"


def test_the_agents_catalog_commands_sort_the_sandbox_as_the_catalog_does(tmp_path: Path) -> None:
    """explorer_browse and explorer_search take the Catalog's Sort for the Sandbox section (the sandbox list's
    own: name, rows, source, created, changed); a wrong one is said in the list's words."""
    from swissarmybench.cli import commands

    with make_client(tmp_path) as client:
        _project(client, tmp_path)
        for name, rows in (("alpha", 2), ("beta", 5), ("gamma", 1)):
            cols = [{"name": "id", "type": "integer"}]
            ok(
                client.post(
                    "/sandbox/tables", json={"from": "columns", "name": name, "columns": cols}, headers=AUTH
                )
            )
            for at in range(rows):
                ok(
                    client.post(
                        "/sandbox/data", json={"op": "insert", "table": name, "row": {"id": at}}, headers=AUTH
                    )
                )

        def names(answer: dict[str, Any]) -> list[str]:
            return [i["name"] for i in next(s for s in answer["sections"] if s["kind"] == "sandbox")["items"]]

        assert names(ok(client.get("/explorer/browse", headers=AGENT))) == ["alpha", "beta", "gamma"]
        by_rows = ok(client.get("/explorer/browse?sort=rows&order=desc", headers=AGENT))
        assert names(by_rows) == ["beta", "alpha", "gamma"]
        found = ok(client.get("/explorer/search?q=a&kinds=tables&sort=rows&order=asc", headers=AGENT))
        tables = [r["name"] for g in found["groups"] if g["kind"] == "tables" for r in g["results"]]
        assert [t for t in tables if t in ("alpha", "beta", "gamma")] == ["gamma", "alpha", "beta"]
        wrong = client.get("/explorer/browse?sort=size", headers=AGENT)
        assert (
            wrong.status_code == 400 and "Sort by one of: name, rows, source, created, changed" in wrong.text
        )
        assert {"sort", "order"} <= {x.name for x in commands.REGISTRY["explorer_browse"].args}


def test_try_its_body_kept_as_the_endpoints_example(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        folder = _project(client, tmp_path)
        (folder / "API.py").write_text(API_PY, encoding="utf-8")
        body = {"order_id": 9, "region": "West", "amount": 1.5}
        kept = ok(
            client.post("/local-api/example", json={"endpoint": "POST /orders", "body": body}, headers=AGENT)
        )
        assert kept["file"] == ".sab/api_examples.json"
        assert json.loads((folder / ".sab" / "api_examples.json").read_text(encoding="utf-8"))[
            "examples"
        ] == {"POST /orders": body}
        assert API_PY == (folder / "API.py").read_text(encoding="utf-8")  # API.py itself never written
        state = ok(client.get("/local-api", headers=AUTH))
        [post] = [e for e in state["endpoints"] if e["method"] == "POST"]
        assert post["example"] == body
        assert (
            state["openapi"]["paths"]["/orders"]["post"]["requestBody"]["content"]["application/json"][
                "example"
            ]
            == body
        )
        refused = client.post(
            "/local-api/example", json={"endpoint": "GET /orders/{region}", "body": body}, headers=AUTH
        )
        assert refused.status_code == 400 and "takes no body" in refused.text
        ok(client.post("/local-api/example", json={"endpoint": "POST /orders", "body": None}, headers=AUTH))
        endpoints = ok(client.get("/local-api", headers=AUTH))["endpoints"]
        assert next(e for e in endpoints if e["method"] == "POST")["example"] is None
