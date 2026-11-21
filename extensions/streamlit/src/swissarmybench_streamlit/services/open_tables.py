"""The open tables (a tab in the grid) as a canvas's widgets read them: their names as Python variables with
their columns (the Properties pane's table and column pickers, a value's check), and one table after its
grid's steps as Parquet (written beside a run's pages as data/<name>.parquet, or into an export)."""

from __future__ import annotations

from typing import Any

from swissarmybench.domain.codegen import variable_name
from swissarmybench.domain.datasets import DatasetInfo, quote
from swissarmybench.domain.export import ExportOptions
from swissarmybench.domain.grids import POS, Grid
from swissarmybench.services.ports import BACKGROUND

_PARQUET = ExportOptions(format="parquet", provenance=False)


class OpenTables:
    def __init__(self, ws: Any, writer: Any) -> None:
        self.ws = ws
        self._writer = writer  # the base's export writer

    def _tables(self) -> dict[str, tuple[DatasetInfo, Grid]]:
        found: dict[str, tuple[DatasetInfo, Grid]] = {}
        for info in self.ws.store.all():
            grid = self.ws.grids.first_for(info.name)
            if grid is not None:
                found.setdefault(variable_name(info.name), (info, grid))
        return found

    def columns(self) -> dict[str, list[str] | None]:
        """Each open table's name (as a Python variable) and its columns."""
        return {name: [c.name for c in info.columns] for name, (info, _grid) in self._tables().items()}

    def _parquet(self, info: DatasetInfo, grid: Grid) -> bytes:
        cursor = self.ws.store.cursor()
        steps = [s for s in grid.steps if not s.params.get("header")]
        positioned, columns = self.ws.views.positioned_sql(cursor, info, steps, grid.settings)
        names = ", ".join(quote(c.name) for c in columns)
        sql = f"SELECT {names} FROM ({positioned}) ORDER BY {POS}"  # noqa: S608 (quoted names of an open table)
        data: bytes = self._writer.write(self.ws.store.cursor(), sql, columns, _PARQUET, None, 0)
        return data

    async def data(self, table: str) -> bytes:
        """An open table after its grid's steps, as Parquet's bytes."""
        info, grid = self._tables()[table]
        found: bytes = await self.ws.workers.run(BACKGROUND, self._parquet, info, grid)
        return found
