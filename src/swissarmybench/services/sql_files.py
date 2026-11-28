""".sql files on the Scripts page (the owner, 2026-11-24: "also we should allow .sql files" / "then when
you run
the file, it adds the table and opens the grid back on the grid menu" / "sql authorship will have one place in
scripts and not on the grid menu"; domain/sql_files.py the rules).

run: the file's one query (Run file) or the statement under the cursor (Run selection) becomes the open table
named after the file, through the same two paths the Tables page's query tab used: DuckDB over the open tables
(services/datasets.py build_from_query) or the connection's own SQL (services/connection_swap.py new_query). A
run again replaces that table; its grid, and so its steps, stay. A failure says the file's line it points at.

for_table: a table a query made, as its .sql file (Edit in Scripts): the project's scripts/<table>.sql (the
app's
own folder with no project open), written only when it is not there yet; the path to open.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmybench.domain import refusals
from swissarmybench.domain import sql_files as rules
from swissarmybench.domain import workbook_queries as workbook_rules
from swissarmybench.domain.variable_refs import MissingVariables
from swissarmybench.services.m_files import PowerQueryFiles
from swissarmybench.services.workbook_queries import WorkbookQueries
from swissarmybench.services.workspace import NotFound, Refused, Workspace

ConnectionQuery = Callable[[str, Any, str], Awaitable[dict[str, Any]]]


class Tables(Protocol):
    """services/datasets.py's DatasetService: the "+" tab's query, and where each table came from."""

    origins: Any

    async def build_from_query(self, name: str, text: str, replace: bool, who: str) -> dict[str, Any]: ...


class Files(Protocol):
    """adapters/workbench.py's Documents: the Workbench's files."""

    def read(self, path: str) -> tuple[str, str, float]: ...

    def write(
        self, path: str, text: str, force: bool = False, make_folder: bool = False
    ) -> tuple[str, float]: ...

    def exists(self, path: str) -> bool: ...

    def made_default_folder(self) -> str: ...


class Projects(Protocol):
    """services/sab_projects.py's SabProjects: the open project (its folder), or None."""

    current: Any


class Swap(Protocol):
    """services/connection_swap.py's ConnectionSwap: a new table from a query on a connection."""

    async def new_query(self, name: str, body: Any, who: str = ...) -> dict[str, Any]: ...


class CodeFiles(Protocol):
    """services/code_files.py: the file_changed notice."""

    async def touched(self, path: str, who: str) -> Any: ...


class SqlFiles:
    def __init__(
        self,
        ws: Workspace,
        tables: Any,
        swap: Swap,
        files: Any,
        projects: Any,
        code_files: CodeFiles,
        connections: Any,
        hooks: Any,
    ) -> None:
        self.ws = ws
        self._tables: Tables = tables
        self._connection_query: ConnectionQuery = swap.new_query
        self._files: Files = files
        self._projects: Projects = projects
        self._touched = code_files.touched
        # The Scripts page's other query language (the owner, 2026-11-27): a Power Query file's run, held here
        # as a text document's service is held by the Workbench. New file's "Import Power BI queries…" is
        # its maker; a project's table a query of it made is run again by it.
        self.power_query = PowerQueryFiles(ws, tables, connections, files, projects, code_files.touched)
        hooks.new_file_makers["powerquery_import"] = self.power_query.import_new
        projects.power_query = self.power_query.reopen
        # A workbook's own Power Query as one linked file (the owner, 2026-11-28): held by the Power Query
        # service, whose run reads the linked workbook's tables.
        self.power_query.workbooks = WorkbookQueries(
            ws, files, projects, code_files.touched, connections.approvals
        )
        hooks.new_file_makers[workbook_rules.TYPE] = self.power_query.workbooks.open_new

    async def run(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{path?, text?, connection?, line?, selection?, table?}: the file's query run; its table built.
        The text
        sent wins over the file's (the page's unsaved edits); with none, the file is read. `connection` sent
        (even "", the open tables) wins over the file's header. `line`: Run selection there (the selected
        text,
        else the statement at the line); none: Run file."""
        if not isinstance(body, dict):
            raise ValueError(
                'Send {"path": "orders_by_month.sql"} or {"text": "SELECT ...", "table": "..."}.'
            )
        path = body.get("path") if isinstance(body.get("path"), str) and body["path"].strip() else None
        text = body.get("text")
        if not isinstance(text, str):
            if path is None:
                raise ValueError('Send the file\'s "path" or its "text".')
            try:
                text = self._files.read(path)[0]
            except FileNotFoundError as error:
                raise NotFound(str(error)) from None
        given = body.get("connection")
        connection = (given.strip() or None) if isinstance(given, str) else rules.connection_of(text)
        line = body.get("line") if isinstance(body.get("line"), int) and body["line"] > 0 else None
        selection = body.get("selection") if isinstance(body.get("selection"), str) else None
        table = body.get("table") if isinstance(body.get("table"), str) and body["table"].strip() else None
        name = rules.table_name(table or path)
        statement = rules.to_run(text, selection, line)
        try:
            if connection:
                built = await self._connection_query(
                    name, {"connection": connection, "sql": statement.text, "replace": True}, who
                )
            else:
                built = await self._tables.build_from_query(name, statement.text, True, who)
        except (MissingVariables, refusals.Explained):
            raise  # their own fixes (Set it, Sign in) said as they are
        except Exception as error:
            said = str(error) or type(error).__name__
            raise rules.SqlFileError(
                refusals.first_sentence(said), rules.error_line(said, statement), said
            ) from None
        self.ws.audit.write(who, "sql_file_run", path or name, table=name, connection=connection or None)
        return built | {
            "table": name,
            "connection": connection,
            "line": statement.line,
            "end_line": statement.end_line,
        }

    async def for_table(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{table}: the .sql file of a table a query made (Edit in Scripts), written from its query when it is
        not there yet; {path, made, connection}."""
        table = body.get("table") if isinstance(body, dict) else None
        if not isinstance(table, str) or not table.strip():
            raise ValueError('Send {"table": "orders_by_month"}.')
        if self.ws.store.get(table) is None:
            raise NotFound(f"{table} is not open.")
        origin = self._tables.origins.get(table)
        if origin is not None and origin.m:  # a Power Query file's query: its own file
            return await self.power_query.for_table(table, origin, who)
        if origin is None or origin.kind not in ("query", "connection") or not origin.sql or origin.dax:
            raise Refused(f"{table} did not come from a SQL query: it has no query to edit.")
        connection = origin.connection if origin.kind == "connection" else None
        current = self._projects.current
        project = current.folder if current is not None else None
        base = project.rstrip("\\/") + "/scripts" if project else self._files.made_default_folder()
        path = f"{base}/{rules.file_name(table)}"
        made = False
        if not self._files.exists(path):
            path = self._files.write(path, rules.file_for(table, origin.sql, connection), make_folder=True)[0]
            made = True
            await self._touched(path, who)
            self.ws.audit.write(who, "sql_file_made", path, table=table)
        return {"path": path, "made": made, "connection": connection, "table": table}
