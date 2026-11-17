# /// swissarmybench-blade
# format = 1
# name = "Dataverse update"
# kind = "snippet"
# description = "Update Dataverse records by key (dry run first; writes on the user's word)"
# tags = ["write", "dataverse"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Dataverse update: records of a Dataverse table updated from the rows, each found by its key.
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_dataverse = sab.blade("Write to Dataverse")  # until the project's functions.py holds write_dataverse

write_dataverse(
    "<<connection>>",  # your Dataverse connection's name
    "<<target: account>>",  # the table: its logical name (account), entity set or display name
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    mode="update",
    key="<<key column: accountnumber>>",  # finds each record: its id (accountid) or an alternate key's column
    batch_size=1000,  # rows in one change set (one transaction; Dataverse takes up to 1,000)
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
