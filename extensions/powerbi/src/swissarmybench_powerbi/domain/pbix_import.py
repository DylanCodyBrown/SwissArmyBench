"""A .pbix imported as a Power BI project (the owner, 2026-11-19: "the heart of it"): what pbixray read of the
file (domain/pbix_file.py) planned into a project ready to work. Pure rules; the service does the work.

  [SOURCES]   each partition's Power Query read back (domain/power_query.py read_source); one library
              connection per distinct source (kind, server, database), an existing one with the same server
              and
              database reused; Power Query parameters as `${NAME}` variables (plain, non-secret values)
  [DATASET]   the published dataset: a thin report's own; else one named like the file in the workspaces the
              Power BI workspace connections reach; several or none: asked, never guessed
  [TABLES]    per model table a Source read (its back-end connection's table or native query; its Power Query
              steps after the navigation said, not translated) and an In Power BI read (the dataset)
  [NOTEBOOK]  data.ipynb: per table a `%%sql <connection>` cell and a `%%dax <dataset connection>/<dataset>`
  cell
  [KEEP]      .sab/powerbi.json: the measures, display folders, formats and each table's original M (part 1's
              export writes an untouched table's M back byte for byte)
  [FINISH]    "To finish setting up" (H): what the import could not resolve, one row each with its fix; the
              import always finishes
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import variable_refs as refs
from swissarmybench_powerbi.domain import pbix_file as pf
from swissarmybench_powerbi.domain import power_query as pq

FORMAT = 1
STATE_PATH = ".sab/powerbi.json"
# Each M kind -> the connection template made for it (server/blade_templates.py ids).
TEMPLATES: dict[str, str] = {
    "sqlserver": "sqlserver",
    "postgres": "postgres",
    "mysql": "mysql",
    "snowflake": "snowflake",
    "databricks": "databricks",
    "oracle": "oracle",
    "dataverse": "dataverse",
    "sharepoint": "sharepoint",
    "datalake": "datalake",
    "onelake": "onelake",
    "delta": "delta",
}
# The kinds whose sign-in an app registration can be (G): Microsoft's own.
MICROSOFT_KINDS = frozenset({"sqlserver", "dataverse", "sharepoint", "datalake", "onelake", "delta"})
SOURCES = ("published", "local", "file")


class ImportError_(ValueError):
    """The import cannot go ahead as asked; the message says why."""


@dataclass(frozen=True)
class SourceConnection:
    """One back-end connection the import names: reused (an existing one) or made."""

    name: str
    kind: str  # the M kind
    settings: Mapping[str, str]
    database: str = ""
    reused: bool = False

    @property
    def key(self) -> tuple[str, str, str]:
        return source_key(self.kind, self.settings, self.database)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "label": pq.KINDS[self.kind].label if self.kind in pq.KINDS else self.kind,
            "settings": dict(self.settings),
            "database": self.database,
            "reused": self.reused,
        }


@dataclass(frozen=True)
class TablePlan:
    name: str
    connection: str = ""  # the back-end connection ("" : none)
    schema: str = ""
    table: str = ""
    query: str = ""  # a native query, in the source's own SQL
    steps_after: bool = False  # its Power Query does more after the navigation (not translated)
    why: str = ""  # why it has no Source read
    m: str = ""
    calculated: bool = False

    def source_sql(self) -> str:
        """The Source cell's SQL: the native query, or the table's SELECT."""
        if self.query:
            return self.query
        if not self.table:
            return ""
        name = ".".join(_quoted(p) for p in (self.schema, self.table) if p)
        return f"SELECT * FROM {name}"  # noqa: S608 (a table name, quoted)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "connection": self.connection}
        for key in ("schema", "table", "query", "why"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        if self.steps_after:
            out["steps_after"] = "Its Power Query steps after the source are not translated (its M is kept)."
        if self.calculated:
            out["calculated"] = True
        return out


def grid_names(table: str) -> tuple[str, str]:
    """A model table's two grids, side by side: (Source, In Power BI): Customer_Source, Customer_PowerBI."""
    bare = re.sub(r"[^A-Za-z0-9_-]+", "_", table.strip()).strip("_")[:48] or "table"
    return f"{bare}_Source", f"{bare}_PowerBI"


