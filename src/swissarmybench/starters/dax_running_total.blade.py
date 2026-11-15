# /// swissarmybench-blade
# format = 1
# name = "DAX running total"
# kind = "snippet"
# description = "A measure added up from the first date to each date"
# tags = ["dax", "time intelligence"]
# family = "DAX"
# language = "dax"
# ///
snippet = r"""
-- Running total: <<measure>> added up from the first date to each date.
DEFINE
    MEASURE '<<table>>'[<<measure>> running total] =
        CALCULATE (
            [<<measure>>],
            FILTER (
                ALL ( '<<date table>>'[<<date column>>] ),
                '<<date table>>'[<<date column>>] <= MAX ( '<<date table>>'[<<date column>>] )
            )
        )
EVALUATE
SUMMARIZECOLUMNS (
    '<<date table>>'[<<date column>>],
    "<<measure>>", [<<measure>>],
    "Running total", [<<measure>> running total]
)
ORDER BY '<<date table>>'[<<date column>>]
"""
