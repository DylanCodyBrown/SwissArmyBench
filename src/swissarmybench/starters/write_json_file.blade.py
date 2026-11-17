# /// swissarmybench-blade
# format = 1
# name = "Write JSON file"
# kind = "snippet"
# description = "The rows written to a JSON file (dry run first; writes on the user's word)"
# tags = ["write", "files", "json", "folder"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# JSON file: the rows written to a JSON file: one array of records, or one record a line.
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_json = sab.blade("Write to JSON")  # until the project's functions.py holds write_json

write_json(
    "<<file: C:/exports/orders.json>>",
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    # A file connection instead (a folder): path = sab.connection("Exports") / "orders.json"
    one_a_line=False,  # True: newline-delimited JSON (one record a line), as most loaders read
    overwrite=False,  # True: an existing file is replaced
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
