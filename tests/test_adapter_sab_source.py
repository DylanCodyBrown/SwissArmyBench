"""A connection's client says what it is (adapter 1.10.0; docs/reviews/craft-review-2026-11-22.md, the
domain's finding 3): its `sab_source` is read before its methods are looked at, so a method added for
another reason never turns one kind of source into another; a client that says nothing (an older saved
connection's code) is told by its methods as before. Made-up data only."""

from __future__ import annotations

import ast
from typing import Any

import pyarrow as pa
import pytest

from swissarmybench.adapters import adapter as sab
from swissarmybench.domain import dataverse, lakes, sharepoint


class Reads:
    """A client that reads a table itself (catalog, rows), with whatever else a test gives it."""

    def catalog(self) -> list[dict[str, str]]:
        return [{"table_name": "stock", "column_name": "sku", "data_type": "VARCHAR"}]

    def rows(self, *args: Any, **kwargs: Any) -> Any:
        return pa.table({"sku": ["a-1"]}), 1


class SaysRows(Reads):
    sab_source = "rows"

    def described(self, table: str) -> list[dict[str, str]]:  # a method for something else: still Rows
        return []


class SaysOData(Reads):
    sab_source = "odata"


class SaysList(Reads):
    sab_source = "list"

    def write_delta(self, *args: Any) -> None:  # never called: it says it is a list
        raise AssertionError("not a lake")

    def create(self, table: str, rows: list[dict[str, Any]]) -> dict[str, int]:
        self.made = rows
        return {"done": len(rows)}

    def ids(self, table: str, values: Any, key: str = "id") -> dict[Any, int]:
        return {}


class SaysLake(Reads):
    sab_source = "lake"

    def create(self, *args: Any) -> None:  # a lake with a create of its own is still a lake
        raise AssertionError("not a list")

    def ids(self, *args: Any) -> None:
        raise AssertionError("not a list")


class Sniffed(Reads):
    def described(self, table: str) -> list[dict[str, str]]:
        return []


def test_what_a_client_says_wins_over_its_methods() -> None:
    assert isinstance(sab.source_from(SaysRows()), sab.Rows)  # it has described, and says rows
    assert isinstance(sab.source_from(SaysOData()), sab.OData)  # no described, and says odata
    assert isinstance(sab.source_from(SaysList()), sab.Rows)
    assert sab.said_source(SaysLake()) == "lake" and sab.said_source(Reads()) == ""


def test_a_client_that_says_nothing_or_an_unknown_word_is_told_by_its_methods() -> None:
    assert isinstance(sab.source_from(Sniffed()), sab.OData)
    assert isinstance(sab.source_from(Reads()), sab.Rows)
    odd = Sniffed()
    odd.sab_source = "a newer word"  # type: ignore[attr-defined]
    assert sab.said_source(odd) == "" and isinstance(sab.source_from(odd), sab.OData)


def test_rows_writes_by_what_the_client_says() -> None:
    rows = pa.table({"Title": ["a made-up task"]}).to_reader()
    listed = SaysList()
    counts = sab.Rows(listed, "Tasks").write("Tasks", rows, (), "insert")
    assert counts.inserted == 1 and listed.made == [{"Title": "a made-up task"}]
    with pytest.raises(sab.AdapterError, match="read only"):
        sab.Rows(SaysRows(), "Docs").write("Documents", pa.table({"a": [1]}).to_reader(), (), "insert")


def _says(code: str, cls: str) -> str | None:
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if (
                    isinstance(item, ast.Assign)
                    and [getattr(t, "id", "") for t in item.targets] == ["sab_source"]
                    and isinstance(item.value, ast.Constant)
                ):
                    return str(item.value.value)
    return None


def test_the_generated_clients_say_what_they_are() -> None:
    assert _says(dataverse.MANAGED, "Dataverse") == "odata"
    assert _says(lakes.DATALAKE_SIGN_INS[0][2], "Lake") == "lake"
    assert _says(sharepoint.LISTS, "SharePointLists") == "list"
    assert _says(sharepoint.DOCS, "SharePointDocuments") == "rows"
    assert {"odata", "lake", "list", "rows"} == set(sab.SAB_SOURCES)
