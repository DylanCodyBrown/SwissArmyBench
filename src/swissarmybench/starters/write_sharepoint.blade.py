# /// swissarmybench-blade
# format = 1
# name = "SharePoint list write"
# kind = "snippet"
# description = "Write rows to SharePoint list by mode (dry run first; writes on the user's word)"
# tags = ["write", "sharepoint"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# SharePoint list write: the rows written as `mode` says (one of these):
#   create    each row a new item of a SharePoint list, through Graph's $batch.
#   update    the items whose id (or key column) is a row's, changed to the row's values.
#   delete    the items whose id (or key column) is a row's, deleted.
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
    mode="<<mode: create>>",  # create, update or delete
    key="<<key column: id>>",  # update and delete: finds each item: id, or a column one item each
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
