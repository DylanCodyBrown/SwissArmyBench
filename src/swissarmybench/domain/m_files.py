"""Power Query files on the Scripts page (the owner, 2026-11-27: "Wish I had it as a supported language and
those data sets can all be imported into one power query file that can be ran against the data set" / "Let's
make our own engine that supports creating tables from m code" / "Our own power query compiler basically" / "I
just want a run button and the power query runs").

A `.pq` or `.m` file is a script of the Scripts page. Run file (F5) runs every query of the file that is a
table, the query under the cursor (Ctrl+Enter) one of them, and each becomes the open table of its name, read
from its original sources, as a .sql file's run does. The compiler is duckpq (src/duckpq.py: its own library,
which knows nothing of this app); this module is the app's half of it:

- the file's rules (its endings, a plain file's one query named after the file, the query at the cursor, the
  open table a query makes);
- **the sources' mapping**: an M source call (Sql.Database("srv", "db") and its navigation) matched to a saved
  connection whose settings name the same server and database, and written as DuckDB SQL names its table
  (`[Warehouse].[dbo].[Orders]`); none matching is said in one sentence with Add connection, never guessed;
- **a dataset's queries as one file**: every table's partition M and the parameters of a .pbix (pbixray's
  frames), a .pbit (its DataModelSchema) or a .pbip (its TMDL, else its model.bim), as one section document.

Pure rules: the standard library and duckpq's compile half (no I/O).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import duckpq

SUFFIXES: tuple[str, ...] = (".pq", ".m")
SUFFIX: str = ".pq"
DEFAULT_QUERY: str = "Query"
MAX_TABLE: int = 64
_TABLE_PART = re.compile(r"[^A-Za-z0-9_-]+")
# How many times a run resolves what the compiler asks for before it gives up (a source's columns, then a
# pivot's values read from it, then ...).
MAX_ROUNDS: int = 8


def is_file(path: Any) -> bool:
    return isinstance(path, str) and path.lower().endswith(SUFFIXES)


def table_name(query: Any) -> str:
    """The open table a query makes: its name as a table's name allows (Sales Orders: Sales_Orders)."""
    cleaned = _TABLE_PART.sub("_", str(query or "")).strip("_")[:MAX_TABLE]
    return cleaned or DEFAULT_QUERY


def query_name(path: Any) -> str:
    """A plain `let ... in` file's one query: named after the file (orders_by_month.pq: orders_by_month)."""
    if not isinstance(path, str) or not path.strip():
        return DEFAULT_QUERY
    name = re.split(r"[\\/]", path)[-1]
    lowered = name.lower()
    stem = next((name[: -len(s)] for s in SUFFIXES if lowered.endswith(s)), name)
    return table_name(stem)


def file_name(table: str) -> str:
    return table_name(table) + SUFFIX


def query_at(compiled: duckpq.Compiled, line: int) -> duckpq.Query | None:
    """The query the cursor's line is in; between two, the one before it (else the first)."""
    queries = list(compiled.queries)
    if not queries:
        return None
    inside = [x for x in queries if x.line <= line <= x.end_line]
    if inside:
        return inside[0]
    before = [x for x in queries if x.end_line < line]
    return before[-1] if before else queries[0]


def starter(table: str | None = None, columns: Sequence[str] = ()) -> str:
    """A new Power Query file: a small `let ... in` over an open table (its first column kept not null), else
    over a table written out, so Run file works at once."""
    if table:
        source = duckpq.quoted_name(table)
        steps = [f"    Source = {source}"]
        last = "Source"
        if columns:
            column = columns[0]
            steps.append(f'    #"Filtered Rows" = Table.SelectRows(Source, each [{_field(column)}] <> null)')
            last = '#"Filtered Rows"'
        steps.append(f'    #"Kept First Rows" = Table.FirstN({last}, 100)')
        body = ",\n".join(steps) + '\nin\n    #"Kept First Rows"\n'
        head = (
            f"// Power Query (M). Run file (F5) builds the open table named after this file, from {table}.\n"
        )
        return head + "let\n" + body
    return (
        "// Power Query (M). Run file (F5) builds the open table named after this file.\n"
        "// A source may be an open table by its name, a file (Csv.Document(File.Contents(...))) or a saved\n"
        '// connection (Sql.Database("server", "database"){[Schema = "dbo", Item = "Orders"]}[Data]).\n'
        "let\n"
        '    Source = #table(type table [Region = text, Amount = number], {{"North", 120}, {"South", 80}}),\n'
        '    #"Filtered Rows" = Table.SelectRows(Source, each [Amount] > 100)\n'
        "in\n"
        '    #"Filtered Rows"\n'
    )