def _quoted(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else '"' + name.replace('"', '""') + '"'


def source_key(kind: str, settings: Mapping[str, str], database: str = "") -> tuple[str, str, str]:
    """Two sources are one connection when their kind, server and database match (any case)."""
    server = next(
        (
            settings[k]
            for k in ("server", "account", "address", "site_url", "root", "workspace")
            if settings.get(k)
        ),
        "",
    )
    db = database or settings.get("database", "") or settings.get("container", "") or settings.get("item", "")
    return (TEMPLATES.get(kind, kind), server.strip().casefold().rstrip("/"), db.strip().casefold())


def connection_name(kind: str, settings: Mapping[str, str], database: str, taken: Iterable[str]) -> str:
    """A new connection's name: its database (else its server's first part), unique among `taken`."""
    server = next(
        (settings[k] for k in ("server", "account", "address", "site_url", "root") if settings.get(k)), ""
    )
    host = re.sub(r"^[a-z]+://", "", server, flags=re.IGNORECASE).split("/")[0].split(".")[0]
    base = (
        database
        or settings.get("database", "")
        or host
        or (pq.KINDS[kind].label if kind in pq.KINDS else kind)
    )
    base = refs.names(base)[0] if refs.holds(base) and refs.names(base) else base
    base = (base[:1].upper() + base[1:]) if base else "Source"
    used = {t.casefold() for t in taken}
    name, n = base, 2
    while name.casefold() in used:
        name, n = f"{base} {n}", n + 1
    return name


@dataclass
class ImportPlan:
    project: str
    model: pf.PbixModel
    connections: list[SourceConnection] = field(default_factory=list)
    tables: list[TablePlan] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)  # Power Query parameter -> plain value
    dataset: dict[str, str] | None = None  # {"connection", "dataset"} found
    dataset_choices: list[dict[str, str]] = field(default_factory=list)  # several: asked
    unreadable: list[dict[str, str]] = field(default_factory=list)  # {"table", "why"}

    def to_json(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "file": self.model.name,
            "thin": self.model.thin_dataset,
            "connections": [c.to_json() for c in self.connections],
            "variables": [{"name": k, "value": v} for k, v in sorted(self.variables.items())],
            "tables": [t.to_json() for t in self.tables],
            "relationships": [r.to_json() for r in self.model.relationships],
            "measures": [m.to_json() for m in self.model.measures],
            "dataset": self.dataset,
            "dataset_choices": self.dataset_choices,
            "unreadable": self.unreadable,
        }


def plan(
    model: pf.PbixModel,
    project: str,
    existing: Sequence[Mapping[str, Any]],
    datasets: Sequence[Mapping[str, str]],
    picked: Mapping[str, Any] | None = None,
) -> ImportPlan:
    """The import's plan. `existing`: the library's connections ({name, kind (M kind), settings, database});
    `datasets`: the published datasets the workspace connections reach ({connection, dataset}); `picked`: the
    user's choice of dataset ({connection, dataset}) or {"none": true} (it isn't published)."""
    out = ImportPlan(project, model, variables=dict(model.parameters))
    known = {
        source_key(str(e["kind"]), e.get("settings", {}), str(e.get("database", ""))): str(e["name"])
        for e in existing
    }
    taken = [str(e["name"]) for e in existing]
    made: dict[tuple[str, str, str], SourceConnection] = {}
    for table in pf.listed(model.tables):
        if table.calculated and not table.m:
            out.tables.append(
                TablePlan(table.name, calculated=True, why="a calculated table (DAX): no source to read")
            )
            continue
        read = pq.read_source(table.m, model.parameters)
        source = read.source
        if source is None or source.kind not in TEMPLATES:
            why = read.why or f"its {source.kind if source else 'source'} has no connection kind here"
            out.tables.append(TablePlan(table.name, why=why, m=table.m))
            out.unreadable.append({"table": table.name, "why": why, "m": table.m})
            continue
        key = source_key(source.kind, source.settings, source.database)
        connection = made.get(key)
        if connection is None:
            if key in known:
                connection = SourceConnection(
                    known[key], source.kind, dict(source.settings), source.database, True
                )
            else:
                name = connection_name(source.kind, source.settings, source.database, taken)
                taken.append(name)
                connection = SourceConnection(name, source.kind, dict(source.settings), source.database)
            made[key] = connection
            out.connections.append(connection)
        out.tables.append(
            TablePlan(
                table.name,
                connection.name,
                source.schema,
                source.table or source.path,
                source.query,
                read.steps_after,
                m=table.m,
            )
        )
    out.dataset, out.dataset_choices = find_dataset(model, datasets, picked)
    return out


