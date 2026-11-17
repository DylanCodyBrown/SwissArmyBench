# /// swissarmybench-blade
# format = 1
# name = "PostgreSQL upsert"
# kind = "snippet"
# description = "Upsert PostgreSQL rows by key (dry run first; writes on the user's word)"
# tags = ["write", "postgres"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# PostgreSQL upsert: the rows inserted into a table in PostgreSQL, or updated where a key matches.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_postgresql = sab.blade("Write to PostgreSQL")  # until the project's functions.py holds write_postgresql

write_postgresql(
    "<<connection>>",  # its name in the Connections page
    "<<target: public.orders>>",  # the table written to
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    mode="upsert",
    keys=["<<key column>>"],  # the columns that find a row: ["region", "order_id"] for two
    batch_size=1000,
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
