# /// swissarmybench-blade
# format = 1
# name = "Write partitioned Parquet"
# kind = "snippet"
# description = "The rows as Parquet files, a folder per value (dry run first; writes on the user's word)"
# tags = ["write", "files", "folder"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Partitioned Parquet: the rows written to a folder of Parquet files, a folder for each value of the
# partition columns (region=North/...), as DuckDB, Spark and Power BI read them.
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_partitioned_parquet = sab.blade("Write to partitioned Parquet")  # until the project's functions.py holds write_partitioned_parquet

write_partitioned_parquet(
    "<<folder: C:/exports/orders>>",
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    ["<<partition column>>"],  # ["year", "region"] for two levels
    # A file connection instead (a folder): path = sab.connection("Exports") / "orders"
    if_there="stop",  # or "replace" (the folder's files go) or "add" (new files beside the old)
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
