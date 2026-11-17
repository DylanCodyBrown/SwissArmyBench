# /// swissarmybench-blade
# format = 1
# name = "Delta optimize"
# kind = "snippet"
# description = "A Delta table's small files compacted (dry run first; writes on the user's word)"
# tags = ["write", "delta", "onelake", "datalake"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Delta optimize: a Delta table's small files compacted into larger ones (the same rows, fewer files).
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_delta = sab.blade("Write to a Delta table")  # until the project's functions.py holds write_delta

write_delta(
    "<<connection>>",  # your lake connection's name (Delta Lake, OneLake, Azure Data Lake Storage)
    "<<target: sales/orders>>",  # the Delta table: its folders and name in the lake
    mode="optimize",
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
