# /// swissarmybench-blade
# format = 1
# name = "DAX year to date"
# kind = "snippet"
# description = "A measure added up from the start of each year (TOTALYTD)"
# tags = ["dax", "time intelligence"]
# family = "DAX"
# language = "dax"
# ///
snippet = r"""
-- Year to date: <<measure>> from the first day of the year to each date.
-- TOTALYTD needs a date table with every day once ("DAX date table checks" finds gaps and repeats).
DEFINE
    MEASURE '<<table>>'[<<measure>> YTD] =
        TOTALYTD ( [<<measure>>], '<<date table>>'[<<date column>>] )
EVALUATE
SUMMARIZECOLUMNS (
    '<<date table>>'[<<date column>>],
    "<<measure>>", [<<measure>>],
    "<<measure>> YTD", [<<measure>> YTD]
)
ORDER BY '<<date table>>'[<<date column>>]
"""