def _field(column: str) -> str:
    plain = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_. ]*", column) is not None and column == column.strip()
    return column if plain else '#"' + column.replace('"', '""') + '"'


# ===== the sources' mapping: an M source call to a saved connection =====


@dataclass(frozen=True)
class Connection:
    """A saved connection as a source is matched to it: its name, its starter's id (sqlserver, postgres...)
    and the settings its code names (server, database...), never a secret."""

    name: str
    template: str
    settings: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceKind:
    """One M source function: the connection starters it may be, which argument is its server and which its
    database (None: not an argument), the settings that hold them, and the words for Add connection."""

    templates: tuple[str, ...]
    label: str
    server: int | None = 0
    database: int | None = 1
    server_settings: tuple[str, ...] = ("server",)
    database_settings: tuple[str, ...] = ("database",)


# One entry a source function: adding one is one line.
SOURCES: dict[str, SourceKind] = {
    "Sql.Database": SourceKind(("sqlserver", "azuresql", "sybase"), "SQL Server"),
    "Sql.Databases": SourceKind(("sqlserver", "azuresql", "sybase"), "SQL Server", database=None),
    "PostgreSQL.Database": SourceKind(("postgres", "redshift"), "PostgreSQL"),
    "AmazonRedshift.Database": SourceKind(("redshift", "postgres"), "Amazon Redshift"),
    "MySQL.Database": SourceKind(("mysql", "mariadb"), "MySQL"),
    "Oracle.Database": SourceKind(
        ("oracle",), "Oracle", database=None, server_settings=("data source", "server")
    ),
    "Snowflake.Databases": SourceKind(
        ("snowflake",), "Snowflake", database=None, server_settings=("account", "server")
    ),
    "Databricks.Catalogs": SourceKind(("databricks",), "Databricks", database=None),
    "CommonDataService.Database": SourceKind(
        ("dataverse",), "Dataverse", database=None, server_settings=("address", "server")
    ),
}
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_DEFAULT_PORTS = (":1433", ",1433", ":5432", ":3306", ":1521", ":443")


def _host(value: Any) -> str:
    """A server as two spellings of it compare: no scheme, `tcp:` or default port, any case, and a Snowflake
    account without its domain."""
    text = _SCHEME.sub("", str(value or "").strip().casefold())
    text = text.removeprefix("tcp:").split("/")[0].rstrip(".")
    for port in _DEFAULT_PORTS:
        text = text.removesuffix(port)
    return text.removesuffix(".snowflakecomputing.com")


def _setting(connection: Connection, names: Iterable[str]) -> str:
    lowered = {str(k).casefold(): str(v) for k, v in connection.settings.items()}
    return next((lowered[n] for n in names if lowered.get(n)), "")


def _argument(source: duckpq.Source, at: int | None) -> str:
    if at is None or at >= len(source.arguments) or not isinstance(source.arguments[at], str):
        return ""
    return str(source.arguments[at])


def database_of(source: duckpq.Source) -> str:
    """The database a source names: its argument, else the navigation's Database step."""
    kind = SOURCES.get(source.function)
    named = _argument(source, kind.database) if kind is not None else ""
    if named:
        return named
    step = next((s for s in source.navigation if str(s.get("Kind") or "").casefold() == "database"), None)
    return str(step.get("Name") or "") if step is not None else ""


class NoConnection(ValueError):
    """No saved connection is this source: one sentence, and what Add connection would make."""

    def __init__(self, message: str, label: str, server: str, database: str) -> None:
        super().__init__(message)
        self.label = label
        self.server = server
        self.database = database


