# /// swissarmybench-blade
# format = 1
# name = "Power BI create push dataset"
# kind = "snippet"
# description = "A push dataset made from the rows' columns, then the rows pushed (dry run first)"
# tags = ["write", "power bi", "powerbi", "push"]
# family = "Write"
# language = "python"
# ///
snippet = r"""
# Power BI create push dataset: a push dataset made in a Power BI workspace from the rows' columns
# (their types from DuckDB's), then the rows pushed into it.
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

w = PushWrite(connection, dataset, in_dataset, "create", rows, dry_run=dry_run)
w.check_new()  # no dataset of that name yet
w.would(
    f"POST datasets: {dataset} (a push dataset), its table {in_dataset}: {w.column_types()}",
    f"POST datasets/<id>/tables/{in_dataset}/rows, {w.requests()} requests",
    inserted=w.rows.count,
)
if not dry_run:
    w.create()
    w.done(inserted=w.push())
w
"""
