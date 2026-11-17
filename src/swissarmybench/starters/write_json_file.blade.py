# /// swissarmybench-blade
# format = 1
# name = "Write JSON file"
# kind = "snippet"
# description = "The rows written to a JSON file (dry run first; writes on the user's word)"
# tags = ["write", "files", "json", "folder"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# JSON file: the rows written to a JSON file: one array of records, or one record a line.
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# Written to a new file beside the target, then put in its place: a failure leaves the old file as it was.
# The rows are written by DuckDB's COPY.
import duckdb  # the rows are staged in DuckDB

from swissarmybench.client.writes import FileWrite

dry_run = True
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
path = "<<file: C:/exports/orders.json>>"
# A file connection instead (a folder): path = sab.connection("Exports") / "orders.json"
one_a_line = False  # True: newline-delimited JSON (one record a line), as most loaders read
overwrite = False  # True: an existing file is replaced

w = FileWrite(path, "json", rows, dry_run=dry_run, overwrite=overwrite)
copy = "COPY sab_rows TO '{file}' (FORMAT json, ARRAY " + ("false" if one_a_line else "true") + ")"
w.would(w.statement(copy), written=w.rows.count)
if not dry_run:
    w.done(written=w.copy(copy))
w
"""
