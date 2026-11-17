# /// swissarmybench-blade
# format = 1
# name = "Dataverse delete"
# kind = "snippet"
# description = "Delete a Dataverse table's records whose keys are in the rows (dry run first)"
# tags = ["write", "dataverse"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Dataverse delete: the records of a Dataverse table whose keys are the rows' keys, deleted.
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
key = "<<key column: accountnumber>>"  # finds each record: its id (accountid) or an alternate key's column
batch_size = 1000  # rows in one change set (one transaction; Dataverse takes up to 1,000)

w = DataverseWrite(connection, table, "delete", rows, dry_run=dry_run, batch_size=batch_size)
w.check_columns([key])  # the key is one of the table's columns
found = w.existing(key)  # only the keys that are records are deleted
w.would(f"DELETE {w.entity_set}(<key>), in {w.change_sets()} change sets", deleted=len(found))
if not dry_run:
    gone = lambda row: ("DELETE", w.address(key, row), None, {}) if str(row[key]).lower() in found else None  # noqa: E731
    answers = w.send(gone)
    w.done(deleted=len(answers))
w
"""
