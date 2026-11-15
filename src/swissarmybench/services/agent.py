"""The agent door: what an MCP client may read and ask for (plan section 12).

The agent sees what the page shows: schemas, profiles, step values and rows, up to 1,048,576 rows
per read (one Excel sheet). Exports by an agent always wait for the user's click (a one-time ticket)
and write only into the export folder.

Blades: the agent works them through the blades routes like the user (blades_create and the rest;
the golden rule). The old propose-then-Allow door here was removed on 2026-11-14.

The current table: the workspace page reports which grid tab is in front, and the agent reads a short
summary of it (metadata only: the dataset, the row count, columns and types, steps, the selection
size, the other open tables), the way an IDE hands a model the open file.

Limitation, stated plainly: the approval trusts the browser. Any process running as the same user can
read the connection file and answer; the gate stops an agent that only has the MCP tools, not code
already running with the user's rights.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from swissarmygrid.domain.datasets import DatasetInfo, quote
from swissarmygrid.domain.export import FORMATS
from swissarmygrid.domain.grids import Grid
from swissarmygrid.services.ports import AGENT, Notifier, SqlSession
from swissarmygrid.services.profile import profile_column, profile_table
from swissarmygrid.services.workspace import Refused, Workspace
from swissarmygrid.settings import EXCEL_MAX_ROWS

# The most rows one agent read returns: as many as one Excel worksheet holds. The agent still
# picks its own limit.
AGENT_ROW_CAP: int = EXCEL_MAX_ROWS
APPROVAL_TIMEOUT_SECONDS: float = 180.0
# How long the user's click on an export stays good for the export it approved.
EXPORT_TICKET_SECONDS: float = 120.0


@dataclass
class ExportTickets:
    """Approved agent exports not yet written: ticket -> (grid id, when it lapses). One click, one
    file. The export use case writes an agent's file only against a ticket, so an agent cannot skip
    the user's click by calling the export route directly."""

    held: dict[str, tuple[str, float]] = field(default_factory=dict)

    def issue(self, grid_id: str) -> str:
        now = time.monotonic()
        self.held = {k: v for k, v in self.held.items() if v[1] > now}
        ticket = secrets.token_urlsafe(16)
        self.held[ticket] = (grid_id, now + EXPORT_TICKET_SECONDS)
        return ticket

    def redeem(self, ticket: str | None, grid_id: str) -> bool:
        """True once for a ticket the user approved for this grid; it is used up either way."""
        held = self.held.pop(ticket, None) if ticket else None
        return held is not None and held[0] == grid_id and held[1] > time.monotonic()


@dataclass
class Approval:
    id: str
    dataset: str
    action: str
    detail: str
    future: asyncio.Future[bool]

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dataset": self.dataset,
            "action": self.action,
            "detail": self.detail,
        }


class Approvals:
    """Questions for the user that wait for one answer: the page shows each, and a click (or three
    minutes) resolves it. A rendezvous, not an event: the asker needs the answer."""

    def __init__(self, live: Notifier) -> None:
        self._live = live
        self._pending: dict[str, Approval] = {}

    async def ask(self, dataset: str, action: str, detail: str) -> bool:
        loop = asyncio.get_running_loop()
        approval = Approval(secrets.token_hex(4), dataset, action, detail, loop.create_future())
        self._pending[approval.id] = approval
        await self._live.broadcast({"type": "approval_requested", **approval.to_json()})
        try:
            return await asyncio.wait_for(approval.future, APPROVAL_TIMEOUT_SECONDS)
        except TimeoutError:
            return False
        finally:
            self._pending.pop(approval.id, None)
            await self._live.broadcast({"type": "approval_resolved", "id": approval.id})

    def pending(self) -> list[dict[str, Any]]:
        return [a.to_json() for a in self._pending.values()]

    def get(self, approval_id: str) -> Approval | None:
        return self._pending.get(approval_id)


