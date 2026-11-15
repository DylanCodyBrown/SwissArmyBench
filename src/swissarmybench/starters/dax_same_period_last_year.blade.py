# /// swissarmybench-blade
# format = 1
# name = "DAX same period last year"
# kind = "snippet"
# description = "A measure a year before, and the change (SAMEPERIODLASTYEAR)"
# tags = ["dax", "time intelligence"]
# family = "DAX"
# language = "dax"
# ///
snippet = r"""
-- Same period last year: <<measure>> for the same dates a year before, and the change in percent.
DEFINE
    MEASURE '<<table>>'[<<measure>> LY] =
        CALCULATE ( [<<measure>>], SAMEPERIODLASTYEAR ( '<<date table>>'[<<date column>>] ) )
    MEASURE '<<table>>'[<<measure>> vs LY %] =
        DIVIDE ( [<<measure>>] - [<<measure>> LY], [<<measure>> LY] )
EVALUATE
SUMMARIZECOLUMNS (
    '<<date table>>'[<<date period column: Year>>],
    "<<measure>>", [<<measure>>],
    "<<measure>> LY", [<<measure>> LY],
    "<<measure>> vs LY %", [<<measure>> vs LY %]
)
ORDER BY '<<date table>>'[<<date period column: Year>>]
"""
