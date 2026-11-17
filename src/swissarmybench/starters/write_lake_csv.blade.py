# /// swissarmybench-blade
# format = 1
# name = "Lake CSV file"
# kind = "snippet"
# description = "Rows written as a CSV file in a lake (dry run first; writes on the user's word)"
# tags = ["write", "onelake", "datalake"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Lake CSV file: the rows written as one CSV file in a lake (OneLake: under Files/).
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run=False and run the cell again.
# An agent sets dry_run=False only after you said to write, in your own words, in this conversation.
# The function holds the statements: Copy it as your own from the Write starters to change it.
write_lake_file = sab.blade("Write to a lake file")  # until the project's functions.py holds write_lake_file

write_lake_file(
    "<<connection>>",  # your lake connection's name (Azure Data Lake Storage, OneLake)
    "<<file: exports/orders.csv>>",  # its folders and name in the lake
    <<table>>,  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
    dry_run=True,  # False writes: only once the dry run reads right
)
"""
