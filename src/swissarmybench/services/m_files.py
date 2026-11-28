"""Power Query files on the Scripts page (the owner, 2026-11-27: "I just want a run button and the power query
runs" / "against the original source"; domain/m_files.py the rules, src/duckpq.py the compiler).

The app is ONE caller of duckpq: it compiles the file with duckpq.compile and resolves what the compiler asks
for its own way, through its own engine, then runs each query's composed DuckDB SQL through the same path a
.sql file's run takes (services/datasets.py build_from_query: the guard, the open tables as their tabs show
them, `[Conn].table` read through the connection tables contract).

run       Run file: every query of the file that is a table, in dependency order; with a line (or a query's
          name): that one. Each becomes the open table of its name (replaced on the next run), which shows its
          M read-only with Edit in Scripts and Show as SQL.
problems  what cannot run, before a run: a mistake in the text, a function duckpq does not run, a source no
          saved connection matches. Nothing is read (no file, no connection).
sql       the DuckDB SQL the compiler composed for each query, and the sources it names.
for_table a table a query made, as its file (Edit in Scripts).
import_new a Power BI dataset's queries (.pbix, .pbit, .pbip) as one new .pq file (New file's maker).
reopen    a project's table read again from its query (services/sab_projects.py).

What the compiler asks for and who answers: a database source -> the saved connection whose settings match
(domain/m_files.py connection_for), named `[Conn].[schema].[table]` in the SQL, its columns from its catalog
(else from the table read once); a native query -> run on that connection, its rows an Arrow table the SQL
names; a file (CSV, workbook sheet, Parquet, JSON) -> the app's own readers, an Arrow table the SQL names; a
${NAME} -> this computer's variable; a column's values (Table.Pivot) -> one query through the same path.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

import duckpq
from swissarmybench.domain import m_files as rules
from swissarmybench.domain import new_files, refusals
from swissarmybench.domain.blades import detect_settings
from swissarmybench.domain.table_cells import Origin
from swissarmybench.domain.variable_refs import MissingVariables
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace


class PowerQueryError(ValueError):
    """What a Power Query file's run cannot do: one sentence, the file's line and column it points at, the
    name it is about and the query it is in; `add_connection`: no saved connection is its source (the page
    offers Add connection)."""

    def __init__(
        self,
        what: str,
        line: int | None = None,
        column: int | None = None,
        name: str | None = None,
        query: str | None = None,
        details: str | None = None,
        add_connection: bool = False,
    ) -> None:
        super().__init__(what)
        self.line, self.column, self.name, self.query = line, column, name, query
        self.details, self.add_connection = details, add_connection


class Tables(Protocol):
    """services/datasets.py's DatasetService."""

    origins: Any
    connection_sql: Any

    async def build_from_query(
        self,
        name: str,
        text: str,
        replace: bool,
        who: str,
        tables: Mapping[str, Any] | None = None,
        origin: Origin | None = None,
    ) -> dict[str, Any]: ...

    async def query_table(
        self, text: str, name: str = "", tables: Mapping[str, Any] | None = None
    ) -> tuple[Any, list[Any]]: ...

    async def read_file(self, path: str, sheet: str | None) -> Any: ...

    async def resolve_text(self, text: str, where: str) -> str: ...


class Connections(Protocol):
    """services/connections.py's ConnectionService."""

    def listing(self) -> dict[str, Any]: ...

    def blade(self, name: str) -> tuple[Any, str]: ...

    async def read_query(self, name: str, sql: str, more: dict[str, Any]) -> Any: ...


class Files(Protocol):
    """adapters/workbench.py's Documents."""

    def read(self, path: str) -> tuple[str, str, float]: ...

    def write(
        self, path: str, text: str, force: bool = False, make_folder: bool = False
    ) -> tuple[str, float]: ...

    def exists(self, path: str) -> bool: ...

    def made_default_folder(self) -> str: ...

    def dataset_queries(self, path: str) -> rules.DatasetQueries: ...


class Projects(Protocol):
    current: Any


def _folder_of(path: str | None) -> str | None:
    if not path:
        return None
    plain = path.replace("\\", "/")
    return plain.rsplit("/", 1)[0] if "/" in plain else None


