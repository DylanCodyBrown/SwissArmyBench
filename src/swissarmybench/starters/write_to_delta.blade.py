# /// swissarmybench-blade
# format = 1
# name = "Write to a Delta table"
# kind = "other"
# description = "Write rows to a Delta table of a lake (dry run first; writes on the user's word)"
# tags = ["write", "delta", "onelake", "datalake"]
# family = "Write"
# variable = "write_delta"
# ///
"""A Delta table of a lake connection (Delta Lake, OneLake, Azure Data Lake Storage), by `mode`: append,
overwrite, merge (by keys: a row whose keys match is updated, any other inserted), delete (the rows a
condition matches), optimize (small files compacted) and vacuum (files no version within the retention
period reads, deleted).

    write_delta = sab.blade("Write to a Delta table")  # the project's functions.py will hold it
    write_delta("Lake", "sales/orders", orders, mode="merge", keys=["order_id"])  # a dry run

Dry run first: dry_run=True (the default) only says what it would do and changes nothing (its counts are
read from the table as it is); dry_run=False writes. An agent sets dry_run=False only after the user said
to write, in their own words, in this conversation. It signs in through the connection's own sign-in
(sab.connection): no secret here. Returns the write's report.

Each write is one Delta commit (all of it or none of it), made by the deltalake package. A vacuum keeps
at least 168 hours (7 days): less is refused unless allow_shorter=True is set here, in the cell.
"""

from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)

from swissarmybench.client.writes import Write, WriteError, live

MODES = ("append", "overwrite", "merge", "delete", "optimize", "vacuum")


def _arrow(given: Any) -> Any:
    """The staged rows as an Arrow table (DuckDB 2's to_arrow_table, 1's fetch_arrow_table)."""
    found = given.db.sql("FROM sab_rows")
    return (getattr(found, "to_arrow_table", None) or found.fetch_arrow_table)()


def write_delta(
    connection: str,
    table: str,
    rows: Any = None,
    mode: str = "append",
    keys: list[str] | None = None,
    condition: str = "",
    retention_hours: int = 168,
    allow_shorter: bool = False,
    dry_run: bool = True,
) -> Write:
    """The rows written to the Delta table `table` (its folders and name below the connection's place:
    sales/orders) of the lake connection named `connection`.

    mode: append, overwrite, merge (keys), delete (condition), optimize, vacuum (retention_hours).
    rows: a DataFrame (pandas, polars, Arrow) or a DuckDB relation (append, overwrite, merge).
    """
    if mode not in MODES:
        raise WriteError(f"mode is one of {', '.join(MODES)}, not {mode!r}.")
    name, conn = live(connection)
    if not hasattr(conn, "write_delta"):
        raise WriteError(f"{name} is not a lake connection (Delta Lake, OneLake, Azure Data Lake Storage).")
    w = Write(name, table, mode, rows if mode in ("append", "overwrite", "merge") else None, dry_run=dry_run)
    path = conn.target_path(table)
    if mode in ("append", "overwrite", "merge"):
        given = w.need_rows()
        data = _arrow(given)
        if mode == "merge":
            if not keys:
                raise WriteError('A merge finds each row by its key columns: keys=["order_id"].')
            given.check_keys(keys, unique=True)
            matched, _ = conn.count_matches(table, data, keys)
            w.would(
                f"MERGE INTO {path} ON {' AND '.join(keys)}: update when matched, insert when not",
                updated=matched,
                inserted=given.count - matched,
            )
        else:
            w.would(f"{mode.upper()} {given.count:,} rows to {path}", written=given.count)
        if not dry_run:
            done = conn.write_delta(path, data, mode, keys or ())
            w.done(**done)
    elif mode == "delete":
        if not condition.strip():
            raise WriteError("A delete names its rows: condition=\"region = 'West'\".")
        w.would(f"DELETE FROM {path} WHERE {condition}", deleted=conn.count_where(table, condition))
        if not dry_run:
            w.done(**conn.delete_delta(path, condition))
    elif mode == "optimize":
        plan = conn.optimize_delta(path, dry_run=True)
        w.would(f"OPTIMIZE {path}: {plan['small']:,} of {plan['files']:,} files are small and compacted")
        if not dry_run:
            done = conn.optimize_delta(path, dry_run=False)
            w.fact("Files", f"{done['added']:,} added, {done['removed']:,} removed")
            w.done()
    else:
        plan = conn.vacuum_delta(path, retention_hours, dry_run=True, allow_shorter=allow_shorter)
        w.would(
            f"VACUUM {path} RETAIN {plan['retention_hours']} HOURS: {plan['files']:,} files no version "
            "within it reads"
        )
        if not dry_run:
            done = conn.vacuum_delta(path, retention_hours, dry_run=False, allow_shorter=allow_shorter)
            w.fact("Files", f"{done['files']:,} deleted")
            w.done()
    return w