def connection_for(source: duckpq.Source, connections: Sequence[Connection]) -> Connection:
    """The saved connection a database source is: its starter one of the function's, its server the same and,
    when both name one, its database the same (two that match: the first by name). NoConnection otherwise;
    a function with no mapping is refused by its name."""
    kind = SOURCES.get(source.function)
    if kind is None:
        raise NoConnection(
            f"{source.function} has no connection kind here yet: nothing in Swiss Army Bench reads it.",
            source.function, "", "",
        )  # fmt: skip
    server, database = _argument(source, kind.server), database_of(source)
    found: list[Connection] = []
    for connection in sorted(connections, key=lambda c: c.name.casefold()):
        if connection.template not in kind.templates:
            continue
        if _host(_setting(connection, kind.server_settings)) != _host(server):
            continue
        theirs = _setting(connection, kind.database_settings)
        if database and theirs and theirs.casefold() != database.casefold():
            continue
        found.append(connection)
    if found:
        return found[0]
    what = f"{server} and {database}" if database else server
    raise NoConnection(
        f"No saved connection matches {source.function} for {what}: Add connection (a {kind.label} one for "
        f"that server{' and database' if database else ''}).",
        kind.label, server, database,
    )  # fmt: skip


def _bracket(part: str) -> str:
    if "[" in part or "]" in part or "\n" in part:
        raise ValueError(f"{part!r} cannot be a table's name in SQL here.")
    return f"[{part}]"


def table_parts(source: duckpq.Source, connection: Connection | None = None) -> list[str]:
    """The table a source's navigation picks, as the parts DuckDB SQL names after the connection: its schema
    and item, or each name picked (a database the connection itself is set to is left out)."""
    parts: list[str] = []
    for step in source.navigation:
        kind = str(step.get("Kind") or "").casefold()
        if "Item" in step:
            parts += [str(step[k]) for k in ("Schema", "Item") if step.get(k) not in (None, "")]
        elif step.get("Name") not in (None, ""):
            name = str(step["Name"])
            mine = _setting(connection, ("database", "catalog")) if connection is not None else ""
            if kind == "database" and (not mine or mine.casefold() == name.casefold()):
                continue  # the connection's own database: its tables are named without it
            parts.append(name)
    return parts


def reference(connection: Connection, source: duckpq.Source) -> str:
    """A database source's table as DuckDB SQL names it: [Warehouse].[dbo].[Orders]."""
    parts = table_parts(source, connection)
    if not parts:
        raise ValueError(
            f'Pick a table of {source.words()}: Source{{[Schema = "dbo", Item = "Orders"]}}[Data].'
        )
    return ".".join(_bracket(p) for p in [connection.name, *parts])


# ===== a dataset's queries as one file =====


