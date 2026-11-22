"""What each connection kind can write (docs/ideas.md, "Writing data"; the owner, 2026-11-17: "Write
blades should be geared towards our connection types. Most of our connections don't support it").

Every connection kind the app has is either **writable** (with the operations its Write starters do,
and how) or **read-only** (with the reason in plain words). A kind is the way the connection lists and
reads its tables (domain/connection_tables.py's TABLE_KINDS: a database, Power BI, Dataverse, your own
Python, an API, a file, a folder) and, for a database or a file, its form's template
(server/blade_templates.py): SQL Server writes, Snowflake is read-only here, a CSV file writes.
The Connections page's cards, the agent's connection description and context.md say it: "Writes: <the
starters>" or "Read-only: <why>", so nobody, the agent included, tries to write where it cannot.

A Write starter (the starter pack's Write family) names the kinds it writes to among its tags; the
tests hold the two together: every writable kind has a starter, every starter names a writable kind,
and a read-only kind has none. Standard library only; no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain.connection_tables import TABLE_KINDS

WRITE_FAMILY: str = "Write"
# sab.write's and the agent's connections_write modes: the adapter's (adapter.MODES; a test holds them).
WRITE_MODES: tuple[str, ...] = ("insert", "update", "merge", "delete", "truncate")
KEYED_MODES: tuple[str, ...] = ("update", "merge", "delete")


def write_request(body: Any) -> tuple[str, str, list[str], bool]:
    """A connections_write body checked: its table, mode, key and dry run; ValueError in one sentence."""
    if not isinstance(body, dict) or not isinstance(body.get("table"), str) or not body["table"].strip():
        raise ValueError('Send the table to write: {"table": "orders", "rows": [...], "mode": "insert"}.')
    mode = str(body.get("mode") or "insert")
    if mode not in WRITE_MODES:
        raise ValueError(f"mode is one of {', '.join(WRITE_MODES)}, not {mode!r}.")
    given = body.get("key")
    key = [given] if isinstance(given, str) else [str(k) for k in given or () if k]
    if mode in KEYED_MODES and not key:
        raise ValueError(f'A {mode} names the key its rows are matched by: "key": "order_id".')
    rows, table = body.get("rows"), body.get("from_table")
    if rows is not None and not (isinstance(rows, list) and all(isinstance(r, dict) for r in rows)):
        raise ValueError('rows is a list of records: [{"order_id": 1, "region": "North"}].')
    if rows is None and not isinstance(table, str) and mode != "truncate":
        raise ValueError("Send the rows (a list of records) or from_table (an open table's name).")
    return body["table"].strip(), mode, key, body.get("dry_run") is True


@dataclass(frozen=True)
class Writable:
    operations: tuple[str, ...]
    how: str  # in plain words: native SQL in one transaction, the Web API's change sets...
    note: str = ""  # a limit worth saying beside the starters


_SQL = ("append", "create", "replace", "upsert", "delete")

WRITABLE: dict[str, Writable] = {
    "sqlserver": Writable(_SQL, "T-SQL in one transaction: staged, MERGE, retried on passing errors"),
    "azuresql": Writable(_SQL, "T-SQL in one transaction: staged, MERGE, retried on Azure's passing errors"),
    "postgres": Writable(_SQL, "SQL in one transaction (COPY, ON CONFLICT)"),
    "mysql": Writable(_SQL, "SQL in one transaction (ON DUPLICATE KEY UPDATE)"),
    "mariadb": Writable(_SQL, "SQL in one transaction (ON DUPLICATE KEY UPDATE)"),
    "oracle": Writable(_SQL, "SQL in one transaction (MERGE)"),
    "sqlite": Writable(_SQL, "SQL in one transaction (the file opened again to write)"),
    "trino": Writable(
        _SQL,
        "SQL, a statement at a time",
        "depends on the catalog's connector: Iceberg, Delta Lake and Hive write; a connector that cannot is "
        "refused in Trino's own words",
    ),
    "odbc": Writable(("append", "create", "replace", "delete"), "SQL, where the source's driver writes"),
    "dataverse": Writable(
        ("create", "update", "upsert", "delete"),
        "the Web API's $batch change sets (its SQL endpoint is read-only)",
    ),
    "csv": Writable(("create", "replace"), "a new file, then put in its place"),
    "excel": Writable(("create", "replace", "append"), "a sheet written, the workbook's other sheets kept"),
    "parquet": Writable(("create", "replace"), "a new file, then put in its place"),
    "json": Writable(("create", "replace"), "a new file, then put in its place"),
    "folder": Writable(
        ("create", "replace", "append"), "files in the folder, partitioned Parquet among them"
    ),
    # Lakes and SharePoint (domain/lakes.py): the connection's own code writes (domain/lake_code.py
    # LakeWrites, domain/sharepoint.py SharePointLists).
    "delta": Writable(
        ("append", "replace", "upsert", "delete", "optimize", "vacuum"),
        "a Delta commit a write (the deltalake package): merge by keys, delete by a condition",
        "vacuum keeps 7 days unless the cell says otherwise",
    ),
    "onelake": Writable(
        ("append", "replace", "upsert", "delete", "create"),
        "a lakehouse's Delta tables (the deltalake package) and its Files/ (Parquet, CSV)",
        "a warehouse is written with T-SQL in its own tools",
    ),
    "datalake": Writable(
        ("append", "replace", "upsert", "delete", "create"),
        "its Delta tables (the deltalake package), and Parquet or CSV files through the ADLS Gen2 API",
    ),
    "sharepoint": Writable(
        ("create", "update", "delete"),
        "Microsoft Graph's $batch, retried on 429 (a list has no transaction)",
    ),
}

_LOADERS = (
    "a warehouse takes rows through its own bulk loads (its stage or storage), not from a notebook's rows"
)
READ_ONLY: dict[str, str] = {
    # The project's sandbox writes only by itself (a local sandbox API's mock clients, its grid's edits).
    "sandbox": "the sandbox is written by its local sandbox API and its grid's edits, not a Write starter",
    "powerbi": "a semantic model takes no rows: write its source, then refresh it (Power BI refresh dataset)",
    "duckdb": "the connection opens the file read-only: DuckDB lets one program write a file at a time",
    "snowflake": _LOADERS,
    "bigquery": _LOADERS,
    "redshift": _LOADERS,
    "databricks": _LOADERS,
    "db2": "the app reads Db2; it has no write starters for it",
    "teradata": "the app reads Teradata; it has no write starters for it",
    "clickhouse": "the app reads ClickHouse; it has no write starters for it",
    "saphana": "the app reads SAP HANA; it has no write starters for it",
    "vertica": "the app reads Vertica; it has no write starters for it",
    "sybase": "the app reads SAP ASE; it has no write starters for it",
    "access": "the app reads Access files; it has no write starters for it",
    "python": "a connection made of your own Python reads tables: write in a cell of your own code",
    "api": "an API writes through the APIs page's Write rows with this call",
    "sharepoint_docs": "its tables are its documents: upload a file with the SharePoint upload file starter",
}
# The tables kinds whose writes are their template's (a database's engine, a file's format); every other
# tables kind is one kind here. dataverse_web is the same Dataverse (its Web API writes either way).
BY_TEMPLATE: frozenset[str] = frozenset({"database", "file"})
_SAME: dict[str, str] = {"dataverse_web": "dataverse"}


def kind_of(tables_kind: str | None, template: str | None) -> str:
    """The key a connection's writes are found by: its template for a database or a file (and when the
    tables kind is not known, as for a form), else its tables kind."""
    if tables_kind is None or tables_kind in BY_TEMPLATE:
        return str(template or "")
    return _SAME.get(tables_kind, tables_kind)


def tables_kinds_covered() -> dict[str, str]:
    """Each of connection_tables' kinds and how its writes are decided: "template", "writable",
    "read-only", or "" (not decided: the tests refuse that)."""
    out: dict[str, str] = {}
    for kind in TABLE_KINDS:
        key = kind_of(kind, None)
        if kind in BY_TEMPLATE:
            out[kind] = "template"
        else:
            out[kind] = "writable" if key in WRITABLE else "read-only" if key in READ_ONLY else ""
    return out


def capability(
    template: str | None, starters: Iterable[Mapping[str, Any]] = (), tables_kind: str | None = None
) -> dict[str, Any]:
    """A connection kind's writes: {"writable", "operations", "how", "note", "starters" (the Write
    starters' names for it), "reason" (read-only: why), "words"} ("Writes: ..." or "Read-only: ...").
    `tables_kind` is connection_tables.tables_kind's answer (None for a form: its template decides)."""
    key = kind_of(tables_kind, template)
    found = WRITABLE.get(key)
    if found is None:
        reason = READ_ONLY.get(key, "the app has no write starters for this kind of connection")
        return {"writable": False, "operations": [], "how": "", "note": "", "starters": [], "reason": reason,
                "words": f"Read-only: {reason}"}  # fmt: skip
    names = starters_for(key, starters)
    words = f"Writes: {', '.join(found.operations)}"
    if found.note:
        words += f" ({found.note})"
    return {
        "writable": True,
        "operations": list(found.operations),
        "how": found.how,
        "note": found.note,
        "starters": names,
        "reason": "",
        "words": words,
    }


def starters_for(template: str, starters: Iterable[Mapping[str, Any]]) -> list[str]:
    """The Write starters that name this kind among their tags, by name: the calls a cell takes (each
    runs one of the family's functions, `Write to SQLite`, which are not listed here)."""
    return sorted(
        str(s["name"])
        for s in starters
        if s.get("family") == WRITE_FAMILY
        and s.get("kind", "snippet") == "snippet"
        and template in [str(t) for t in s.get("tags") or ()]
    )


def kinds_named(tags: Sequence[str]) -> list[str]:
    """The connection kinds a Write starter's tags name (writable or not)."""
    known = set(WRITABLE) | set(READ_ONLY)
    return [t for t in tags if t in known]
