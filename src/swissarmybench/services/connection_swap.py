"""A table's connection swapped for another, and the code that named the old one pointed at the new one
(the owner, 2026-11-16: "I deleted the edp but need its queries to run on the other"; the rules are
domain/connection_swap.py).

  state    a table's connection (from where it came: its origin, or the project's file for one waiting
           to come back), how it was read (a catalog table, a query), the other connections, an undo
  swap     the table read again from the other connection with the SAME steps (the grid keeps its tab):
           a catalog table found in the other's catalog (asked to pick when it is not found, or found
           twice); a query answered for review (the page's SQL window) and run once it comes back
  move     every table that used a connection (a deleted one: the project's tables to fix) moved at once,
           each as in swap; the queries reviewed one by one, or run as they are
  undo     the table as it was before its last swap: its rows and its origin (or waiting again)
  repoint  the cells that name the old connection pointed at the new one: an open document in the
           Workbench window (unsaved until Save, or autosaved), any other's file (in a project, its folder)

Nothing is ever deleted: the old rows are kept for the undo until the next swap of that table (memory only).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain import connection_swap as rules
from swissarmybench.domain import connection_usage as usage_rules
from swissarmybench.domain.blades import BladeError
from swissarmybench.domain.catalogs import select_sql
from swissarmybench.domain.connection_swap import Place, SwapError
from swissarmybench.domain.datasets import Opened
from swissarmybench.domain.notebooks import NotebookError
from swissarmybench.domain.sab_files import Source, TableEntry
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.catalog_loading import CatalogLoading
from swissarmybench.services.catalogs import CatalogService
from swissarmybench.services.connection_usage import ConnectionUsage
from swissarmybench.services.connections import ConnectionService, TableRead
from swissarmybench.services.datasets import DatasetService
from swissarmybench.services.ports import BACKGROUND
from swissarmybench.services.sab_projects import SabProjects
from swissarmybench.services.workspace import NotFound, Workspace

MAX_PICKS = 200


@dataclass
class Before:
    """A table as it was before its last swap: open (its rows) or waiting to come back."""

    origin: Origin | None = None
    rows: Any = None
    opened: Opened | None = None
    waiting: TableEntry | None = None
    problem: dict[str, Any] | None = None
    connection: str = ""


class ConnectionSwap:
    def __init__(
        self,
        ws: Workspace,
        datasets: DatasetService,
        connections: ConnectionService,
        catalogs: CatalogService,
        loading: CatalogLoading,
        projects: SabProjects,
        usage: ConnectionUsage,
        reader: Any,  # query_table(cursor, sql): a table's rows (adapters/datasets.py)
        *,
        read_document: Callable[[str], tuple[str, str, float]],
        write_document: Callable[[str, str], Any],
        open_documents: Callable[[], Iterable[str]],
        ask_window: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None,
    ) -> None:
        self.ws = ws
        self._datasets = datasets
        self._connections = connections
        self._catalogs = catalogs
        self._loading = loading
        self._projects = projects
        self._usage = usage
        self._reader = reader
        self._read_document = read_document
        self._write_document = write_document
        self._open_documents = open_documents
        self._ask_window = ask_window
        self._before: dict[str, Before] = {}

    # ===== where a table comes from =====

    def _names(self) -> dict[str, str]:
        """The connections that hold tables (databases, Python), by their names casefolded."""
        found = {}
        for entry in self._connections.listing()["connections"]:
            if entry.get("connection") in ("database", "python"):
                found[str(entry["name"]).casefold()] = str(entry["name"])
        return found

    def _target(self, name: Any) -> str:
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Name the connection to use: {"to": "Trino"}.')
        found = self._names().get(" ".join(name.split()).casefold())
        if found is None:
            raise NotFound(f"There is no connection called {name} that holds tables.")
        return found

    def _from(self, name: str) -> dict[str, Any]:
        """What a table is read from: its connection (its base name), its place, its query."""
        if self.ws.store.get(name) is not None:
            origin = self._datasets.origins.get(name)
            if origin.kind == "connection" and origin.connection:
                base = origin.connection.split("/", 1)[0]
                if origin.place is not None and not (origin.dax and not origin.place[2]):
                    place = Place(*origin.place)
                    return {"open": True, "connection": base, "how": "table", "place": place,
                            "sql": origin.sql, "dax": origin.dax}  # fmt: skip
                return {"open": True, "connection": base, "how": "query", "sql": origin.sql or "",
                        "dax": origin.dax, "dataset": origin.connection.partition("/")[2]}  # fmt: skip
            if origin.kind == "file" and origin.connection and origin.place is not None:
                # A file connection's file (a folder's file, a workbook's sheet): its place there.
                return {"open": True, "connection": origin.connection, "how": "table",
                        "place": Place(*origin.place), "sql": None, "dax": False}  # fmt: skip
            if origin.kind == "query" and origin.sql:
                return {"open": True, "connection": "", "how": "query", "sql": origin.sql, "dax": False}
            return {"open": True, "connection": "", "how": origin.kind}
        waiting = self._projects.waiting(name)
        if waiting is None:
            raise NotFound(f"No table named {name} is open.")
        source = waiting.source
        if source.kind == "connection":
            if source.sql and not source.table:
                return {"open": False, "connection": source.connection or "", "how": "query",
                        "sql": source.sql, "dax": source.dax, "dataset": source.schema}  # fmt: skip
            place = Place(source.database, source.schema, source.table)
            return {"open": False, "connection": source.connection or "", "how": "table", "place": place,
                    "dax": source.dax}  # fmt: skip
        if source.kind == "query" and source.sql:
            return {"open": False, "connection": "", "how": "query", "sql": source.sql, "dax": False}
        return {"open": False, "connection": "", "how": source.kind}

    def state(self, name: str) -> dict[str, Any]:
        """A table's connection, how it is read, the other connections it could move to, and whether its
        last swap can be undone."""
        found = self._from(name)
        names = self._names()
        current = found["connection"]
        listed = {str(e["name"]).casefold() for e in self._connections.listing()["connections"]}
        exists = bool(current) and current.casefold() in listed
        place = found.get("place")
        return {
            "table": name,
            "connection": names.get(current.casefold(), current) if current else None,
            "exists": exists,
            "how": found["how"],
            "place": place.to_json() if isinstance(place, Place) else None,
            "sql": found.get("sql") or None,
            "open": found["open"],
            "others": [n for k, n in sorted(names.items()) if k != current.casefold()],
            "undo": name in self._before,
            "undo_connection": self._before[name].connection or None if name in self._before else None,
        }

    # ===== the other connection's table =====

    async def _candidates(self, to: str, table: str) -> list[Place]:
        if not await self._loading.ready(to):
            return []
        found = await self._catalogs.search(to, table, MAX_PICKS)
        return [Place(str(t["database"]), str(t["schema"]), str(t["table"])) for t in found["tables"]]

    async def _schemas(self, to: str) -> list[dict[str, Any]]:
        try:
            return list((await self._catalogs.schemas(to))["schemas"])
        except (KeyError, LookupError):
            return []

    def _suggested(self, to: str, place: Place) -> str:
        """A first query on the other connection for a table it does not hold by that name."""
        blade, _ = self._connections.blade(to)
        return select_sql(str(blade.dialect or "other"), place.database, place.schema, place.table, [], None)

    # ===== swap =====

    async def _old_rows(self, name: str) -> Any:
        info = self.ws.store.get(name)
        if info is None:
            return None
        return await self.ws.workers.run(
            BACKGROUND,
            self._reader.query_table,
            self.ws.store.cursor(),
            f"SELECT * FROM {info.table}",  # noqa: S608 (a quoted dataset name)
        )

    def _steps_check(self, name: str) -> list[str]:
        """The grids' steps against the new rows: each grid's first step that no longer works, in words."""
        info = self.ws.store.get(name)
        problems: list[str] = []
        if info is None:
            return problems
        cursor = self.ws.store.cursor()
        for grid in self.ws.grids.for_dataset(name):
            if not grid.steps:
                continue
            compiled = self.ws.compiled(cursor, grid, info)
            if compiled.error is not None:
                problems.append(f"Step {(compiled.error.index or 0) + 1}: {compiled.error.message}")
        return problems

    async def _keep(self, name: str, found: dict[str, Any]) -> None:
        """What the table is before a swap, for its undo (the last swap only)."""
        if found["open"]:
            info = self.ws.store.get(name)
            self._before[name] = Before(
                origin=self._datasets.origins.get(name),
                rows=await self._old_rows(name),
                opened=info.opened if info is not None else None,
                connection=found["connection"],
            )
        else:
            waiting = self._projects.waiting(name)
            problem = (self._projects.state().get("project") or {}).get("problems") or []
            said = next((p for p in problem if p.get("table") == name), None)
            self._before[name] = Before(waiting=waiting, problem=said, connection=found["connection"])

    async def _store(self, name: str, read: TableRead, who: str, place: Place | None) -> None:
        origin = Origin(
            "connection",
            connection=read.connection or None,
            sql=read.sql or None,
            dax=read.dax,
            code=read.code or None,
            place=(place.database, place.schema, place.table) if place is not None else None,
            whole=read.opened is None,
        )
        # The table's first grid takes the new rows; its steps and every other grid stay as they were.
        await self._datasets.store_table(name, read.table, "connection", False, who, opened=read.opened,
                                         origin=origin)  # fmt: skip

    async def swap(self, name: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Read a table from another connection, its steps kept: {"to", "place"?: the table there,
        "sql"?: the query to run there (a reviewed one), "all"?: every row, "dataset"?: a Power BI
        dataset}. Answers {"swapped"}, or {"review": the query to look over}, or {"pick": the other
        connection's tables to choose from}."""
        if not isinstance(body, dict):
            raise ValueError('Send {"to": "Trino"}.')
        to = self._target(body.get("to"))
        found = self._from(name)
        every = body.get("all") is True
        place = rules.place_of(body.get("place"))
        if body.get("sql") is not None:
            sql = rules.check_read_query(body.get("sql"))
            if not found["open"]:
                return await self._move_waiting(
                    name, Source("connection", connection=to, sql=sql, dax=bool(found.get("dax")),
                                 schema=str(body.get("dataset") or "")), found, who)  # fmt: skip
            read = await self._connections.read_query(to, sql, {"dataset": body.get("dataset") or ""})
            await self._keep(name, found)
            await self._store(name, read, who, None)
            return await self._done(name, to, found, who, "query")
        if found["how"] == "query" and place is None:
            return {"review": {"table": name, "to": to, "from": found["connection"] or None,
                               "sql": found.get("sql") or ""}}  # fmt: skip
        if found["how"] != "table" and place is None:
            raise SwapError(f"{name} does not come from a connection: there is nothing to swap.")
        old = found.get("place")
        if place is None and isinstance(old, Place):
            match, named = rules.match_place(old, await self._candidates(to, old.table))
            if match is None:
                return {
                    "pick": {
                        "table": name,
                        "to": to,
                        "from": found["connection"] or None,
                        "was": old.to_json(),
                        "candidates": [c.to_json() for c in named],
                        "schemas": await self._schemas(to),
                        "sql": self._suggested(to, old),
                    }
                }
            place = match
        if place is None:
            raise SwapError(f"Pick the table {name} is in {to}: place.")
        if not found["open"]:
            source = Source("connection", connection=to, database=place.database, schema=place.schema,
                            table=place.table, whole=True)  # fmt: skip
            return await self._move_waiting(name, source, found, who)
        blade, kind = self._connections.blade(to)
        read = await self._connections.read_table(blade, kind, place.to_json(), every, {})
        await self._keep(name, found)
        await self._store(name, read, who, place)
        return await self._done(name, to, found, who, "table", place)

    async def _move_waiting(
        self, name: str, source: Source, found: dict[str, Any], who: str
    ) -> dict[str, Any]:
        await self._keep(name, found)
        problem = await self._projects.move_waiting(name, source, who)
        if problem is not None:
            return {"table": name, "to": source.connection, "failed": problem.get("message") or "",
                    "problem": problem}  # fmt: skip
        return await self._done(name, source.connection or "", found, who, "query" if source.sql else "table")

    async def _done(
        self, name: str, to: str, found: dict[str, Any], who: str, how: str, place: Place | None = None
    ) -> dict[str, Any]:
        self.ws.audit.write(who, "swap_connection", name, to=to, was=found["connection"] or None)
        await self.ws.live.broadcast({"type": "table_connection", "dataset": name, "connection": to})
        await self._projects.changed()
        return {
            "swapped": {
                "table": name,
                "from": found["connection"] or None,
                "to": to,
                "how": how,
                "place": place.to_json() if place else None,
                "steps_problems": self._steps_check(name),
                "grids": [g.id for g in self.ws.grids.for_dataset(name)],
            }
        }

    async def new_query(self, name: str, body: Any, who: str = "user") -> dict[str, Any]:
        """New table from a query run on a connection, in its own SQL (the "+" tab's Query from: the owner,
        2026-11-17: "add a connection and query from that connection or choose Grids to query local"):
        {"connection", "sql", "dataset"?: a Power BI dataset for DAX, "replace"?: the tab's Run again, which
        rebuilds only a table such a query made}. The table remembers the connection and the query, so a
        project reads it again on open and the tab's tray runs it again."""
        if not isinstance(body, dict):
            raise ValueError('Send {"connection": "Warehouse", "sql": "SELECT ..."}.')
        to = self._target(body.get("connection"))
        sql = rules.check_read_query(body.get("sql"))
        existing = self.ws.store.get(name)
        if existing is not None:
            origin = self._datasets.origins.get(name)
            made_here = origin.kind == "connection" and bool(origin.sql) and existing.query is not None
            if not (body.get("replace") is True and made_here):
                raise ValueError(f"A table named {name!r} already exists; pick a new name.")
        read = await self._connections.read_query(to, sql, {"dataset": body.get("dataset") or ""})
        origin = Origin(
            "connection", connection=read.connection or to, sql=read.sql or sql, dax=read.dax, whole=True
        )
        result = await self._datasets.store_table(name, read.table, "connection", False, who, query=sql,
                                                  origin=origin)  # fmt: skip
        self.ws.audit.write(who, "connection_query", name, connection=to, rows=read.table.num_rows)
        await self._projects.changed()
        return result | {"rows": read.table.num_rows, "connection": to}

    async def undo(self, name: str, who: str = "user") -> dict[str, Any]:
        """The table as it was before its last swap (its rows and where they came from)."""
        before = self._before.pop(name, None)
        if before is None:
            raise NotFound(f"{name} has no swap to undo.")
        if before.waiting is not None:
            await self._datasets.close(name, who)
            await self._projects.wait_again(before.waiting, before.problem)
        else:
            kind = "connection" if (before.origin and before.origin.kind == "connection") else "sql_result"
            await self._datasets.store_table(name, before.rows, kind, False, who, opened=before.opened,
                                             origin=before.origin)  # fmt: skip
        self.ws.audit.write(who, "swap_connection_undone", name, to=before.connection or None)
        await self.ws.live.broadcast(
            {"type": "table_connection", "dataset": name, "connection": before.connection}
        )
        await self._projects.changed()
        return {"undone": name, "connection": before.connection or None}

    # ===== every table of a connection at once =====

    def tables_of(self, connection: str) -> list[str]:
        """The open tables and the project's waiting ones read from `connection`."""
        names = [i.name for i in self.ws.store.all()]
        names += [t.name for t in self._projects.waiting_tables() if t.name not in names]
        found = []
        for name in names:
            try:
                said = self._from(name)
            except NotFound:
                continue
            if said["connection"] and usage_rules.same_name(said["connection"], connection):
                found.append(name)
        return found

    async def move(self, connection: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Every table read from `connection` moved to another: {"to", "run_as_is"?: run the queries as
        they are (else each comes back for review)}. Each as swap answers it."""
        if not isinstance(body, dict):
            raise ValueError('Send {"to": "Trino"}.')
        to = self._target(body.get("to"))
        if usage_rules.same_name(to, connection):
            raise SwapError(f"The tables already use {to}.")
        moved: list[dict[str, Any]] = []
        review: list[dict[str, Any]] = []
        pick: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for name in self.tables_of(connection):
            found = self._from(name)
            ask: dict[str, Any] = {"to": to}
            if found["how"] == "query" and body.get("run_as_is") is True:
                ask["sql"] = found.get("sql") or ""
                ask["dataset"] = found.get("dataset") or ""
            try:
                answer = await self.swap(name, ask, who)
            except (BladeError, SwapError, ValueError, NotFound, LookupError) as error:
                failed.append({"table": name, "error": str(error)[:300]})
                continue
            except Exception as error:  # the connection's own code failing: its words, never a dead end
                failed.append({"table": name, "error": str(error)[:300] or type(error).__name__})
                continue
            if "swapped" in answer:
                moved.append(answer["swapped"])
            elif "review" in answer:
                review.append(answer["review"])
            elif "pick" in answer:
                pick.append(answer["pick"])
            else:
                failed.append({"table": name, "error": answer.get("failed") or ""})
        return {
            "from": connection,
            "to": to,
            "moved": moved,
            "review": review,
            "pick": pick,
            "failed": failed,
        }

    # ===== the code that names the old connection =====

    def references(self, connection: str) -> dict[str, Any]:
        """The cells that name `connection` (it may be deleted), each a pick for repoint; a table's
        read-only cell and an open grid follow their table, and a canvas block its cell."""
        found, unread = self._usage.references(connection)
        out = []
        for r in found:
            ref = r.to_json()
            ref["pickable"] = r.kind in ("notebook", "script") and not r.table_cell
            out.append(ref)
        return {"connection": connection, "references": out, "unread": unread}

    async def repoint(self, connection: str, body: Any, who: str = "user") -> dict[str, Any]:
        """Point cells at another connection: {"to", "picks"?: [{"document", "cell"}] (the cell's own
        number; null: a script's main code), every cell that names it when left out}."""
        if not isinstance(body, dict):
            raise ValueError('Send {"to": "Trino", "picks"?: [{"document", "cell"}]}.')
        to = body.get("to")
        if not isinstance(to, str) or not to.strip() or "\n" in to or len(to) > 200:
            raise ValueError('Name the connection the cells use now: {"to": "Trino"}.')
        to = to.strip()
        if to.casefold() not in self._names() and to.casefold() not in {
            str(c["name"]).casefold() for c in self._connections.listing()["connections"]
        }:
            raise NotFound(f"There is no connection called {to}.")
        picks = body.get("picks")
        wanted: dict[str, set[int | None]] = {}
        if picks is None:
            for ref in self.references(connection)["references"]:
                if ref["pickable"]:
                    wanted.setdefault(str(ref["document"]), set()).add(ref["cell"])
        else:
            if not isinstance(picks, list) or len(picks) > rules.MAX_CANDIDATES * 5:
                raise ValueError("picks is a list of {document, cell}.")
            for pick in picks:
                document = pick.get("document") if isinstance(pick, dict) else None
                cell = pick.get("cell") if isinstance(pick, dict) else None
                if not isinstance(document, str) or not (cell is None or isinstance(cell, int)):
                    raise ValueError(
                        "Each pick is {document: a file, cell: its number (null: the main code)}."
                    )
                wanted.setdefault(document, set()).add(cell)
        shown = {self._key(p) for p in self._open_documents()}
        changed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for document, cells in wanted.items():
            try:
                if (
                    self._key(document) in shown
                    and self._ask_window is not None
                    and self.ws.live.workbench_open()
                ):
                    answer = await self._ask_window(
                        "doc.repoint",
                        {
                            "path": document,
                            "from": connection,
                            "to": to,
                            "cells": sorted(cells, key=lambda c: c or 0),
                        },
                    )
                    done = list((answer or {}).get("cells") or []) if isinstance(answer, dict) else []
                    changed.append({"document": document, "cells": done, "unsaved": True})
                    continue
                text, full, _ = self._read_document(document)
                written, done = rules.repoint_document(full, text, connection, to, cells)
                if done:
                    self._write_document(full, written)
                changed.append({"document": full, "cells": done, "unsaved": False})
            except (OSError, ValueError, NotebookError, LookupError) as error:
                failed.append({"document": document, "error": str(error)[:300]})
            except Exception as error:  # the window could not (a document closed meanwhile): said
                failed.append({"document": document, "error": str(error)[:300] or type(error).__name__})
        count = sum(len(c["cells"]) for c in changed)
        self.ws.audit.write(who, "repoint_connection", connection, to=to, cells=count)
        await self._projects.changed()
        return {"from": connection, "to": to, "changed": changed, "failed": failed, "cells": count}

    @staticmethod
    def _key(path: str) -> str:
        return path.replace("\\", "/").casefold()

    @staticmethod
    def rewrite(body: Any) -> dict[str, Any]:
        """The Workbench window's helper: one cell's text or a script's pointed at another connection
        ({"kind": "python" | "line" | "script", "text", "from", "to", "cells"?})."""
        if not isinstance(body, dict):
            raise ValueError('Send {"kind", "text", "from", "to"}.')
        kind, text, old, new = (body.get(k) for k in ("kind", "text", "from", "to"))
        if (
            not isinstance(text, str)
            or not isinstance(old, str)
            or not isinstance(new, str)
            or not old
            or not new
        ):
            raise ValueError('Send {"kind", "text", "from", "to"} as text.')
        if len(text) > 1_000_000:
            raise ValueError("At most a million characters.")
        if kind == "line":
            return {"text": rules.repoint_line(text, old, new)}
        if kind == "python":
            written, count = rules.repoint_python(text, old, new)
            return {"text": written, "changed": count}
        if kind == "script":
            cells = body.get("cells")
            picked = None if cells is None else {c if isinstance(c, int) else None for c in cells}
            written, done = rules.repoint_script(text, old, new, picked)
            return {"text": written, "cells": done}
        raise ValueError('kind is "python", "line" or "script".')
