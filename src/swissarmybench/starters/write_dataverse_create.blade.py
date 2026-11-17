# /// swissarmybench-blade
# format = 1
# name = "Dataverse create"
# kind = "snippet"
# description = "Each row a new record in a Dataverse table (dry run first; writes on the user's word)"
# tags = ["write", "dataverse"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Dataverse create: each row a new record in a Dataverse table, through the Web API.
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# Each batch is one $batch change set: all of its rows or none (a failure names the batch; the
# batches before it stay written). A throttled request (429) waits as Dataverse asks, then goes again.
# A choice column takes its labels (Won, not 1); a lookup is a column named <column>@odata.bind.
# It signs in through the connection's own sign-in (sab.connection): no secret in this cell.
from swissarmybench.client.write_dataverse import DataverseWrite

dry_run = True
connection = "<<connection>>"  # your Dataverse connection's name
table = "<<target: account>>"  # the table: its logical name (account), entity set or display name
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
batch_size = 1000  # rows in one change set (one transaction; Dataverse takes up to 1,000)

w = DataverseWrite(connection, table, "create", rows, dry_run=dry_run, batch_size=batch_size)
w.check_columns()  # each column is one of the table's
w.would(f"POST {w.entity_set}: one record a row, in {w.change_sets()} $batch change sets", inserted=w.rows.count)
if not dry_run:
    answers = w.send(lambda row: ("POST", w.entity_set, w.body(row, skip_empty=True), {}))
    w.done(inserted=len(answers))
w
"""
