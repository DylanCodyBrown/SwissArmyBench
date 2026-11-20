"""A SQL Server connection on an endpoint that takes only part of SQL Server's language (Dataverse's SQL
endpoint: "Unsupported sql function PARSENAME"; the owner, 2026-11-20) lists its tables from
INFORMATION_SCHEMA instead. Made-up tables only."""

from __future__ import annotations

from typing import Any

import pytest

from swissarmybench.adapters.blade_run import BladeRunError, run_catalog
from swissarmybench.domain import sql_server


class Endpoint:
    """A stand-in for a partial endpoint: the rich catalog refused, INFORMATION_SCHEMA answered."""

    def __init__(self, plain_works: bool = True) -> None:
        self.plain_works = plain_works
        self.asked: list[str] = []

    def cursor(self) -> Any:
        endpoint = self

        class Cursor:
            description: Any = None

            def execute(self, sql: str) -> None:
                endpoint.asked.append(sql)
                if "PARSENAME" in sql:
                    raise RuntimeError(
                        '{"Message":"Unsupported sql function PARSENAME. Line:31, Position:17"}'
                    )
                if not endpoint.plain_works:
                    raise RuntimeError("Login failed for user")
                self.description = [
                    (n,)
                    for n in (
                        "table_catalog",
                        "table_schema",
                        "table_name",
                        "table_type",
                        "column_name",
                        "data_type",
                        "is_nullable",
                        "ordinal_position",
                    )
                ]

            def fetchall(self) -> list[tuple[Any, ...]]:
                return [("org", "dbo", "account", "BASE TABLE", "name", "nvarchar", "YES", 1)]

        return Cursor()


def test_the_rich_catalog_falls_back_to_information_schema() -> None:
    endpoint = Endpoint()
    columns, rows = run_catalog(endpoint, {}, "sql", sql_server.CATALOG, {}, "Made-up Dataverse")
    assert columns[2] == "table_name" and rows == [
        ["org", "dbo", "account", "BASE TABLE", "name", "nvarchar", "YES", 1]
    ]
    assert endpoint.asked == [sql_server.CATALOG, sql_server.PLAIN_CATALOG]


def test_when_the_plain_listing_fails_too_the_first_error_is_said() -> None:
    with pytest.raises(BladeRunError, match="PARSENAME"):
        run_catalog(Endpoint(plain_works=False), {}, "sql", sql_server.CATALOG, {}, "Made-up Dataverse")


def test_another_catalog_command_is_never_swapped() -> None:
    endpoint = Endpoint()
    with pytest.raises(BladeRunError):
        run_catalog(endpoint, {}, "sql", "SELECT PARSENAME('a.b', 1)", {}, "Made-up")
    assert len(endpoint.asked) == 1
