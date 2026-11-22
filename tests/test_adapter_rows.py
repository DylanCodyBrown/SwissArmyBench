"""The lakes and SharePoint as a backend of the adapter (Plans/adapter.plan.md, Order 2): a connection whose
own code reads a table given columns, filters and a limit (lakes.READ's contract). The adapter folds those
three, in SQL's order, and does the rest over the answer; tests/test_lakes.py runs the real kinds' Open as
grid on it against tests/lake_standins.py. Made-up data only."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from swissarmybench.adapters import sab_adapter as sab
from swissarmybench.adapters.sab_adapter import Filter, Plan

STOCK = pa.table({"sku": ["a-1", "b-2", "c-3", "d-4"], "qty": [5, 0, 12, 3], "bin": ["N", "S", "N", "S"]})


class Shelf:
    """A connection shaped like the lakes' and SharePoint's: rows() applies what it is sent."""

    def __init__(self) -> None:
        self.asked: list[dict[str, Any]] = []

    def catalog(self) -> list[dict[str, str]]:
        return [{"table_schema": "store", "table_name": "stock", "column_name": n, "data_type": "VARCHAR"}
                for n in STOCK.column_names]  # fmt: skip

    def rows(self, table: str, schema: str = "", limit: Any = None, columns: Any = None, filters: Any = None,
             frame: bool = False) -> tuple[pa.Table, int]:  # fmt: skip
        self.asked.append(
            {"table": table, "schema": schema, "limit": limit, "columns": columns, "filters": filters}
        )
        found = STOCK
        for column, op, value in filters or []:
            assert op in (">", "<>")
            keep = [(v > value) if op == ">" else (v != value) for v in found.column(column).to_pylist()]
            found = found.filter(pa.array(keep))
        total = found.num_rows
        found = found.select(columns) if columns else found
        return (found.slice(0, limit) if limit is not None else found), total


def test_filters_columns_and_limit_are_sent_and_said() -> None:
    shelf = Shelf()
    source = sab.Rows(shelf)
    plan = Plan(columns=("sku",), filters=(Filter("qty", ">", 1), Filter("bin", "!=", "X")), limit=2)
    reader, folded = sab.read(source, "store/stock", plan)
    assert folded.parts == ("filters", "columns", "limit")
    assert reader.read_all().column("sku").to_pylist() == ["a-1", "c-3"]
    assert shelf.asked[-1] == {"table": "stock", "schema": "store", "limit": 2, "columns": ["sku"],
                               "filters": [["qty", ">", 1], ["bin", "<>", "X"]]}  # fmt: skip
    assert source.total == 3


def test_a_sort_stops_the_limit_being_sent() -> None:
    shelf = Shelf()
    reader, folded = sab.read(sab.Rows(shelf), "store/stock", Plan(sort=(("qty", True),), limit=1))
    assert folded.parts == ()
    assert reader.read_all().column("sku").to_pylist() == ["c-3"]
    assert shelf.asked[-1]["limit"] is None


def test_tables_come_from_the_connections_catalog() -> None:
    listed = sab.tables(sab.Rows(Shelf()))
    assert [(t.name, [c.name for c in t.columns]) for t in listed] == [("store/stock", ["sku", "qty", "bin"])]
