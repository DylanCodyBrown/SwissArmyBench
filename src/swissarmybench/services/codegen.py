"""Copy as code: generate, then verify what the user will paste (plan section 9).

The text is the domain's (domain/codegen.py). Every result is verified before it is offered:
exactly the copied text runs in a fresh namespace holding only the user's variable (the
`CodeVerifier` port; adapters/codegen.py), and what it assigns is compared, row by row and in order,
with what the grid shows. Only verified code gets the copy buttons; otherwise the response carries
the first differing row.
"""

from __future__ import annotations

from typing import Any

from swissarmygrid.domain.codegen import (
    pasted_for,
    python_code,
    reads_text,
    view_query,
)
from swissarmygrid.domain.datasets import DatasetInfo
from swissarmygrid.domain.grids import Grid
from swissarmygrid.domain.sql_guard import SqlGrammar
from swissarmygrid.domain.steps import Step, StepError, ViewSettings
from swissarmygrid.services.ports import BACKGROUND, CodeVerifier, SqlSession, Views
from swissarmygrid.services.workspace import Workspace


def generate_code(
    cursor: SqlSession,
    views: Views,
    info: DatasetInfo,
    steps: list[Step],
    settings: ViewSettings,
    *,
    verifier: CodeVerifier,
    grammar: SqlGrammar,
) -> dict[str, Any]:
    """The grid's steps as one DuckDB query, checked: `verifier` runs exactly the copied text and
    compares what it assigns with the grid's rows."""
    compiled = views.compile(cursor, info, steps, settings)
    if compiled.error is not None:
        raise StepError(compiled.error.index, f"Fix this step first: {compiled.error.message}")
    sql = view_query(info, compiled, steps, settings, grammar.keywords)
    code = python_code(sql, info.name, info.source_kind)
    expected = views.window(cursor, info, steps, settings, 0, max(1, info.row_count))
    pasted = pasted_for(info.name, info.source_kind, code, sql)
    outcome = verifier.verify(pasted, cursor, info.table, [c.name for c in expected.columns], expected.rows)
    return {
        "code": code,
        # The query alone ("Copy as SQL"); the code runs exactly this text.
        "sql": sql,
        "variable": pasted.variable,
        "result_variable": pasted.result,
        "reads": reads_text(info.name, info.source_kind),
        "verified": outcome.identical,
        "difference": outcome.message,
        "note": outcome.note,
        "rows_checked": len(expected.rows),
        "reason": None,
    }


class CodeService:
    """Copy as code for a grid: the use case the door calls."""

    def __init__(self, ws: Workspace, verifier: CodeVerifier) -> None:
        self.ws = ws
        self._verifier = verifier

    async def code(self, grid: Grid, info: DatasetInfo, who: str) -> dict[str, Any]:
        ws = self.ws

        def make(cur: SqlSession) -> dict[str, Any]:
            return generate_code(
                cur,
                ws.views,
                info,
                grid.steps,
                grid.settings,
                verifier=self._verifier,
                grammar=ws.grammar,
            )

        result = await ws.grid_query(grid, None, BACKGROUND, make)
        ws.audit.write(who, "code", info.name, verified=result["verified"])
        return result
