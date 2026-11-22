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

Each write is one Delta commit (all of it or none of it), made by the deltalake package. append,
overwrite and merge are the adapter's write (sab_adapter.write on the connection: insert, truncate, merge,
Plans/adapter.plan.md); delete by a condition, optimize and vacuum are the lake's own calls. A vacuum keeps
at least 168 hours (7 days): less is refused unless allow_shorter=True is set here, in the cell.
"""

from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)

from swissarmybench.adapters import sab_adapter
from swissarmybench.client.writes import Write, WriteError, by_adapter, live

MODES = ("append", "overwrite", "merge", "delete", "optimize", "vacuum")
_ADAPTER = {"append": "insert", "overwrite": "truncate", "merge": "merge"}  # the adapter's modes


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
    w = Write(name, table, mode, rows if mode in _ADAPTER else None, dry_run=dry_run)
    path = conn.target_path(table)
    if mode in _ADAPTER:
        given = w.need_rows()
        if mode == "merge":
            if not keys:
                raise WriteError('A merge finds each row by its key columns: keys=["order_id"].')
            given.check_keys(keys, unique=True)
            said = f"MERGE INTO {path} ON {' AND '.join(keys)}: update when matched, insert when not"
            return by_adapter(w, sab_adapter.Rows(conn, name), table, "merge", keys, said=said)
        said = f"{mode.upper()} {given.count:,} rows to {path}"
        return by_adapter(w, sab_adapter.Rows(conn, name), table, _ADAPTER[mode], said=said, written=True)
    if mode == "delete":
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
