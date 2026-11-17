# /// swissarmybench-blade
# format = 1
# name = "Dataverse update"
# kind = "snippet"
# description = "Update a Dataverse table's records from the rows, by key (dry run first)"
# tags = ["write", "dataverse"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Dataverse update: records of a Dataverse table updated from the rows, each found by its key.
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

w = DataverseWrite(connection, table, "update", rows, dry_run=dry_run, batch_size=batch_size)
w.check_columns()  # each column is one of the table's
w.check_key(key)  # a value in each row, one row each
found = w.existing(key)  # the keys that are records
missing = [k for k in w.keys_of(key) if k not in found]
if missing:  # an update only updates: a key that is not a record stops it (the upsert starter makes them)
    raise ValueError(f"{len(missing):,} keys are not records of {table}: {', '.join(missing[:5])}")
w.would(f"PATCH {w.entity_set}(<key>) with If-Match: * (update only), in {w.change_sets()} change sets", updated=len(found))
if not dry_run:
    answers = w.send(lambda row: ("PATCH", w.address(key, row), w.body(row, without=[key]), {"If-Match": "*"}))
    w.done(updated=len(answers))
w
"""
