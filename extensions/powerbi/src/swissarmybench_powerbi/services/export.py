"""Export to Power BI… on the ERD page (the owner, 2026-11-19: "Make a powerbi desktop file with our model
exported an option on the erd page"): the model's tables, relationships and each table's Power Query as a
Power BI Project. Rules in domain/export.py (the files) and domain/power_query.py (each source's M).

  plan    what the dialog shows: the tables the ERD shows, each going or not (why, and its fix: Include its
          rows), its notes (steps not carried, a type as text, Only works on your machine), the relationships
          that go (active or not, and why) and the ones left out
  export  the files written into the open project's `powerbi/` (only changed bytes; an earlier export's stale
          files removed), or with no project a zip of the same folder; rows only on the Include its rows
          tick, the agent's waiting for the user's Allow
  open    the .pbip opened in Power BI Desktop (Windows, when it has a program) or its folder shown: the
          user's click only

Never a password, token or secret in the files: a `${NAME}` becomes a Power Query parameter whose value is the
variable's plain shareable value, else empty for the user to fill in; Power BI Desktop asks for credentials.
"""

from __future__ import annotations

import asyncio
import posixpath
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import connection_tables as table_rules
from swissarmybench.domain import portability
from swissarmybench.domain import variable_refs as refs
from swissarmybench.domain.blades import Blade, BladeCodeError, detect_settings
from swissarmybench.domain.codegen import variable_name, view_query
from swissarmybench.domain.datasets import Column, DatasetInfo, quote
from swissarmybench.domain.export import ExportOptions
from swissarmybench.domain.grids import POS, Grid
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.ports import BACKGROUND, Approvals, SqlSession
from swissarmybench.services.relationships import Models
from swissarmybench.services.workspace import NotFound, Refused, Workspace
from swissarmybench_powerbi.domain import export as rules
from swissarmybench_powerbi.domain import pbix_import as import_rules
from swissarmybench_powerbi.domain import power_query as pq
from swissarmybench_powerbi.domain import report_swap as swap

MAX_TABLES: int = 200


class Files(Protocol):
    """The export's files (adapters/powerbi_files.py)."""

    def existing(self, folder: str) -> list[str]: ...

    def write(self, folder: str, files: Mapping[str, bytes]) -> list[str]: ...

    def remove(self, folder: str, paths: list[str]) -> None: ...

    def zipped(self, files: Mapping[str, bytes], top: str) -> bytes: ...

    def save_zip(self, folder: str, name: str, data: bytes) -> str: ...

    def has_program(self, path: str) -> bool: ...

    def open_file(self, path: str) -> str: ...


class ReportReader(Protocol):
    """A dropped report read (adapters/report_files.py): by its path, or its uploaded bytes and name."""

    def __call__(self, path: str | None = None, data: bytes | None = None, name: str = "") -> swap.Report: ...


MAX_UPLOAD_BYTES: int = 512 * 1024 * 1024


@dataclass
class ReportUse:
    """Another report's pages for the export: what the dialog shows, and what the export writes."""

    info: dict[str, Any]
    files: dict[str, bytes]
    measures: list[rules.Measure]


class Kept(Protocol):
    """A Power BI project's kept state (.sab/powerbi.json) and its data.ipynb's text; (None, None) without."""

    def __call__(self) -> tuple[Mapping[str, Any] | None, str | None]: ...


class RowWriter(Protocol):
    """Rows as a file's bytes (adapters/export.py write: Parquet here)."""

    def write(
        self,
        cursor: Any,
        sql: str,
        columns: tuple[Column, ...],
        options: ExportOptions,
        provenance: Any,
        row_count: int,
    ) -> bytes: ...


@dataclass
class TablePlan:
    name: str
    goes: bool = True
    source: str = ""  # where it is read from, in words
    why: str = ""  # why it cannot go as it is
    fix: str = ""  # its fix, in words
    needs_rows: bool = False  # Power Query cannot read its source: Include its rows offers it
    rows: bool = False  # its rows go (the tick)
    notes: list[str] = field(default_factory=list)
    local: list[str] = field(default_factory=list)  # Only works on your machine
    columns: tuple[tuple[str, str], ...] = ()  # (column, Power BI type)
    m: pq.MText | None = None
    view_sql: str | None = None  # its rows, when they go
    view_columns: tuple[Column, ...] = ()
    row_count: int = 0
    keys: set[str] = field(default_factory=set)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "goes": self.goes,
            "source": self.source,
            **({"why": self.why} if self.why else {}),
            **({"fix": self.fix} if self.fix else {}),
            "needs_rows": self.needs_rows,
            "rows": self.rows,
            "notes": self.notes,
            "local": self.local,
            "columns": len(self.columns),
            **({"row_count": self.row_count} if self.needs_rows else {}),
        }