def find_dataset(
    model: pf.PbixModel, datasets: Sequence[Mapping[str, str]], picked: Mapping[str, Any] | None
) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
    """The published dataset: the user's pick; a thin report's own; else the one named like the file. Several
    or none: (None, the choices) — asked, never guessed."""
    if picked and picked.get("none"):
        return None, []
    if picked and picked.get("connection") and picked.get("dataset"):
        return {"connection": str(picked["connection"]), "dataset": str(picked["dataset"])}, []
    wanted = (model.thin_dataset or model.name).casefold()
    found = [dict(d) for d in datasets if str(d.get("dataset", "")).casefold() == wanted]
    if len(found) == 1:
        return {"connection": found[0]["connection"], "dataset": found[0]["dataset"]}, []
    return None, found or [dict(d) for d in datasets]


# ===== the data notebook =====


def notebook_cells(plan_: ImportPlan, dataset_connection: str | None) -> list[dict[str, Any]]:
    """data.ipynb's cells: per table its `%%sql` Source cell and its `%%dax` cell, each named after it."""
    cells: list[dict[str, Any]] = [
        {
            "kind": "markdown",
            "source": f"# {plan_.project}\nEach table read from its source, and as Power BI has it.",
        }
    ]
    dataset = plan_.dataset["dataset"] if plan_.dataset else ""
    for t in plan_.tables:
        sql = t.source_sql()
        if t.connection and sql:
            cells.append(
                {"kind": "code", "source": f"%%sql {t.connection}\n{sql}", "name": f"{t.name} source"}
            )
        if dataset_connection and dataset:
            dax = "EVALUATE " + "'" + t.name.replace("'", "''") + "'"
            cells.append(
                {
                    "kind": "code",
                    "source": f"%%dax {dataset_connection}/{dataset}\n{dax}",
                    "name": f"{t.name} in Power BI",
                }
            )
    return cells


