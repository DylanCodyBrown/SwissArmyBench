"""Web call blades' rules (domain/web_calls.py): the shapes a response comes in, DuckDB's conversion of
them, the header's types, the settings and the tables contract. Made-up data only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from swissarmybench.domain import web_calls as rules
from swissarmybench.domain.web_calls import WebCallError

HEADER = [
    {"name": "id", "type": "bigint"},
    {"name": "name", "type": "varchar"},
    {"name": "amt", "type": "decimal(10,2)"},
]


def run(conversion: str, pages: list[Any], tmp_path: Path) -> list[tuple[Any, ...]]:
    """The conversion as the API blade runs it: every page a row of `response`, then DuckDB's query."""
    file = tmp_path / "pages.ndjson"
    file.write_text("".join(json.dumps({"page": p}) + "\n" for p in pages), encoding="utf-8")
    con = duckdb.connect()
    view = f"CREATE VIEW response AS SELECT * FROM read_json_auto('{file}', format='newline_delimited')"  # noqa: S608 (a test's own temporary file)
    con.execute(view)
    return con.sql(conversion).fetchall()


def settings(found: dict[str, Any] | None) -> dict[str, Any]:
    assert found is not None
    call = {"api": "Shop", "operation": "list", "method": "GET", "path": "/x", "as_table": True} | found
    return rules.check_web_call(call)


@pytest.mark.parametrize(
    ("page", "shape", "records", "header"),
    [
        ([{"a": 1}], "records", "$", ""),
        ({"data": [{"a": 1}]}, "records", "$.data", ""),
        ({"value": [{"a": 1}], "@odata.nextLink": "https://x/next"}, "records", "$.value", ""),
        ({"result": {"items": [{"a": 1}]}}, "records", "$.result.items", ""),
        ({"columns": ["id", "name"], "rows": [[1, "Acme"]]}, "header_rows", "$.rows", "$.columns"),
        ({"header": ["id"], "data": [[1]]}, "header_rows", "$.data", "$.header"),
        ({"headers": ["id"], "values": [[1]]}, "header_rows", "$.values", "$.headers"),
        ({"columns": HEADER, "data": [[1, "Acme", 2.5]]}, "header_rows", "$.data", "$.columns"),
        ({"rows": [["id", "name"], [1, "Acme"]]}, "header_rows", "$.rows", "first_row"),
        ([["id", "name"], [1, "Acme"]], "header_rows", "$", "first_row"),
        ({"data": {"columns": ["id"], "rows": [[1]]}}, "header_rows", "$.data.rows", "$.data.columns"),
        (
            {"result": {"header": ["id"], "values": [[1]]}},
            "header_rows",
            "$.result.values",
            "$.result.header",
        ),
    ],
)
def test_the_common_shapes_are_found(page: Any, shape: str, records: str, header: str) -> None:
    found = rules.detect(page)
    assert found is not None and (found["shape"], found["records"], found["header"]) == (
        shape,
        records,
        header,
    )


def test_a_response_with_no_table_has_none() -> None:
    assert rules.detect({"id": 1, "name": "Acme"}) is None and rules.detect("text") is None
    assert rules.detect({"value": [1, 2]}) is None


def test_the_next_field_is_found_for_paging() -> None:
    assert rules.detect({"value": [{"a": 1}], "@odata.nextLink": "u"})["next"] == "@odata.nextLink"  # type: ignore[index]
    assert rules.detect({"data": {"columns": ["a"], "rows": [[1]]}, "nextUri": "u"})["next"] == "nextUri"  # type: ignore[index]


def test_header_types_become_duckdbs_and_win(tmp_path: Path) -> None:
    assert [rules.duckdb_type(t) for t in ("bigint", "INT", "string", "float8", "timestamp with time zone",
                                           "decimal(10,2)", "bool", "date", "mystery")] == [
        "BIGINT", "BIGINT", "VARCHAR", "DOUBLE", "TIMESTAMP", "DECIMAL(10, 2)", "BOOLEAN", "DATE", None,
    ]  # fmt: skip
    call = settings(rules.detect({"columns": HEADER, "data": [[1, "Acme", "2.50"]]}))
    assert call["columns"] == {"id": "BIGINT", "name": "VARCHAR", "amt": "DECIMAL(10, 2)"}
    assert 'AS "id"' in call["conversion"] and "TRY_CAST" in call["conversion"]
    rows = run(
        call["conversion"], [{"columns": HEADER, "data": [[1, "Acme", "2.50"], [2, "Birch", 7]]}], tmp_path
    )
    assert [(r[0], r[1], float(r[2])) for r in rows] == [(1, "Acme", 2.5), (2, "Birch", 7.0)]