def _settings(blade: Blade) -> dict[str, str]:
    """A connection's settings as their boxes' text, by plain name and by the code's own name (first wins)."""
    out: dict[str, str] = {}
    try:
        found = detect_settings(blade.code)
    except BladeCodeError:
        return out
    for s in found:
        text = s.text if s.text is not None else str(s.value)
        for key in (s.name, s.key):
            out.setdefault(key, text)
    return out


def _kind(blade: Blade) -> str | None:
    """The M kind of a connection (domain/power_query.py TEMPLATE_KINDS), None: Power Query has no reader."""
    tables = table_rules.tables_kind(
        blade.kind, blade.template, blade.dialect, blade.catalog_language, blade.tags, blade.code
    )
    if tables in ("dataverse", "sharepoint", "onelake", "datalake", "delta"):
        return pq.TEMPLATE_KINDS.get(tables)
    return pq.TEMPLATE_KINDS.get(str(blade.template or ""))


def _measures(kept: list[rules.Measure], brought: list[rules.Measure]) -> list[rules.Measure]:
    """The kept measures, then another report's brought ones not already there (by table and name)."""
    have = {(m.table.casefold(), m.name.casefold()) for m in kept}
    return kept + [m for m in brought if (m.table.casefold(), m.name.casefold()) not in have]


def _extension(path: str) -> str:
    return posixpath.splitext(path.replace("\\", "/").lower())[1]


