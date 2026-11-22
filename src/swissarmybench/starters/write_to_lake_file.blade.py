# /// swissarmybench-blade
# format = 1
# name = "Write to a lake file"
# kind = "other"
# description = "Rows written as a Parquet or CSV file in a lake (dry run first; writes on the user's word)"
# tags = ["write", "onelake", "datalake", "parquet", "csv"]
# family = "Write"
# variable = "write_lake_file"
# ///
"""A Parquet or CSV file in a lake connection (Azure Data Lake Storage, OneLake's Files/, a folder of a
Delta Lake here): the rows written as one file, replacing a file of that name.

    write_lake_file = sab.blade("Write to a lake file")  # the project's functions.py will hold it
    write_lake_file("Sales Lake", "exports/orders.parquet", orders)  # a dry run

Dry run first: dry_run=True (the default) only says what it would do and changes nothing; dry_run=False
writes. An agent sets dry_run=False only after the user said to write, in their own words, in this
conversation. It signs in through the connection's own sign-in (sab.connection): no secret here. Returns
the write's report.

Azure and OneLake: the ADLS Gen2 API's create, append and flush (the file appears whole, at the flush);
a folder here: a new file put in the old one's place.

The write is the adapter's (sab_adapter.write on the connection, truncate: the file written whole,
Plans/adapter.plan.md).
"""

from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)

from swissarmybench.adapters import sab_adapter
from swissarmybench.client.writes import Write, WriteError, by_adapter, live

FORMATS = ("parquet", "csv")


def write_lake_file(
    connection: str,
    path: str,
    rows: Any,
    file_format: str = "",
    dry_run: bool = True,
) -> Write:
    """The rows written to `path` (folders and the file's name below the connection's place) of the lake
    connection named `connection`, as parquet or csv (by its suffix when not said).

    rows: a DataFrame (pandas, polars, Arrow) or a DuckDB relation.
    """
    kind = file_format or path.rsplit(".", 1)[-1].lower()
    if kind not in FORMATS:
        raise WriteError(f"A lake file is written as parquet or csv, not {kind!r}: end the path with one.")
    name, conn = live(connection)
    if not hasattr(conn, "write_file"):
        raise WriteError(f"{name} is not a lake connection (Azure Data Lake Storage, OneLake, Delta Lake).")
    w = Write(name, path, f"{kind} file", rows, dry_run=dry_run)
    target = path if path.lower().endswith("." + kind) else f"{path}.{kind}"
    said = f"PUT {path} ({kind}, one file: created, written, flushed)"
    return by_adapter(w, sab_adapter.Rows(conn, name), target, "truncate", said=said, written=True)