class AgentService:
    def __init__(
        self,
        ws: Workspace,
        approvals: Approvals,
        tickets: ExportTickets,
    ) -> None:
        self.ws = ws
        self.approvals = approvals
        self._tickets = tickets
        # The grid tab in front, as the workspace page last reported it.
        self._active: str | None = None
        # What describe and profile found, by load (a dataset's name and serial) and column: an
        # agent asks about the same table again and again, and only a new push changes the answer.
        self._profiled: OrderedDict[tuple[str, int, str | None], Any] = OrderedDict()

    async def _profile_once(
        self, info: DatasetInfo, column: str | None, compute: Callable[[SqlSession], Any]
    ) -> Any:
        key = (info.name, info.serial, column)
        if key in self._profiled:
            self._profiled.move_to_end(key)
            return self._profiled[key]
        ws = self.ws
        found = await ws.workers.run(AGENT, lambda: compute(ws.store.cursor()))
        self._profiled[key] = found
        while len(self._profiled) > 256:
            self._profiled.popitem(last=False)
        return found

    # ===== the user's answers =====

    def resolve_approval(self, approval: Approval, body: Any) -> dict[str, Any]:
        approved = bool(isinstance(body, dict) and body.get("approve"))
        if not approval.future.done():
            approval.future.set_result(approved)
        self.ws.audit.write("user", "approval", approval.dataset, approved=approved, request=approval.action)
        return {"id": approval.id, "approved": approved}

    # ===== agent reads =====

    def _dataset(self, name: str) -> DatasetInfo:
        info = self.ws.store.get(name)
        if info is None:
            raise LookupError("No such dataset.")
        return info

    async def describe(self, dataset: str) -> dict[str, Any]:
        """Schema, counts and the profile of every column."""
        ws = self.ws
        info = self._dataset(dataset)

        def compute(cur: SqlSession) -> Any:
            names = ", ".join(quote(c.name) for c in info.columns)
            sql = f"SELECT {names} FROM {info.table}"
            return profile_table(cur, sql, info.columns)

        profiled = await self._profile_once(info, None, compute)
        ws.audit.write("agent", "describe", info.name)
        return {
            "dataset": info.name,
            "version": info.version,
            "rows": info.row_count,
            "columns": profiled["columns"],
            "duplicate_rows": profiled["duplicate_rows"],
            "grids": [g.id for g in ws.grids.for_dataset(info.name)],
        }

    async def profile(self, dataset: str, column_name: str | None) -> Any:
        ws = self.ws
        info = self._dataset(dataset)
        column = next((c for c in info.columns if c.name == column_name), None)
        if column is None:
            raise LookupError(f"No column {column_name!r}.")
        sql = f"SELECT * FROM {info.table}"
        result = await self._profile_once(info, column.name, lambda cur: profile_column(cur, sql, column))
        ws.audit.write("agent", "profile", info.name, column=column.name)
        return result

    async def read_grid(self, grid: Grid, info: DatasetInfo, offset: int, limit: int) -> dict[str, Any]:
        """A window of the grid's view as the user sees it, always with the view's row count.

        The agent picks offset and limit, capped at 1,048,576 rows."""
        ws = self.ws
        cap = AGENT_ROW_CAP
        take = min(limit, cap)

        def count(cur: SqlSession) -> tuple[int, list[str]]:
            n = ws.views.row_count(cur, info, grid.steps, grid.settings, None)
            return n, [c.name for c in ws.compiled(cur, grid, info).columns]

        row_count, names = await ws.grid_query(grid, None, AGENT, count)
        out: dict[str, Any] = {
            "grid": grid.id,
            "dataset": info.name,
            "row_count": row_count,
            "offset": offset,
            "row_cap": cap,
            "columns": names,
            "rows": [],
        }
        if take == 0 or offset >= row_count:
            return out
        end = min(row_count, offset + take)

        def read(cur: SqlSession) -> list[list[Any]]:
            window = ws.views.window(cur, info, grid.steps, grid.settings, offset, end)
            return [list(r) for r in window.rows]

        rows = await ws.grid_query(grid, None, AGENT, read)
        ws.audit.write("agent", "read", info.name, grid=grid.id, rows=len(rows))
        return out | {"rows": rows, "capped": limit > cap}

    # ===== the current table =====

    def set_active(self, grid_id: Any) -> dict[str, Any]:
        """The workspace page says which grid tab is in front."""
        self._active = grid_id if isinstance(grid_id, str) and self.ws.grids.get(grid_id) else None
        return {"grid": self._active}

    async def current(self) -> dict[str, Any]:
        """A short summary of the table the user is looking at, and the other open tables."""
        ws = self.ws
        grid = ws.grids.get(self._active) if self._active else None
        others = [
            {
                "dataset": i.name,
                "rows": i.row_count,
                "grids": [g.id for g in ws.grids.for_dataset(i.name)],
            }
            for i in sorted(ws.store.all(), key=lambda i: i.name)
        ]
        out: dict[str, Any] = {"active": None, "open_tables": others}
        info = ws.store.get(grid.dataset) if grid else None
        if grid is None or info is None:
            return out

        def describe(cur: SqlSession) -> tuple[int | None, list[dict[str, str]]]:
            try:
                n: int | None = ws.views.row_count(cur, info, grid.steps, grid.settings, None)
                columns = ws.compiled(cur, grid, info).columns
            except ws.engine_error:
                return None, [{"name": c.name, "type": c.type} for c in info.columns]
            return n, [{"name": c.name, "type": c.type} for c in columns]

        row_count, columns = await ws.grid_query(grid, None, AGENT, describe)
        steps = [s.to_json() for s in grid.steps]
        out["active"] = {
            "grid": grid.id,
            "dataset": info.name,
            "dataset_rows": info.row_count,
            "view_rows": row_count,
            "columns": columns,
            "steps": steps,
            "selected_rows": grid.selected,
        }
        return out

    # ===== exports =====

    async def approve_export(self, grid: Grid, info: DatasetInfo, fmt: str) -> dict[str, Any]:
        """An agent export: always waits for the user's click (plan section 10a). The click gives a
        one-time ticket, and the export writes an agent's file only against one, so skipping this
        step is refused by the server, not just by the command that normally calls it."""
        if fmt not in FORMATS:  # the text goes into the user's approval prompt
            raise ValueError(f"format must be one of {', '.join(FORMATS)}.")
        detail = f"{fmt} export of {info.name} to the export folder"
        if not await self.approvals.ask(info.name, "export", detail):
            raise Refused("The user declined (or did not answer) this export.")
        return {"approved": True, "ticket": self._tickets.issue(grid.id)}