class PowerBIExport:
    def __init__(
        self,
        ws: Workspace,
        models: Models,
        origins: Callable[[str], Origin],
        connection: Callable[[str], Blade],
        shareable: Callable[[], Mapping[str, str]],
        project: Callable[[], Mapping[str, Any] | None],
        used: Callable[[], set[str] | None],
        files: Files,
        writer: RowWriter,
        approvals: Approvals,
        read_report: ReportReader | None = None,
        kept: Kept | None = None,
    ) -> None:
        self.ws = ws
        self._models = models
        self._origins = origins
        self._connection = connection
        self._shareable = shareable
        self._project = project
        self._used = used
        self._files = files
        self._writer = writer
        self._approvals = approvals
        self._read_report = read_report
        # A Power BI project's .sab/powerbi.json and its data.ipynb's text (the round trip), set once built.
        self.kept = kept
        # A report dropped on the page (no path: the browser's drop), kept in memory until the next one.
        self._uploads: dict[str, tuple[str, bytes]] = {}

    # ===== which tables =====

    def _wanted(self, raw: Any) -> list[str]:
        if raw is None or raw == "":
            used = self._used()
            open_names = [i.name for i in self.ws.store.all()]
            names = sorted(used if used is not None else set(open_names) | self._models.model.tables())
            return names[:MAX_TABLES]
        if isinstance(raw, str):
            raw = [t for t in raw.split(",") if t.strip()]
        if not isinstance(raw, list) or not all(isinstance(t, str) for t in raw) or len(raw) > MAX_TABLES:
            raise ValueError(f"tables is a list of up to {MAX_TABLES} table names.")
        return list(dict.fromkeys(t.strip() for t in raw))

    @staticmethod
    def _rows_wanted(raw: Any) -> set[str] | bool:
        if raw is True or raw in ("true", "all"):
            return True
        if isinstance(raw, str):
            return {t for t in raw.split(",") if t.strip()}
        if isinstance(raw, list):
            return {str(t) for t in raw}
        return set()

    # ===== the plan =====

    def _source(self, info: DatasetInfo, origin: Origin) -> tuple[pq.MSource | None, str, str, list[str]]:
        """The table's source as M reads it (None: Power Query cannot), its words, why not, and its local
        notes."""
        if origin.kind in ("file", "dropped") and origin.path:
            kind = pq.FILE_KINDS.get(_extension(origin.path))
            label = posixpath.basename(origin.path.replace("\\", "/"))
            if kind is None:
                return None, label, f"Power Query reads no {_extension(origin.path) or 'such'} file here", []
            delimiter = "\t" if _extension(origin.path) == ".tsv" else ","
            source = pq.MSource(
                kind, path=refs.escape(origin.path), sheet=origin.sheet or "", delimiter=delimiter
            )
            return source, label, "", [portability.LOCAL_FILE.words()]
        if origin.kind == "connection" and origin.connection:
            name = origin.connection.split("/", 1)[0] if origin.dax else origin.connection
            if origin.dax:
                return (
                    None,
                    name,
                    "a Power BI dataset's table is read with DAX, which a semantic model's Power Que"
                    "ry does not do",
                    [],
                )
            try:
                blade = self._connection(name)
            except Exception:
                return None, name, f"its connection {name} is not in the library any more", []
            kind = _kind(blade)
            if kind is None:
                label = str(blade.template or blade.kind)
                return None, name, f"Power Query has no reader here for a {label} connection", []
            settings = _settings(blade)
            local = [f.words() for f in portability.check(blade.code, blade.template)]
            database, schema, table = origin.place or ("", "", "")
            if kind in ("csv", "excel", "parquet"):
                path = settings.get("path") or settings.get("file") or ""
                source = pq.MSource(kind, settings, path=path, sheet=table if kind == "excel" else "")
            elif kind in ("datalake", "onelake", "delta"):
                source = pq.MSource(kind, settings, path="/".join(p for p in (schema, table) if p))
            else:
                query = origin.sql if origin.place is None and origin.sql else ""
                source = pq.MSource(kind, settings, database, schema, table, query=query)
            return source, name, "", local
        said = {
            "python": "a Python session pushed it",
            "paste": "it was pasted",
            "query": "it is a query of other tables",
            "structure": "it came from a structure",
        }.get(origin.kind, "where it came from is not known")
        return None, origin.label() or origin.kind, f"Power Query cannot read it: {said}", []

    def _plan_table(self, cursor: SqlSession, name: str, rows: set[str] | bool) -> TablePlan:
        info = self.ws.store.get(name)
        plan = TablePlan(name)
        if info is None:
            plan.goes, plan.why, plan.fix = False, "it is not open", "Open it, then export again."
            return plan
        origin = self._origins(name)
        grid: Grid | None = self.ws.grids.first_for(name)
        steps = [s for s in (grid.steps if grid is not None else []) if not s.params.get("header")]
        on = [s for s in steps if s.enabled]
        compiled = self.ws.views.compile(cursor, info, steps, grid.settings) if grid is not None else None
        if compiled is not None and compiled.error is not None:
            compiled = None
            on = []
            plan.notes.append("a step in its grid cannot run: it goes without its steps")
        source, plan.source, why, plan.local = self._source(info, origin)
        plan.row_count = info.row_count
        columns = info.columns
        m: pq.MText | None = None
        if source is not None and on and grid is not None and compiled is not None:
            if source.kind in pq.DIALECTS:
                query = view_query(info, compiled, steps, grid.settings, self.ws.grammar.keywords)
                native = pq.native_steps(
                    query,
                    variable_name(info.name),
                    source.kind,
                    source.schema,
                    source.table,
                    source.query,
                    source.database,
                )
                if native.sql is not None:
                    source = pq.MSource(
                        source.kind,
                        source.settings,
                        source.database,
                        source.schema,
                        source.table,
                        query=native.sql,
                    )
                    columns = compiled.columns
                else:
                    plan.notes.append(f"goes without its steps: {native.why}")
            else:
                plan.notes.append("its steps are not carried: the file is read as it is")
        typed = [(c.name, rules.data_type(c.type)[0]) for c in columns]
        if source is not None:
            try:
                m = pq.m_for(source, typed)
            except pq.PowerQueryError as error:
                why = str(error)
                source = None
        if source is None:
            plan.needs_rows = True
            plan.why = why
            plan.fix = "Include its rows: they go as Parquet beside the model."
            if rows is True or (isinstance(rows, set) and name in rows):
                plan.rows = True
                if grid is not None and on:
                    positioned, made = self.ws.views.positioned_sql(cursor, info, steps, grid.settings)
                    plan.view_columns = made
                    names = ", ".join(quote(c.name) for c in made)
                    plan.view_sql = f"SELECT {names} FROM ({positioned}) ORDER BY {POS}"  # noqa: S608 (quoted names, its view)
                else:
                    plan.view_columns = info.columns
                    names = ", ".join(quote(c.name) for c in info.columns)
                    plan.view_sql = f"SELECT {names} FROM {info.table} ORDER BY rowid"  # noqa: S608 (quoted names)
                columns = plan.view_columns
                found = cursor.execute(f"SELECT count(*) FROM ({plan.view_sql})").fetchone()  # noqa: S608 (its own view)
                plan.row_count = int(found[0]) if found else 0
                m = pq.parquet_rows(f"{name}.parquet", rules.DATA_FOLDER_PARAMETER)
            else:
                plan.goes = False
        said = sorted({c.type for c in columns if rules.data_type(c.type)[1]})
        if said:
            plan.notes.append(f"{', '.join(said)} goes as text")
        plan.columns = tuple((c.name, rules.data_type(c.type)[0]) for c in columns)
        plan.m = m
        return plan

    async def _plans(self, names: list[str], rows: set[str] | bool) -> list[TablePlan]:
        def job() -> list[TablePlan]:
            cursor = self.ws.store.cursor()
            return [self._plan_table(cursor, n, rows) for n in names]

        return await self.ws.workers.run(BACKGROUND, job)

    def _keys(self, plans: list[TablePlan]) -> None:
        model = self._models.model
        by = {p.name: p for p in plans}
        for table, key in model.keys.items():
            if table in by:
                by[table].keys |= set(key)
        for r in model.relationships:
            if r.from_table in by:
                by[r.from_table].keys |= set(r.from_columns)
            if r.to_table in by:
                by[r.to_table].keys |= set(r.to_columns)

    def _name(self, raw: Any) -> str:
        if raw in (None, ""):
            project = self._project()
            base = str(project.get("name") or "") if project else ""
            cleaned = re.sub(r"[^A-Za-z0-9 _-]", "", base).strip()
            return cleaned[:64] if cleaned and rules.NAME.match(cleaned) else "Model"
        return rules.check_name(raw)

    def _where(self, name: str) -> str | None:
        project = self._project()
        folder = str(project.get("folder") or "") if project else ""
        if not folder:
            return None
        sep = "\\" if "\\" in folder and "/" not in folder else "/"
        return folder.rstrip("\\/") + sep + rules.FOLDER

    async def plan(self, body: Any) -> dict[str, Any]:
        body = body if isinstance(body, dict) else {}
        name = self._name(body.get("name"))
        plans = await self._plans(
            self._wanted(body.get("tables")), self._rows_wanted(body.get("include_rows"))
        )
        plans, _ = await self._round_trip(plans)
        answer = self._answer(name, plans)
        used = await self._report(body, plans)
        return answer | ({"report": used.info} if used is not None else {})

    # ===== the round trip: a Power BI project's own tables and measures back as the .pbix had them =====

    async def _round_trip(self, plans: list[TablePlan]) -> tuple[list[TablePlan], list[rules.Measure]]:
        """In a project made from a .pbix: each kept table in place of its two grids (_Source, _PowerBI),
        its M byte for byte or its changed notebook query as a native query, and the kept measures."""
        if self.kept is None:
            return plans, []
        try:
            state, notebook = await asyncio.to_thread(self.kept)
        except Exception:  # not a Power BI project: the export as before
            return plans, []
        if not state:
            return plans, []
        trips = import_rules.round_trip_tables(state, import_rules.notebook_queries(notebook))
        by = {p.name: p for p in plans}
        mine: set[str] = set()
        made: list[TablePlan] = []
        for t in trips:
            pair = import_rules.grid_names(t.name)
            mine |= {t.name, *pair}
            columns = t.columns
            if not columns:  # an older state: the Source grid's columns
                grid = next((by[g] for g in pair if g in by and by[g].columns), None)
                columns = grid.columns if grid is not None else ()
            target = posixpath.basename(str(state.get("target") or "").replace("\\", "/")) or "the .pbix"
            plan = TablePlan(t.name, source=target, columns=columns, m=t.m)
            plan.notes.append(t.words())
            if not columns:
                plan.goes, plan.why = False, "its columns are not known: open its Source grid"
            made.append(plan)
        rest = [p for p in plans if p.name not in mine]
        measures = [rules.Measure(**m) for m in import_rules.kept_measures(state)]
        return made + rest, measures

    # ===== another report's pages =====

    def upload(self, data: bytes, name: str) -> dict[str, Any]:
        """A report dropped on the page (the browser gives its bytes, not its path): kept in memory, by id."""
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("The file is too large to use.")
        if not name.lower().endswith((".pbix", ".pbit")):
            raise ValueError("Drop a .pbix or a .pbit (a .pbip: choose its file on this computer).")
        self._uploads.clear()
        key = f"u{len(data):x}{abs(hash(data[:4096])) % 10**8:x}"
        self._uploads[key] = (name, data)
        return {"upload": key, "file": name}

    async def _report(self, body: Mapping[str, Any], plans: list[TablePlan]) -> ReportUse | None:
        raw = body.get("report")
        if not raw or self._read_report is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError('report is {"path": a .pbix, .pbit or .pbip} or {"upload": its id}.')
        reader = self._read_report
        if raw.get("upload"):
            if raw["upload"] not in self._uploads:
                raise NotFound("Drop the report again: the app keeps only the last one dropped.")
            label, data = self._uploads[raw["upload"]]
            report = await asyncio.to_thread(reader, None, data, label)
        elif isinstance(raw.get("path"), str):
            label = posixpath.basename(raw["path"].replace("\\", "/"))
            report = await asyncio.to_thread(reader, raw["path"])
        else:
            raise ValueError('report is {"path": a .pbix, .pbit or .pbip} or {"upload": its id}.')
        ours = {p.name: [c for c, _ in p.columns] for p in plans if p.goes}
        fields = swap.fields_of(report.files)
        bring = bool(body.get("bring_measures", True))
        coming = [(m["table"], m["name"]) for m in (report.measures or [])] if bring else []
        tables = {t.casefold(): t for t in ours}
        names = [(tables[t.casefold()], m) for t, m in coming if t.casefold() in tables]
        mapping = body.get("mapping")
        if mapping is not None and not isinstance(mapping, dict):
            raise ValueError('mapping is {"Table.Field": "Table.Field" or null}.')
        mapped = swap.chosen(swap.propose(fields, ours, names), mapping)
        brought, said = swap.bring_measures(report.measures or [], mapped, ours) if bring else ([], [])
        files = swap.rewrite(report.files, mapped)
        info = {
            "file": label,
            "ours": {t: sorted(cs) for t, cs in sorted(ours.items())},
            "kind": report.source,
            "pages": "PBIR" if any(p.startswith("definition/") for p in files) else "legacy layout",
            "fields": [m.to_json() for m in mapped],
            "measures": [m.name for m in brought],
            "said": said + ([report.measures_note] if report.measures_note else []),
        }
        measures = [rules.Measure(m.table, m.name, m.expression, m.format, m.folder) for m in brought]
        return ReportUse(info, files, measures)

    def _answer(self, name: str, plans: list[TablePlan]) -> dict[str, Any]:
        self._keys(plans)
        going = {p.name: dict(p.columns) for p in plans if p.goes}
        planned = rules.plan_relationships(self._models.model.relationships, going)
        where = self._where(name)
        return {
            "name": name,
            "where": (where + ("\\" if "\\" in where else "/") + f"{name}.pbip") if where else None,
            "download": where is None,
            "tables": [p.to_json() for p in plans],
            "relationships": [p.to_json() for p in planned],
            "parameters": sorted({n for p in plans if p.goes and p.m for n in p.m.parameters}),
        }

    # ===== the export =====

    async def export(self, body: Any, who: str = "user") -> dict[str, Any]:
        """The export: written into the project's powerbi/ ({"written": paths, ...}), or a zip ({"zip": bytes,
        "file": name}) with no project open (the agent's zip is saved in the export folder)."""
        body = body if isinstance(body, dict) else {}
        name = self._name(body.get("name"))
        plans = await self._plans(
            self._wanted(body.get("tables")), self._rows_wanted(body.get("include_rows"))
        )
        plans, kept_measures = await self._round_trip(plans)
        with_rows = [p for p in plans if p.rows]
        if with_rows:
            await self._approvals.allowed(
                who,
                subject=name,
                action="export to Power BI with rows",
                detail="\n".join(
                    ["Export to Power BI with these tables' rows written beside the model:"]
                    + [f"  {p.name} ({p.row_count:,} rows)" for p in with_rows]
                ),
                otherwise="nothing was exported",
            )
        going = [p for p in plans if p.goes and p.m is not None]
        if not going:
            raise Refused("No table can go: tick Include its rows for a table Power Query cannot read.")
        answer = self._answer(name, plans)
        used = await self._report(body, plans)
        if used is not None:
            answer |= {"report": used.info}
        folder = self._where(name)
        shared = self._shareable()
        parameters: dict[str, str] = {}
        for p in going:
            for n in p.m.parameters if p.m is not None else ():
                parameters[n] = "" if n == rules.DATA_FOLDER_PARAMETER else shared.get(n, "")
        if any(rules.DATA_FOLDER_PARAMETER in (p.m.parameters if p.m else ()) for p in going):
            data = f"{folder}/{name}.SemanticModel/data/" if folder else ""
            parameters[rules.DATA_FOLDER_PARAMETER] = (
                data.replace("/", "\\") if folder and "\\" in folder else data
            )
        going_columns = {p.name: dict(p.columns) for p in going}
        planned = rules.plan_relationships(self._models.model.relationships, going_columns)
        tables = [
            rules.ExportTable(p.name, p.columns, p.m, frozenset(p.keys)) for p in going if p.m is not None
        ]
        package = rules.build(
            name,
            tables,
            planned,
            parameters,
            _measures(kept_measures, used.measures if used is not None else []),
            used.files if used is not None else None,
        )
        files = dict(package.files)
        if with_rows:
            files |= await self._rows(name, with_rows)
        files[".gitignore"] = rules.GITIGNORE.encode("utf-8")
        self.ws.audit.write(who, "export to power bi", name, tables=len(tables), rows=len(with_rows))
        if folder is None:
            archive = self._files.zipped(files, rules.FOLDER)
            file = f"{name}.zip"
            if who == "agent":
                saved = self._files.save_zip(str(self.ws.settings.export_dir), file, archive)
                return answer | {"saved": saved}
            return answer | {"zip": archive, "file": file}
        stale = rules.stale(name, self._files.existing(folder), package)
        stale = [s for s in stale if s not in files]
        written = self._files.write(folder, files)
        self._files.remove(folder, stale)
        return answer | {
            "folder": folder,
            "written": written,
            "removed": stale,
            "opens": self._files.has_program(answer["where"]),
        }

    async def _rows(self, name: str, plans: list[TablePlan]) -> dict[str, bytes]:
        options = ExportOptions(format="parquet", provenance=False)

        def job() -> dict[str, bytes]:
            out: dict[str, bytes] = {}
            for p in plans:
                if p.view_sql is None:
                    continue
                info = self.ws.store.get(p.name)
                cols = p.view_columns or (info.columns if info else ())
                data = self._writer.write(
                    self.ws.store.cursor(), p.view_sql, tuple(cols), options, None, p.row_count
                )
                out[f"{name}.SemanticModel/data/{p.name}.parquet"] = data
            return out

        return await self.ws.workers.run(BACKGROUND, job)

    # ===== open it =====

    def open(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Open in Power BI Desktop: the .pbip with its program, else its folder shown. The user's click
        only."""
        if who == "agent":
            raise Refused(
                "Open in Power BI Desktop starts a program on the user's screen: it is the user's click."
            )
        path = body.get("path") if isinstance(body, dict) else None
        folder = self._where("x")
        if not isinstance(path, str) or folder is None or not path.endswith(".pbip"):
            raise NotFound("Export the model into the open project first.")
        if not path.replace("\\", "/").startswith(folder.replace("\\", "/")):
            raise Refused("Only an export in the open project's powerbi folder opens from here.")
        try:
            return {"done": self._files.open_file(path), "path": path}
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
