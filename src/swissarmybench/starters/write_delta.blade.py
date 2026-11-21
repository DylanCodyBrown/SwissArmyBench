# /// swissarmybench-blade
# format = 1
# name = "Delta write"
# kind = "snippet"
# description = "Write rows to Delta by mode (dry run first; writes on the user's word)"
# tags = ["write", "delta", "onelake", "datalake"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Delta write: the rows written as `mode` says (one of these):
#   append    the rows added to a Delta table, in one commit.
#   overwrite a Delta table's rows replaced by these, in one commit (earlier versions stay readable).
#   merge     each row updated where its keys match, inserted where not (deltalake's merge).
#   delete    the rows a condition matches deleted, in one commit.
#   optimize  a Delta table's small files compacted into larger ones (the same rows, fewer files).
#   vacuum    files no version within the retention period reads, deleted (time travel before it ends).
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_delta = sab.blade("Write to a Delta table")  # until the project's functions.py holds write_delta

write_delta(
    "<<connection>>",  # your lake connection's name (Delta Lake, OneLake, Azure Data Lake Storage)
    "<<target: sales/orders>>",  # the Delta table: its folders and name in the lake
    <<table>>,  # append, overwrite and merge: a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    mode="<<mode: append>>",  # append, overwrite, merge, delete, optimize or vacuum
    retention_hours=168,  # vacuum: 7 days, the least; less needs allow_shorter=True here
    condition="<<condition: region = 'West'>>",  # delete: a SQL condition on its columns
    keys=["<<key column: order_id>>"],  # merge: the columns that find a row
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
