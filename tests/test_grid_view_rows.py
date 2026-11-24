"""An open table's view rows at given places (services/grids.py view_rows: what a sandbox grid's edit names),
on fakes of the workspace: no DuckDB (craft review 2026-11-22, item 8). Made-up rows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from swissarmybench.services.grids import view_rows

ROWS = [[1, "Ada"], [2, "Ben"]]


@dataclass
class Views:
    asked: list[tuple[int, int]] = field(default_factory=list)

    def window(self, cursor: Any, info: Any, steps: Any, settings: Any, start: int, end: int, _: Any) -> Any:
        self.asked.append((start, end))
        columns = [SimpleNamespace(name="id"), SimpleNamespace(name="name")]
        return SimpleNamespace(columns=columns, rows=ROWS[start:end])


def _ws(open_: bool = True) -> Any:
    grid = SimpleNamespace(steps=[], settings={})
    views = Views()

    async def grid_query(g: Any, generation: Any, priority: Any, read: Any) -> Any:
        assert g is grid
        return read("cursor")

    return SimpleNamespace(
        grids=SimpleNamespace(first_for=lambda name: grid if open_ else None),
        store=SimpleNamespace(get=lambda name: object()),
        views=views,
        grid_query=grid_query,
    )


def test_the_rows_at_each_place_and_the_columns_shown() -> None:
    ws = _ws()
    shown, rows = asyncio.run(view_rows(ws, "orders", [1, 0, 5]))
    assert shown == ["id", "name"]
    assert rows == [[2, "Ben"], [1, "Ada"], None]
    assert ws.views.asked == [(1, 2), (0, 1), (5, 6)]


def test_a_table_not_open_is_said() -> None:
    with pytest.raises(LookupError, match="orders is not open on the Tables page"):
        asyncio.run(view_rows(_ws(open_=False), "orders", [0]))
