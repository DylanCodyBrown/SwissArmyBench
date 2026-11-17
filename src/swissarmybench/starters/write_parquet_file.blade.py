# /// swissarmybench-blade
# format = 1
# name = "Write Parquet file"
# kind = "snippet"
# description = "The rows written to a Parquet file (dry run first; writes on the user's word)"
# tags = ["write", "files", "parquet", "folder"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Parquet file: the rows written to one Parquet file (zstd).
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_parquet = sab.blade("Write to Parquet")  # until the project's functions.py holds write_parquet

write_parquet(
    "<<file: C:/exports/orders.parquet>>",
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    # A file connection instead (a folder): path = sab.connection("Exports") / "orders.parquet"
    overwrite=False,  # True: an existing file is replaced
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
