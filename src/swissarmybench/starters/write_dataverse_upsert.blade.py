# /// swissarmybench-blade
# format = 1
# name = "Dataverse upsert"
# kind = "snippet"
# description = "Upsert Dataverse records by key (dry run first; writes on the user's word)"
# tags = ["write", "dataverse"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Dataverse upsert: each row a record of a Dataverse table, made or updated by its key
# (an alternate key's column, or the record's id).
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

w = DataverseWrite(connection, table, "upsert", rows, dry_run=dry_run, batch_size=batch_size)
w.check_columns()  # each column is one of the table's
w.check_key(key)  # a value in each row, one row each
found = len(w.existing(key)) if dry_run else None  # the keys that are records already
w.would(
    f"PATCH {w.entity_set}(<key>) (Dataverse makes the record when it is not there), in {w.change_sets()} change sets",
    updated=found,
    inserted=None if found is None else w.rows.count - found,
)
if not dry_run:
    prefer = {"Prefer": "return=representation"}  # answered 201 when made, 200 when updated
    answers = w.send(lambda row: ("PATCH", w.address(key, row), w.body(row, without=[key]), prefer))
    w.done(inserted=answers.count(201), updated=answers.count(200))
w
"""