@dataclass(frozen=True)
class DatasetQueries:
    """A Power BI dataset's queries: its name, its parameters and each table's M (name, expression), in the
    model's order; `skipped` the tables with no M (a calculated table's DAX) and why."""

    name: str
    parameters: tuple[tuple[str, str], ...] = ()
    tables: tuple[tuple[str, str], ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()


class ImportError_(ValueError):
    """A dataset file whose queries cannot be read, in one sentence."""


def _expression(value: Any) -> str:
    """An expression as a model's JSON holds it: one text, or its lines."""
    if isinstance(value, list):
        return "\n".join(str(line) for line in value)
    return str(value or "")


def from_schema(text: str, name: str) -> DatasetQueries:
    """A .pbit's DataModelSchema or a .pbip's model.bim (the tabular model as JSON): each table's M partition
    and the model's M expressions (its parameters and shared queries)."""
    try:
        model = json.loads(text)
    except ValueError:
        raise ImportError_(f"{name}'s model could not be read: it is not JSON.") from None
    model = model.get("model", model) if isinstance(model, dict) else {}
    parameters = [
        (str(e.get("name")), _expression(e.get("expression")))
        for e in model.get("expressions") or ()
        if isinstance(e, dict) and e.get("name") and str(e.get("kind") or "m").casefold() == "m"
    ]
    tables: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for table in model.get("tables") or ():
        if not isinstance(table, dict) or not table.get("name"):
            continue
        sources = [p.get("source") or {} for p in table.get("partitions") or () if isinstance(p, dict)]
        m = next((s for s in sources if str(s.get("type") or "").casefold() == "m"), None)
        if m is not None and _expression(m.get("expression")).strip():
            tables.append((str(table["name"]), _expression(m.get("expression"))))
        elif any(str(s.get("type") or "").casefold() == "calculated" for s in sources):
            skipped.append((str(table["name"]), "a calculated table (DAX)"))
        elif not str(table["name"]).startswith(("DateTableTemplate_", "LocalDateTable_")):
            skipped.append((str(table["name"]), "it has no Power Query"))
    return DatasetQueries(name, tuple(parameters), tuple(tables), tuple(skipped))


_TMDL_NAME = r"(?:'((?:[^']|'')+)'|([^\s=]+))"
_TMDL_TABLE = re.compile(rf"^table {_TMDL_NAME}\s*$")
_TMDL_PARTITION = re.compile(rf"^\tpartition {_TMDL_NAME}\s*=\s*(\w+)\s*$")
_TMDL_SOURCE = re.compile(r"^(\t+)source\s*=\s*(.*)$")
_TMDL_EXPRESSION = re.compile(rf"^expression {_TMDL_NAME}\s*=\s*(.*)$")


def _tmdl_name(found: re.Match[str], at: int = 1) -> str:
    return found.group(at).replace("''", "'") if found.group(at) is not None else found.group(at + 1)


def _tmdl_body(lines: Sequence[str], start: int, depth: int, first: str) -> str:
    """A TMDL expression: what follows its `=` on the line, then the lines indented two tabs past its
    property (a ``` fence kept out), with that indentation taken off."""
    indent = "\t" * (depth + 2)
    body = [first] if first.strip() and first.strip() != "```" else []
    for line in lines[start:]:
        if line.strip() == "```":
            continue
        if line.strip() and not line.startswith(indent):
            break
        body.append(line[len(indent) :] if line.startswith(indent) else "")
    return "\n".join(body).strip("\n")


def from_tmdl(files: Mapping[str, str], name: str) -> DatasetQueries:
    """A .pbip's TMDL (path -> text: definition/tables/<table>.tmdl, definition/expressions.tmdl): each
    table's `partition ... = m` source and each `expression`."""
    parameters: list[tuple[str, str]] = []
    tables: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for path in sorted(files):
        lines = files[path].replace("\r\n", "\n").split("\n")
        table, kind = "", ""
        for at, line in enumerate(lines):
            expression = _TMDL_EXPRESSION.match(line)
            if expression:
                parameters.append((_tmdl_name(expression), _tmdl_body(lines, at + 1, 0, expression.group(3))))
                continue
            named = _TMDL_TABLE.match(line)
            if named:
                table, kind = _tmdl_name(named), ""
                continue
            partition = _TMDL_PARTITION.match(line)
            if partition and table:
                kind = partition.group(3).casefold()
                if kind == "calculated":
                    skipped.append((table, "a calculated table (DAX)"))
                continue
            source = _TMDL_SOURCE.match(line)
            if source and table and kind == "m":
                tables.append((table, _tmdl_body(lines, at + 1, len(source.group(1)), source.group(2))))
                kind = ""
    return DatasetQueries(name, tuple(parameters), tuple(tables), tuple(skipped))


def from_frames(
    name: str, queries: Iterable[tuple[str, str]], parameters: Iterable[tuple[str, str]] = ()
) -> DatasetQueries:
    """A .pbix as pbixray reads it: its power_query rows (table, expression) and its m_parameters."""
    return DatasetQueries(
        name,
        tuple((str(n), str(e)) for n, e in parameters if str(n).strip() and str(e).strip()),
        tuple((str(n), str(e)) for n, e in queries if str(n).strip() and str(e).strip()),
    )


def _section_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
    return cleaned if cleaned and not cleaned[0].isdigit() else "Section1"


def document(queries: DatasetQueries, source_file: str = "") -> str:
    """The dataset's queries as ONE section document: its parameters first, then every table's M as a
    `shared` query of the table's name, as it was. Nothing is rewritten: what cannot run says so on Run."""
    if not queries.tables and not queries.parameters:
        raise ImportError_(f"{queries.name} has no Power Query to import (its tables are DAX or have none).")
    seen: set[str] = set()
    out = [
        f"// {queries.name}: the dataset's Power Query, every table one shared query"
        + (f" (imported from {source_file})." if source_file else "."),
        "// Run file (F5) runs them all against their original sources, each as the open table of its name;",
        "// Ctrl+Enter runs the one under the cursor.",
    ]
    out += [f"// Not imported: {table} ({why})." for table, why in queries.skipped]
    out += ["", f"section {_section_name(queries.name)};", ""]
    for name, expression in [*queries.parameters, *queries.tables]:
        if name in seen:
            continue
        seen.add(name)
        body = expression.strip().rstrip(";").rstrip()
        out += [f"shared {duckpq.quoted_name(name)} = {body};", ""]
    return "\n".join(out).rstrip("\n") + "\n"


# ===== an export: the file with the library beside it, so the M runs anywhere =====

EXPORT_FOLDER: str = "exports/powerquery"
LIBRARY_FILE: str = "duckpq.py"
RUN_FILE: str = "run.py"


def _run_script(stem: str, file: str, sources: Sequence[duckpq.Source]) -> str:
    """run.py: the file run with duckpq, each table written as Parquet; a branch per database source to
    fill in."""
    calls = [s for s in sources if s.kind == "call"]
    lines = [
        f'"""Runs {file} with duckpq (the file beside this one): every query that is a table, read from its',
        "sources, written as out/<table>.parquet. Nothing of Swiss Army Bench is needed: Python and duckdb",
        "(requirements.txt), on a laptop, a Linux container or an Azure Function App alike.",
        "",
        f"    python {RUN_FILE}",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from pathlib import Path",
        "from typing import Any",
        "",
        "import duckpq",
        "",
        "HERE = Path(__file__).resolve().parent",
        "",
        "",
        "def resolver(source: duckpq.Source) -> Any:",
        '    """Each source the file reads that is not a file: return something DuckDB reads (a path, a',
        '    relation, an Arrow table, a DataFrame). A file (CSV, Parquet, JSON, a sheet) needs nothing."""',
    ]
    for source in calls:
        lines += [
            f"    if source.function == {source.function!r} and source.arguments == "
            f"{tuple(source.arguments)!r}:",
            f"        # {source.words()}",
            '        raise NotImplementedError("Read this source here: return its rows.")',
        ]
    lines += [
        "    return None",
        "",
        "",
        "def main() -> None:",
        f'    text = (HERE / {file!r}).read_text(encoding="utf-8-sig")',
        f"    tables = duckpq.run(text, name={stem!r}, resolver=resolver, folder=str(HERE))",
        '    out = HERE / "out"',
        "    out.mkdir(exist_ok=True)",
        "    for name, table in tables.items():",
        '        table.write_parquet(str(out / f"{name}.parquet"))',
        '        print(f"{name}: {len(table.columns)} columns -> out/{name}.parquet")',
        "",
        "",
        'if __name__ == "__main__":',
        "    main()",
        "",
    ]
    return "\n".join(lines)


def export_files(path: str, text: str, sources: Sequence[duckpq.Source], library: str) -> dict[str, str]:
    """A Power Query file's export, by file name: the file as it is, duckpq.py as it is (the M runs with the
    library, not with this app), run.py, requirements.txt and a README that names each source to plug in."""
    file = re.split(r"[\\/]", path)[-1]
    stem = query_name(path)
    calls = [s for s in sources if s.kind == "call"]
    files = [s for s in sources if s.kind == "file"]
    readme = [
        f"# {file}",
        "",
        f"`python {RUN_FILE}` runs every query of `{file}` that is a table and writes each as",
        "`out/<table>.parquet`. It needs Python 3.12 or later and `duckdb` (`pip install -r",
        "requirements.txt`); `duckpq.py` beside it is the Power Query compiler (one file, not a Microsoft",
        "product).",
        "",
        "## Sources",
        "",
    ]
    readme += [
        f"- A file: `{s.words()}`. Put it where the path says, or change the path in `{file}`." for s in files
    ]
    readme += [f"- `{s.words()}`: answer for it in `{RUN_FILE}`'s `resolver`." for s in calls]
    if not sources:
        readme.append("None: the queries read nothing from outside the file.")
    return {
        file: text,
        LIBRARY_FILE: library,
        RUN_FILE: _run_script(stem, file, sources),
        "requirements.txt": "duckdb>=1.2\n",
        "README.md": "\n".join(readme) + "\n",
    }
