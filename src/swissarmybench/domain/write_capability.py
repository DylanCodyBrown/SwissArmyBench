"""What each connection kind can write (docs/ideas.md, "Writing data"; the owner, 2026-11-17: "Write
blades should be geared towards our connection types. Most of our connections don't support it").

Every connection kind the app has (its form's template: server/blade_templates.py) is either
**writable** (with the operations its Write starters do, and how) or **read-only** (with the reason in
plain words). The Connections page's cards and the agent's connection description say it: "Writes:
<the starters>" or "Read-only: <why>", so nobody, the agent included, tries to write where it cannot.

A Write starter (the starter pack's Write family) names the kinds it writes to among its tags; the
tests hold the two together: every writable kind has a starter, every starter names a writable kind,
and a read-only kind has none. Standard library only; no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

WRITE_FAMILY: str = "Write"


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
    "powerbi": Writable(
        ("create", "append", "replace"),
        "push datasets only",
        "a model (semantic model) is read-only: write its source, then refresh it",
    ),
    "csv": Writable(("create", "replace"), "a new file, then put in its place"),
    "excel": Writable(("create", "replace", "append"), "a sheet written, the workbook's other sheets kept"),
    "parquet": Writable(("create", "replace"), "a new file, then put in its place"),
    "json": Writable(("create", "replace"), "a new file, then put in its place"),
    "folder": Writable(
        ("create", "replace", "append"), "files in the folder, partitioned Parquet among them"
    ),
}

_LOADERS = (
    "a warehouse takes rows through its own bulk loads (its stage or storage), not from a notebook's rows"
)
READ_ONLY: dict[str, str] = {
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
    "python": "a connection made of your own Python reads tables; an API added with Add API writes through "
    "the APIs page's Write rows with this call",
}


def capability(template: str | None, starters: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """A connection kind's writes: {"writable", "operations", "how", "note", "starters" (the Write
    starters' names for it), "reason" (read-only: why), "words"} ("Writes: ..." or "Read-only: ...")."""
    key = str(template or "")
    found = WRITABLE.get(key)
    if found is None:
        reason = READ_ONLY.get(key, "the app has no write starters for this kind of connection")
        return {"writable": False, "operations": [], "how": "", "note": "", "starters": [], "reason": reason,
                "words": f"Read-only: {reason}"}  # fmt: skip
    names = starters_for(key, starters)
    words = f"Writes: {', '.join(names)}" if names else f"Writes: {found.how}"
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
    """The Write starters that name this kind among their tags, by name."""
    return sorted(
        str(s["name"])
        for s in starters
        if s.get("family") == WRITE_FAMILY and template in [str(t) for t in s.get("tags") or ()]
    )


def kinds_named(tags: Sequence[str]) -> list[str]:
    """The connection kinds a Write starter's tags name (writable or not)."""
    known = set(WRITABLE) | set(READ_ONLY)
    return [t for t in tags if t in known]