def test_header_and_rows_across_pages_read_the_header_once(tmp_path: Path) -> None:
    pages = [
        {"columns": ["id", "name"], "rows": [[1, "Acme"], [2, "Birch"]], "nextUri": "https://x/2"},
        {"columns": ["id", "name"], "rows": [[3, "Cedar"]]},
    ]
    call = settings(rules.detect(pages[0]))
    assert call["columns"] == {"id": "", "name": ""}  # no types in the header: text, as read
    assert run(call["conversion"], pages, tmp_path) == [("1", "Acme"), ("2", "Birch"), ("3", "Cedar")]


def test_a_header_row_as_the_first_row_is_skipped(tmp_path: Path) -> None:
    page = {"rows": [["id", "name"], [1, "Acme"], [2, "Birch"]]}
    call = settings(rules.detect(page))
    assert run(call["conversion"], [page], tmp_path) == [("1", "Acme"), ("2", "Birch")]


def test_records_are_unnested_by_duckdb_nested_lists_kept(tmp_path: Path) -> None:
    page = {
        "data": {
            "items": [
                {"id": 1, "c": {"region": "N"}, "lines": [1, 2]},
                {"id": 2, "c": {"region": "S"}, "lines": []},
            ]
        }
    }
    call = settings({"shape": "records", "records": "$.data.items", "flatten": True})
    assert run(call["conversion"], [page, page], tmp_path)[:2] == [(1, "N", [1, 2]), (2, "S", [])]
    kept = settings({"shape": "records", "records": "$.data.items", "flatten": False})
    assert run(kept["conversion"], [page], tmp_path)[0] == (1, {"region": "N"}, [1, 2])


def test_the_settings_are_checked() -> None:
    base = {"api": "Shop", "operation": "list", "method": "GET", "path": "/x"}
    assert rules.check_web_call(base)["as_table"] is False  # off unless said
    for bad in ({**base, "records": "items"}, {**base, "method": "FETCH"}, {**base, "paging": "some"},
                {**base, "columns": {"a": "bigint; DROP"}}, {"operation": "x"}):  # fmt: skip
        with pytest.raises(WebCallError):
            rules.check_web_call(bad)


def test_the_tables_contract_is_exactly_the_switched_on_calls() -> None:
    def blade(op: str, on: bool, inputs: dict[str, Any]) -> dict[str, Any]:
        call = {"api": "Shop", "operation": op, "method": "GET", "path": f"/{op}", "as_table": on}
        source = rules.code("Shop", "GET", f"/{op}", "", inputs, None, rules.check_web_call(call))
        return {"name": rules.name_of("Shop", op), "code": source, "web_call": rules.check_web_call(call)}

    blades = [
        blade("orders", True, {}),
        blade("order", True, {"path": {"order_id": None}}),
        blade("create", False, {}),
    ]
    found = rules.table_calls(blades, "Shop")
    assert [(t["table"], t["needs"]) for t in found] == [("order", ["order_id (path)"]), ("orders", [])]
    catalog, read = rules.tables_boxes(found)
    assert "orders" in catalog and "create" not in catalog and "needs" in read


def test_a_web_call_blades_code_and_what_the_app_runs_of_it() -> None:
    source = rules.code("Shop", "POST", "/orders", "Make one", {"query": {"dry": True}}, {"sku": "A-1"})
    assert 'api = sab.blade("Shop")' in source and 'body = {"sku": "A-1"}' in source
    assert rules.values_of(source) == {"inputs": {"query": {"dry": True}}, "body": {"sku": "A-1"}}
    assert "sab.blade" not in rules.call_section(source)
    command = rules.send_command(source)
    compile(command, "send", "exec")
    assert "except api.Error" in command
