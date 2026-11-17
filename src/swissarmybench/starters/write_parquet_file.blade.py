# /// swissarmybench-blade
# format = 1
# name = "Write Parquet file"
# kind = "snippet"
# description = "The rows written to a Parquet file (dry run first)"
# tags = ["write", "files", "parquet", "folder"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Parquet file: the rows written to one Parquet file (zstd).
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
path = "<<file: C:/exports/orders.parquet>>"
# A file connection instead (a folder): path = sab.connection("Exports") / "orders.parquet"
overwrite = False  # True: an existing file is replaced

w = FileWrite(path, "parquet", rows, dry_run=dry_run, overwrite=overwrite)
copy = "COPY sab_rows TO '{file}' (FORMAT parquet, COMPRESSION zstd)"
w.would(w.statement(copy), written=w.rows.count)
if not dry_run:
    w.done(written=w.copy(copy))
w
"""
