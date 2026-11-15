# /// swissarmybench-blade
# format = 1
# name = "DAX measure by month"
# kind = "snippet"
# description = "A measure for each year and month of the date table (SUMMARIZECOLUMNS)"
# tags = ["dax", "time intelligence"]
# family = "DAX"
# language = "dax"
# ///
snippet = r"""
-- <<measure>> by month: one row for each year and month of the date table.
-- With a month-number column in the date table, sort by it instead of the month's name.
EVALUATE
SUMMARIZECOLUMNS (
    '<<date table>>'[<<date year column: Year>>],
    '<<date table>>'[<<date month column: Month>>],
    "<<measure>>", [<<measure>>]
)
ORDER BY '<<date table>>'[<<date year column: Year>>], '<<date table>>'[<<date month column: Month>>]
"""