def notebook_json(cells: Sequence[Mapping[str, Any]]) -> str:
    """The cells as an .ipynb (nbformat 4), each code cell's name in its metadata."""
    out: list[dict[str, Any]] = []
    for n, cell in enumerate(cells, 1):
        source = str(cell["source"])
        lines = source.splitlines(keepends=True)
        meta: dict[str, Any] = {
            "swissarmybench": {"number": n} | ({"name": cell["name"]} if cell.get("name") else {})
        }
        if cell["kind"] == "markdown":
            out.append({"cell_type": "markdown", "metadata": meta, "source": lines})
        else:
            out.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": meta,
                    "outputs": [],
                    "source": lines,
                }
            )
    book = {
        "cells": out,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(book, indent=1, ensure_ascii=False) + "\n"


def changed_query(source: str) -> str | None:
    """A Source cell's SQL (its text after the %%sql line), for the round trip."""
    lines = source.splitlines()
    return "\n".join(lines[1:]).strip() if lines and lines[0].startswith("%%sql") else None


# ===== .sab/powerbi.json: what goes back to Power BI, and the project's Power BI settings =====


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def state_json(
    plan_: ImportPlan, target: str, dataset_connection: str, file_connection: str
) -> dict[str, Any]:
    """The kept state: the target, the connections named, each table's original M (and its Source SQL's
    digest, so a changed notebook query is told), measures with folders and formats, relationships."""
    return {
        "format": FORMAT,
        "target": target,
        "dataset_connection": dataset_connection,
        "file_connection": file_connection,
        "dataset": plan_.dataset,
        "source": "published" if plan_.dataset else "file",
        "registration": None,
        "parameters": dict(sorted(plan_.variables.items())),
        "tables": [
            {
                "name": t.name,
                "connection": t.connection,
                "m": t.m,
                "sql": t.source_sql(),
                "sql_digest": digest(t.source_sql()),
            }
            | ({"why": t.why} if t.why else {})
            for t in plan_.tables
        ],
        "measures": [m.to_json() for m in plan_.model.measures],
        "relationships": [r.to_json() for r in plan_.model.relationships],
        "unreadable": [{"table": u["table"], "why": u["why"]} for u in plan_.unreadable],
    }


def write_state(state: Mapping[str, Any]) -> str:
    """Byte-stable: sorted keys, two-space indent, one newline."""
    return json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def round_trip_m(
    kept: Mapping[str, Any], current_sql: str | None, kind_dialect_ok: bool = True
) -> tuple[str, str]:
    """A table's M for part 1's export: ("kept", its original M byte for byte) while its notebook query is
    untouched; ("query", the new native query) once it changed; ("none", "") when nothing was kept."""
    m = str(kept.get("m") or "")
    if current_sql is None or digest(current_sql) == kept.get("sql_digest"):
        return ("kept", m) if m else ("none", "")
    return "query", current_sql


def with_native_query(m: str, query: str) -> str:
    """The original M with its source's navigation replaced by the native query (Sql.Database's Query option,
    else Value.NativeQuery on the source): the connector call and its arguments kept."""
    read = pq.read_source(m)
    if read.source is None:
        return m
    rebuilt = pq.m_for(pq.MSource(read.source.kind, read.source.settings, read.source.database, query=query))
    return rebuilt.text


# ===== To finish setting up (H) =====


def to_finish(
    state: Mapping[str, Any],
    registrations: Sequence[str],
    needs: Mapping[str, str],
) -> list[dict[str, Any]]:
    """The rows still to do, each {id, words, fix: {label, action, ...}}; gone when done. `needs`: a back-end
    connection -> what it lacks on this computer ("a password", "a sign-in")."""
    rows: list[dict[str, Any]] = []
    uses_microsoft = state.get("uses_microsoft", True)
    if state.get("registration") is None and not state.get("registration_none") and uses_microsoft:
        rows.append(
            {
                "id": "registration",
                "words": "Choose the app registration its Microsoft sources sign in with.",
                "fix": {"label": "Choose", "action": "registration", "choices": list(registrations)},
            }
        )
    if not state.get("dataset") and not state.get("not_published"):
        rows.append(
            {
                "id": "dataset",
                "words": "Find the published dataset.",
                "fix": {"label": "Find it", "action": "dataset"},
                "other": {"label": "It isn't published", "action": "not_published"},
            }
        )
    for connection, what in sorted(needs.items()):
        rows.append(
            {
                "id": f"connection:{connection}",
                "words": f"{connection} needs {what} on this computer.",
                "fix": {"label": "Set up this computer", "action": "setup", "connection": connection},
            }
        )
    for item in state.get("unreadable", []):
        rows.append(
            {
                "id": f"unreadable:{item['table']}",
                "words": f"{item['table']}: {item['why']}. Its Power Query is kept; no Source grid.",
                "fix": {"label": "Show its Power Query", "action": "show_m", "table": item["table"]},
            }
        )
    return rows
