# /// swissarmybench-blade
# format = 1
# name = "Write to partitioned Parquet"
# kind = "other"
# description = "The rows as Parquet files, a folder per value (dry run first; writes on the user's word)"
# tags = ["write", "files", "folder"]
# family = "Write"
# variable = "write_partitioned_parquet"
# ///
"""Partitioned Parquet: the rows written to a folder of Parquet files, a folder for each value of the
partition columns (region=North/...), as DuckDB, Spark and Power BI read them.

    write_partitioned_parquet = sab.blade("Write to partitioned Parquet")  # the project's functions.py will hold it

Dry run first: dry_run=True (the default) only says what it would do and changes nothing;
dry_run=False writes. An agent sets dry_run=False only after the user said to write, in their own
words, in this conversation. Returns the write's report.

Written to a new file beside the target, then put in its place: a failure leaves the old file as it was.
The rows are written by the adapter (adapter.write on its Files: DuckDB's COPY, Plans/adapter.plan.md).

Laid out top to bottom: the imports, then `write_partitioned_parquet`, the one function, which you call.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)

from swissarmybench.client.writes import FileWrite


def write_partitioned_parquet(
    path: str | Path,
    rows: Any,
    partition_by: Sequence[str],
    if_there: str = "stop",
    dry_run: bool = True,
) -> FileWrite:
    """The rows written to a folder of Parquet files, a folder for each value of the partition columns (region=North/...), as DuckDB, Spark and Power BI read them."""
    w = FileWrite(
        path, "folder", rows, dry_run=dry_run, overwrite=if_there == "replace", add=if_there == "add"
    )
    w.check_columns(partition_by)
    return w.by_adapter("COMPRESSION zstd", partition_by)
