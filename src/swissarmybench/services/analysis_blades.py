"""Analysis blades: the user's own analyses in the Analyze page's toolbar (Yours; their contracts read by
services/analyze.py), each run on a grid's rows as it shows them, in a child process (server/blade_runner.py).
Split from services/blades.py (craft review 2026-11-22), which makes it and hands it its ports.

  analyses        the analysis blades: name, description, tags
  analysis_blade  one by its name (BladeError: it is not an analysis blade)
  analyze         one run on a grid's view (its steps), up to max_analysis_rows: {"title", "cards", "blade"}
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmybench.domain.analysis import whole_view_queries
from swissarmybench.domain.blades import Blade, BladeError
from swissarmybench.domain.datasets import DatasetInfo
from swissarmybench.domain.grids import Grid
from swissarmybench.services.ports import BACKGROUND, SqlSession
from swissarmybench.services.workspace import Workspace


class Store(Protocol):
    """The saved blades (adapters/blades.py BladeStore)."""

    def all(self) -> list[Blade]: ...

    def get(self, name: str) -> Blade: ...


class AnalysisBlades:
    """Analysis blades: the user's own analyses in the Analyze page's toolbar (Yours), each run on a grid's
    rows as it shows them in a child process. Split from BladeService (craft review 2026-11-22); its ports:
    the saved blades, the values a blade's secrets were typed, the child process's run."""

    def __init__(
        self,
        ws: Workspace,
        store: Store,
        typed: Callable[[Blade, Any], dict[str, str]],
        run: Callable[..., Awaitable[dict[str, Any]]],
    ) -> None:
        self.ws = ws
        self._blades = store
        self._typed = typed
        self._run = run

    def analyses(self) -> dict[str, Any]:
        """The analysis blades, for the Analyze menu: name, description, favourite."""
        found = [b for b in self._blades.all() if b.kind == "analysis"]
        return {"analyses": [{"name": b.name, "description": b.description, "tags": b.tags} for b in found]}

    def analysis_blade(self, name: str) -> Blade:
        """An analysis blade by its name (the Analyze page reads its contract from its code)."""
        blade = self._blades.get(name)
        if blade.kind != "analysis":
            raise BladeError(f"{blade.name} is not an analysis blade.")
        return blade

    async def analyze(
        self, name: str, grid: Grid, info: DatasetInfo, body: dict[str, Any], who: str
    ) -> dict[str, Any]:
        """Run the analysis blade `name` on the grid's rows as it shows them (its steps), in a child
        process: {"title", "cards"}, ready for Visualizations."""
        blade = self._blades.get(name)
        if blade.kind != "analysis":
            raise BladeError(f"{blade.name} is not an analysis blade.")
        columns = body.get("columns") or []
        if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
            raise BladeError("columns is a list of the grid's column names.")
        ws = self.ws
        limit = ws.settings.max_analysis_rows

        def read(cur: SqlSession) -> Any:
            with ws.views.reading(cur, info, grid.steps, grid.settings) as rows:
                how_many, every = whole_view_queries(f"({rows}) AS src")
                counted = cur.execute(how_many).fetchone()
                if counted and int(counted[0]) > limit:
                    raise BladeError(
                        f"{counted[0]:,} rows is more than an analysis blade takes ({limit:,}): "
                        "filter the grid first."
                    )
                return cur.execute(every).to_arrow_table()

        table = await ws.grid_query(grid, None, BACKGROUND, read)
        typed = self._typed(blade, body)
        answer = await self._run(blade, "analysis", typed, {"table": table, "columns": columns})
        ws.audit.write(who, "blade_analysis", info.name, blade=blade.name)
        return {
            "title": answer.get("title") or blade.name,
            "cards": answer.get("cards", []),
            "blade": blade.name,
        }
