# /// swissarmybench-blade
# format = 1
# name = "Power BI push rows"
# kind = "snippet"
# description = "Add rows to a Power BI push dataset's table, or replace its rows (dry run first)"
# tags = ["write", "power bi", "powerbi", "push"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Power BI push rows: the rows added to a table of a Power BI push dataset (made from the rows'
# columns when it is not there), or put in place of its rows.
#
# Dry run first: as it stands it only says what it would do and changes nothing. Read it, then set
# dry_run = False and run the cell again.
# An agent sets dry_run = False only after you said to write, in your own words, in this conversation.
# A Power BI model (a semantic model) is not written row by row: write its source, then refresh it
# (Power BI refresh dataset). A push dataset is: rows go in through Power BI's REST API, 10,000 a request.
# It signs in through the workspace connection's own sign-in (sab.connection): no secret in this cell.
from swissarmybench.client.write_powerbi import PushWrite

dry_run = True
connection = "<<connection>>"  # your Power BI workspace connection's name
dataset = "<<dataset: Sales push>>"  # the push dataset
in_dataset = "<<target: Sales>>"  # its table
rows = <<table>>  # a DataFrame (pandas, polars, Arrow) or a DuckDB relation
replace = False  # True: the table's rows are removed first

w = PushWrite(connection, dataset, in_dataset, "replace" if replace else "append", rows, dry_run=dry_run)
there = w.check_push()  # a push dataset with that table, or none yet (it is made)
w.would(
    "" if there else f"POST datasets: {dataset} (a push dataset), its table {in_dataset}: {w.column_types()}",
    f"DELETE datasets/<id>/tables/{in_dataset}/rows" if replace and there else "",
    f"POST datasets/<id>/tables/{in_dataset}/rows, {w.requests()} requests",
    inserted=w.rows.count,
)
if not dry_run:
    if not there:
        w.create()
    elif replace:
        w.clear()
    w.done(inserted=w.push())
w
"""
