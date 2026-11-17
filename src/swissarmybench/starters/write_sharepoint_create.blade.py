# /// swissarmybench-blade
# format = 1
# name = "SharePoint list create"
# kind = "snippet"
# description = "Each row a new item of a SharePoint list (dry run first; writes on the user's word)"
# tags = ["write", "sharepoint"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# SharePoint list create: each row a new item of a SharePoint list, through Graph's $batch.
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_sharepoint_list = sab.blade("Write to a SharePoint list")  # until the project's functions.py holds write_sharepoint_list

write_sharepoint_list(
    "<<connection>>",  # your SharePoint lists connection's name
    "<<target: Tasks>>",  # the list: its display name
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    mode="create",
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
