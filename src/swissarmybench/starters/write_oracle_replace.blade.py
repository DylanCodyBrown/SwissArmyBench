# /// swissarmybench-blade
# format = 1
# name = "Oracle replace"
# kind = "snippet"
# description = "Replace every row of an Oracle table (dry run first; writes on the user's word)"
# tags = ["write", "oracle"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Oracle replace: every row of a table in Oracle replaced by the rows.
#
# Dry run first: as it stands it only says what it would do (the target, the rows and their types, the
# statements, the counts) and changes nothing. Read it, then set dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_oracle = sab.blade("Write to Oracle")  # until the project's functions.py holds write_oracle

write_oracle(
    "<<connection>>",  # its name in the Connections page
    "<<target: SALES.ORDERS>>",  # the table written to
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    mode="replace",
    batch_size=1000,
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