class _Resolution:
    """One run's (or one look's) answers to what the compiler asks for: the Arrow tables the SQL names, and
    each key resolved."""

    def __init__(self) -> None:
        self.tables: dict[str, Any] = {}
        self.reads: list[dict[str, Any]] = []
        self.workbook: str | None = None  # the workbook the file is linked to (Excel.CurrentWorkbook())


class PowerQueryFiles:
    def __init__(
        self,
        ws: Workspace,
        tables: Tables,
        connections: Connections,
        files: Files,
        projects: Projects,
        touched: Callable[[str, str], Awaitable[Any]],
    ) -> None:
        self.ws = ws
        self._tables = tables
        self._connections = connections
        self._files = files
        self._projects = projects
        self._touched = touched
        # A linked file's workbook (services/workbook_queries.py), set by SqlFiles.
        self.workbooks: Any = None

    # ===== what the compiler is told =====

    def saved_connections(self) -> list[rules.Connection]:
        """Every saved connection with the settings its code names (never a secret), for the matching."""
        found: list[rules.Connection] = []
        for row in self._connections.listing()["connections"]:
            try:
                blade = self._connections.blade(str(row["name"]))[0]
                settings = {s.name: str(s.value) for s in detect_settings(blade.code) if s.value is not None}
            except Exception:  # noqa: S112 (a connection whose code cannot be read is not matched)
                continue
            found.append(rules.Connection(blade.name, str(blade.template or ""), settings))
        return found

    def _context(self, path: str | None) -> duckpq.Context:
        open_tables = {i.name: [c.name for c in i.columns] for i in self.ws.store.all()}
        return duckpq.Context(tables=open_tables, folder=_folder_of(path), bind_variables=True)

    def _text(self, body: Any) -> tuple[str, str | None]:
        if not isinstance(body, dict):
            raise ValueError('Send {"path": "orders.pq"} or {"text": "let ... in ...", "path"?}.')
        path = body.get("path") if isinstance(body.get("path"), str) and body["path"].strip() else None
        text = body.get("text")
        if not isinstance(text, str):
            if path is None:
                raise ValueError('Send the file\'s "path" or its "text".')
            try:
                text = self._files.read(path)[0]
            except FileNotFoundError as error:
                raise NotFound(str(error)) from None
        return text, path

    def _matched(self, source: duckpq.Source, saved: list[rules.Connection]) -> Any:
        """A database source's saved connection, or the Failure the compiler says at its line."""
        try:
            return rules.connection_for(source, saved)
        except rules.NoConnection as error:
            return duckpq.Failure(str(error))

    def _lint_answers(
        self, context: duckpq.Context, saved: list[rules.Connection], linked: bool = False
    ) -> None:
        """What can be answered with nothing read: a database source no saved connection matches (a linked
        file's Excel.CurrentWorkbook() is its workbook: read on a run)."""
        for key in context.missing:
            if key[0] != "source":
                continue
            source = context.sources[key[1]]
            if source.function == rules.CURRENT_WORKBOOK and linked:
                continue
            if source.kind == "call":
                found = self._matched(source, saved)
                if isinstance(found, duckpq.Failure):
                    context.resolved[key] = found

    # ===== problems, before a run =====

    async def problems(self, body: Any) -> dict[str, Any]:
        """{path?, text?}: what cannot run, found without reading anything: {problems: [{message, line,
        column, name, query}], queries: [{name, kind, line, end_line}]}."""
        text, path = self._text(body)
        context = self._context(path)
        saved = self.saved_connections()
        compiled = duckpq.compile(text, rules.query_name(path), context)
        if context.missing:
            linked = self.workbooks is not None and self.workbooks.table_path(text, path) is not None
            self._lint_answers(context, saved, linked)
            compiled = duckpq.compile(text, rules.query_name(path), context)
        return {
            "problems": [p.to_json() for p in compiled.problems],
            "queries": [
                {
                    "name": x.name,
                    "kind": x.kind,
                    "line": x.line,
                    "end_line": x.end_line,
                    "table": rules.table_name(x.name),
                }
                for x in compiled.queries
            ],
        }

    # ===== resolving: the app's own way to each thing the compiler asks for =====

    async def _resolve(
        self, key: duckpq.Key, context: duckpq.Context, held: _Resolution, saved: list[rules.Connection]
    ) -> Any:
        try:
            if key[0] == "variable":
                return await self._tables.resolve_text("${" + str(key[1]) + "}", "the Power Query file")
            if key[0] == "json":
                return json.loads(await asyncio.to_thread(lambda: self._files.read(str(key[1]))[0]))
            if key[0] == "probe":
                table, _ = await self._tables.query_table(str(key[1]), "", held.tables)
                return table.column(0).to_pylist() if table.num_columns else []
            return await self._source(context.sources[key[1]], held, saved)
        except MissingVariables as error:
            return duckpq.Failure(refusals.first_sentence(str(error)))
        except FileNotFoundError as error:
            # M's own read would raise too: a `try` around the source takes its otherwise (duckpq 1.1.1)
            return duckpq.Failure(refusals.first_sentence(str(error)) or "No file.", raised=True)
        except (OSError, ValueError, LookupError, refusals.Explained) as error:
            return duckpq.Failure(refusals.first_sentence(str(error)) or type(error).__name__)
        except Exception as error:  # a connection's own code failing: its words, at the source's line
            return duckpq.Failure(refusals.first_sentence(str(error)) or type(error).__name__)

    async def _source(self, source: duckpq.Source, held: _Resolution, saved: list[rules.Connection]) -> Any:
        if source.kind == "file":
            if "://" not in str(source.path) and not self._files.exists(str(source.path)):
                raise FileNotFoundError(f"No file at {source.path}.")
            table = await self._tables.read_file(str(source.path), source.sheet)
            held.tables[source.name] = table
            return duckpq.Resolved([str(n) for n in table.schema.names])
        if source.function == rules.CURRENT_WORKBOOK:
            return await self._workbook_table(source, held)
        found = self._matched(source, saved)
        if isinstance(found, duckpq.Failure):
            return found
        if source.query is not None:
            read = await self._connections.read_query(found.name, source.query, {})
            held.tables[source.name] = read.table
            held.reads.append({"connection": found.name, "rows": int(read.table.num_rows), "query": True})
            return duckpq.Resolved([str(n) for n in read.table.schema.names])
        named = rules.reference(found, source)
        columns = await self._tables.connection_sql.columns_of(found.name, rules.table_parts(source, found))
        if not columns:  # its catalog names no columns: the table read once says them
            table = await self._tables.connection_sql.read_named(named)
            columns = [str(n) for n in table.schema.names]
        return duckpq.Resolved(columns, named)

    async def _workbook_table(self, source: duckpq.Source, held: _Resolution) -> Any:
        """Excel.CurrentWorkbook(){[Name = "Table1"]}[Content]: that named table (or sheet) of the workbook
        the file is linked to, read through the app's own workbook reader (the adapter's Excel source)."""
        name = next((str(s["Name"]) for s in source.navigation if s.get("Name")), "")
        if held.workbook is None:
            return duckpq.Failure(
                "Excel.CurrentWorkbook() is the workbook a file is linked to, and this file names none "
                "(Edit workbook queries… links one)."
            )
        if not name:
            return duckpq.Failure(
                'Pick the workbook\'s table: Excel.CurrentWorkbook(){[Name = "Table1"]}[Content].'
            )
        table = await self._tables.read_file(held.workbook, name)
        held.tables[source.name] = table
        return duckpq.Resolved([str(n) for n in table.schema.names])

    async def _compiled(
        self, text: str, path: str | None
    ) -> tuple[duckpq.Compiled, duckpq.Context, _Resolution]:
        """The file compiled with everything it asks for resolved."""
        context, held, saved = self._context(path), _Resolution(), self.saved_connections()
        if self.workbooks is not None:
            held.workbook = self.workbooks.table_path(text, path)
        name = rules.query_name(path)
        for _ in range(rules.MAX_ROUNDS):
            compiled = duckpq.compile(text, name, context)
            if compiled.complete:
                return compiled, context, held
            for key in list(context.missing):
                context.resolved[key] = await self._resolve(key, context, held, saved)
        raise PowerQueryError("The file's sources could not all be resolved.", 1)

    def _raise(self, problem: duckpq.Problem) -> None:
        raise PowerQueryError(
            problem.message, problem.line, problem.column, problem.name, problem.query,
            add_connection="Add connection" in problem.message,
        )  # fmt: skip

    def _wanted(self, compiled: duckpq.Compiled, body: dict[str, Any]) -> list[duckpq.Query]:
        """The queries a run runs: the one named or under the cursor's line, else every table of the file."""
        named = body.get("query") if isinstance(body.get("query"), str) and body["query"].strip() else None
        line = body.get("line") if isinstance(body.get("line"), int) and body["line"] > 0 else None
        if named is None and line is None:
            for problem in compiled.problems:
                self._raise(problem)
            tables = compiled.tables()
            if not tables:
                raise PowerQueryError("The file has no query that is a table yet.", 1)
            return tables
        one = rules.query_at(compiled, line) if named is None and line is not None else None
        if named is not None:
            one = next((x for x in compiled.queries if x.name == named), None)
        if one is None:
            raise PowerQueryError(
                f"The file has no query named {named}." if named else "No query is here.", line
            )
        if one.problem is not None:
            self._raise(one.problem)
        if one.kind != "table":
            words = {"value": "a value (a parameter)", "function": "a function"}.get(one.kind, one.kind)
            raise PowerQueryError(
                f"{one.name} is {words}, not a table: nothing to open.", one.line, 1, one.name
            )
        return [one]

    # ===== run =====

    async def run(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{path?, text?, line?, query?}: the file's queries run, each the open table of its name. The text
        sent wins over the file's (the page's unsaved edits). `line`: the query under the cursor; `query`:
        the one named; neither: Run file. {tables: [{table, query, grid, dataset, rows, line, end_line}],
        table, grid, rows (the last one built: what the page brings forward)}."""
        text, path = self._text(body)
        compiled, _, held = await self._compiled(text, path)
        if not compiled.queries and compiled.problems:
            self._raise(compiled.problems[0])
        built: list[dict[str, Any]] = []
        lines = text.replace("\r\n", "\n").split("\n")
        for query in self._wanted(compiled, body):
            name = rules.table_name(query.name)
            written = "\n".join(lines[query.line - 1 : query.end_line])
            origin = Origin("query", sql=query.sql, path=path, m=written, m_query=query.name)
            tables = {s: held.tables[s] for s in query.sources if s in held.tables}
            try:
                made = await self._tables.build_from_query(name, str(query.sql), True, who, tables, origin)
            except (MissingVariables, refusals.Explained):
                raise
            except Exception as error:
                said = str(error) or type(error).__name__
                raise PowerQueryError(
                    f"{query.name}: {refusals.first_sentence(said)}",
                    query.line,
                    1,
                    query.name,
                    query.name,
                    said,
                ) from None
            built.append(
                {k: made.get(k) for k in ("grid", "dataset", "version", "rows")}
                | {"table": name, "query": query.name, "line": query.line, "end_line": query.end_line}
            )
        self.ws.audit.write(
            who, "power_query_run", path or built[-1]["table"], tables=[b["table"] for b in built]
        )
        return {"tables": built, "sources": [s.to_json() for s in compiled.sources.values()]} | built[-1]

    async def reopen(self, table: str, path: str, query: str, who: str = "user") -> None:
        """A project's table read again from its Power Query file's query (the project opened)."""
        if not self._files.exists(path):
            raise FileNotFoundError(f"{path} is not there.")
        await self.run({"path": path, "query": query}, who)

    # ===== the composed SQL =====

    async def sql(self, body: Any) -> dict[str, Any]:
        """{path?, text?, line?, query?}: the DuckDB SQL the compiler composed for each query (or the one at
        the line, or named), with the sources its SQL names. The sources are resolved (their columns are
        needed), nothing is built."""
        text, path = self._text(body)
        compiled, _, _ = await self._compiled(text, path)
        if not compiled.queries and compiled.problems:
            self._raise(compiled.problems[0])
        asked = dict(body) if isinstance(body, dict) else {}
        here = rules.query_at(compiled, asked["line"]) if isinstance(asked.get("line"), int) else None
        if here is not None and not asked.get("query") and here.kind in ("value", "function"):
            asked.pop("line")  # the cursor is in a parameter or a function: every table's SQL instead
        wanted = self._wanted(compiled, asked)
        return {
            "queries": [
                {
                    "query": x.name,
                    "table": rules.table_name(x.name),
                    "sql": x.sql,
                    "columns": list(x.columns),
                    "line": x.line,
                    "sources": [compiled.sources[s].to_json() for s in x.sources if s in compiled.sources],
                }
                for x in wanted
            ]
        }

    # ===== Edit in Scripts =====

    async def for_table(self, table: str, origin: Origin, who: str = "user") -> dict[str, Any]:
        """A table a Power Query made, as its file: the one it ran from, else (run from text alone) the
        project's scripts/<table>.pq written from its M."""
        if origin.path and self._files.exists(origin.path):
            return {
                "path": origin.path,
                "made": False,
                "connection": None,
                "table": table,
                "query": origin.m_query,
            }
        current = self._projects.current
        project = current.folder if current is not None else None
        base = project.rstrip("\\/") + "/scripts" if project else self._files.made_default_folder()
        path = f"{base}/{rules.file_name(table)}"
        made = False
        if not self._files.exists(path):
            path = self._files.write(path, (origin.m or "").rstrip("\n") + "\n", make_folder=True)[0]
            made = True
            await self._touched(path, who)
            self.ws.audit.write(who, "power_query_file_made", path, table=table)
        return {"path": path, "made": made, "connection": None, "table": table, "query": origin.m_query}

    # ===== an export: the file with the library beside it =====

    async def export(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{path}: the file's export, so its M runs anywhere (a Function App among them) with no app: the
        file, duckpq.py as it is, run.py, requirements.txt and README.md in the project's
        exports/powerquery/<name>/ (no project open: <name>_export beside the file). Only a file whose bytes
        change is written. {folder, files, sources}."""
        text, path = self._text(body)
        if path is None:
            raise ValueError('Send the saved file\'s "path": its export is made beside it.')
        context = self._context(path)
        compiled = duckpq.compile(text, rules.query_name(path), context)
        if compiled.problems and not compiled.queries:
            self._raise(compiled.problems[0])
        library = await asyncio.to_thread(lambda: self._files.read(str(duckpq.__file__))[0])
        made = rules.export_files(path, text, list(context.sources.values()), library)
        current = self._projects.current
        name = rules.query_name(path)
        if current is not None:
            folder = f"{str(current.folder).replace(chr(92), '/').rstrip('/')}/{rules.EXPORT_FOLDER}/{name}"
        else:
            folder = f"{_folder_of(path) or '.'}/{name}_export"
        written: list[str] = []
        for file, content in made.items():
            target = f"{folder}/{file}"
            same = self._files.exists(target) and self._files.read(target)[0] == content
            if not same:
                await asyncio.to_thread(self._files.write, target, content, True, True)
                written.append(file)
        self.ws.audit.write(who, "power_query_export", path, files=len(made))
        return {
            "folder": folder,
            "files": sorted(made),
            "written": written,
            "sources": [s.to_json() for s in context.sources.values()],
        }

    # ===== a dataset's queries as one file =====

    async def import_new(self, body: dict[str, Any], who: str = "user") -> dict[str, Any]:
        """New file's maker for "Import Power BI queries…": {name, folder, source, check}: the dataset's
        queries (a .pbix, .pbit or .pbip at `source`) as one new .pq file, named and placed as New file
        places any file. With `check`, only where it would go."""
        kind = new_files.type_of("powerquery_import", (), True)
        current = self._projects.current
        folder = current.folder if current is not None else None
        try:
            if folder:
                root = str(folder).replace("\\", "/").rstrip("/")
                relative = new_files.place(
                    kind,
                    body.get("name"),
                    body.get("folder"),
                    lambda inside: self._files.exists(f"{root}/{inside}"),
                )
                full = f"{root}/{relative}"
            else:
                full = new_files.loose_place(kind, body.get("name"), body.get("folder"), self._files.exists)
                relative = full.rsplit("/", 1)[-1]
        except new_files.NameTaken as error:
            raise Conflict(str(error)) from None
        made = {"path": full, "relative": relative}
        if body.get("check"):
            return made
        source = body.get("source")
        if not isinstance(source, str) or not source.strip():
            raise Refused("Pick the Power BI file to import: a .pbix, a .pbit or a .pbip.")
        try:
            queries = await asyncio.to_thread(self._files.dataset_queries, source.strip())
            text = rules.document(queries, source.strip().replace("\\", "/").rsplit("/", 1)[-1])
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        except rules.ImportError_ as error:
            raise Refused(str(error)) from None
        full = (await asyncio.to_thread(self._files.write, full, text, False, True))[0]
        await self._touched(full, who)
        self.ws.audit.write(who, "power_query_import", relative, tables=len(queries.tables))
        return made | {"path": full, "queries": len(queries.tables), "parameters": len(queries.parameters),
                       "skipped": [name for name, _ in queries.skipped]}  # fmt: skip
