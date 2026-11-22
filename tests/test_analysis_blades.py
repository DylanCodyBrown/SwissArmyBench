"""Analysis blades on their own (services/analysis_blades.py), over fakes of the store, the workspace and the
child process (craft review 2026-11-22, item 10). Made-up names and rows."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from swissarmybench.domain.blades import Blade, BladeError
from swissarmybench.services.analysis_blades import AnalysisBlades

BLADES = [
    Blade(name="Odds by region", kind="analysis", description="Made up", tags=["mine"]),
    Blade(name="Warehouse", kind="sql"),
]


class Store:
    def all(self) -> list[Blade]:
        return BLADES

    def get(self, name: str) -> Blade:
        return next(b for b in BLADES if b.name == name)


class Cursor:
    def __init__(self, rows: int) -> None:
        self.rows = rows

    def execute(self, sql: str) -> Any:
        return SimpleNamespace(fetchone=lambda: (self.rows,), to_arrow_table=lambda: "the table")


def _ws(rows: int) -> Any:
    audit: list[tuple[str, str, str]] = []

    @contextmanager
    def reading(cur: Any, info: Any, steps: Any, settings: Any) -> Any:
        yield "SELECT * FROM orders"

    async def grid_query(grid: Any, generation: Any, priority: Any, read: Any) -> Any:
        return read(Cursor(rows))

    return SimpleNamespace(
        settings=SimpleNamespace(max_analysis_rows=100),
        views=SimpleNamespace(reading=reading),
        grid_query=grid_query,
        audit=SimpleNamespace(write=lambda who, action, what, **more: audit.append((who, action, what))),
        said=audit,
    )


def _blades(rows: int = 10) -> tuple[AnalysisBlades, list[Any]]:
    ran: list[Any] = []

    async def run(blade: Blade, mode: str, typed: dict[str, str], extra: dict[str, Any]) -> dict[str, Any]:
        ran.append((blade.name, mode, extra))
        return {"title": "Odds", "cards": [{"kind": "note"}]}

    return AnalysisBlades(_ws(rows), Store(), lambda blade, body: {}, run), ran


def test_the_analysis_blades_are_listed_and_found_by_name() -> None:
    blades, _ = _blades()
    assert blades.analyses() == {
        "analyses": [{"name": "Odds by region", "description": "Made up", "tags": ["mine"]}]
    }
    assert blades.analysis_blade("Odds by region").kind == "analysis"
    with pytest.raises(BladeError, match="Warehouse is not an analysis blade"):
        blades.analysis_blade("Warehouse")


def test_a_run_reads_the_grid_s_view_and_is_audited() -> None:
    blades, ran = _blades()
    info = SimpleNamespace(name="orders")
    grid = SimpleNamespace(steps=[], settings={})
    answer = asyncio.run(blades.analyze("Odds by region", grid, info, {"columns": ["region"]}, "agent"))  # type: ignore[arg-type]
    assert answer == {"title": "Odds", "cards": [{"kind": "note"}], "blade": "Odds by region"}
    assert ran == [("Odds by region", "analysis", {"table": "the table", "columns": ["region"]})]
    assert blades.ws.said == [("agent", "blade_analysis", "orders")]  # type: ignore[attr-defined]


def test_too_many_rows_and_bad_columns_are_said() -> None:
    blades, _ = _blades(rows=1000)
    grid, info = SimpleNamespace(steps=[], settings={}), SimpleNamespace(name="orders")
    with pytest.raises(BladeError, match="more than an analysis blade takes"):
        asyncio.run(blades.analyze("Odds by region", grid, info, {"columns": []}, "user"))  # type: ignore[arg-type]
    with pytest.raises(BladeError, match="columns is a list"):
        asyncio.run(blades.analyze("Odds by region", grid, info, {"columns": "region"}, "user"))  # type: ignore[arg-type]
