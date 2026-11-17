# /// swissarmybench-blade
# format = 1
# name = "Write to CSV"
# kind = "other"
# description = "The rows written to a CSV file (dry run first; writes on the user's word)"
# tags = ["write", "files", "csv", "folder"]
# family = "Write"
# variable = "write_csv"
# ///
"""CSV file: the rows written to a CSV file.

    write_csv = sab.blade("Write to CSV")  # the project's functions.py will hold it

Dry run first: dry_run=True (the default) only says what it would do and changes nothing;
dry_run=False writes. An agent sets dry_run=False only after the user said to write, in their own
words, in this conversation. Returns the write's report.

Written to a new file beside the target, then put in its place: a failure leaves the old file as it was.
The rows are written by DuckDB's COPY.
"""

from pathlib import Path
from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)

from swissarmybench.client.writes import FileWrite


def write_csv(
    path: str | Path,
    rows: Any,
    delimiter: str = ",",
    overwrite: bool = False,
    dry_run: bool = True,
) -> FileWrite:
    """The rows written to a CSV file."""
    w = FileWrite(path, "csv", rows, dry_run=dry_run, overwrite=overwrite)
    copy = f"COPY sab_rows TO '{{file}}' (FORMAT csv, HEADER, DELIMITER {w.literal(delimiter)})"
    w.would(w.statement(copy), written=w.need_rows().count)
    if not dry_run:
        w.done(written=w.copy(copy))
    return w
