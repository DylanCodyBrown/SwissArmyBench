# /// swissarmybench-blade
# format = 1
# name = "Write partitioned Parquet"
# kind = "snippet"
# description = "The rows written to a folder of Parquet files, by partition columns (dry run first)"
# tags = ["write", "files", "folder"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Partitioned Parquet: the rows written to a folder of Parquet files, a folder for each value of the
# partition columns (region=North/...), as DuckDB, Spark and Power BI read them.
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
path = "<<folder: C:/exports/orders>>"
# A file connection instead (a folder): path = sab.connection("Exports") / "orders"
partition_by = ["<<partition column>>"]  # ["year", "region"] for two levels
if_there = "stop"  # or "replace" (the folder's files go) or "add" (new files beside the old)

w = FileWrite(path, "folder", rows, dry_run=dry_run, overwrite=if_there == "replace", add=if_there == "add")
w.check_columns(partition_by)
copy = (
    "COPY sab_rows TO '{file}' "
    f"(FORMAT parquet, COMPRESSION zstd, PARTITION_BY ({w.names(partition_by)}), FILENAME_PATTERN 'data_{{uuid}}')"
)
w.would(w.statement(copy), written=w.rows.count)
if not dry_run:
    w.done(written=w.copy(copy))
w
"""
