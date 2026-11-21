# /// swissarmybench-blade
# format = 1
# name = "Write to JSON"
# kind = "other"
# description = "The rows written to a JSON file (dry run first; writes on the user's word)"
# tags = ["write", "files", "json", "folder"]
# family = "Write"
# variable = "write_json"
# ///
"""JSON file: the rows written to a JSON file: one array of records, or one record a line.

    write_json = sab.blade("Write to JSON")  # the project's functions.py will hold it

Dry run first: dry_run=True (the default) only says what it would do and changes nothing;
dry_run=False writes. An agent sets dry_run=False only after the user said to write, in their own
words, in this conversation. Returns the write's report.

Written to a new file beside the target, then put in its place: a failure leaves the old file as it was.
The rows are written by DuckDB's COPY.

Laid out top to bottom: the imports, then `write_json`, the one function, which you call.
"""

from pathlib import Path
from typing import Any

import duckdb  # noqa: F401 (the package this needs: the rows are staged in DuckDB)

from swissarmybench.client.writes import FileWrite


def write_json(
    path: str | Path,
    rows: Any,
    one_a_line: bool = False,
    overwrite: bool = False,
    dry_run: bool = True,
) -> FileWrite:
    """The rows written to a JSON file: one array of records, or one record a line."""
    w = FileWrite(path, "json", rows, dry_run=dry_run, overwrite=overwrite)
    copy = "COPY sab_rows TO '{file}' (FORMAT json, ARRAY " + ("false" if one_a_line else "true") + ")"
    w.would(w.statement(copy), written=w.need_rows().count)
    if not dry_run:
        w.done(written=w.copy(copy))
    return w
