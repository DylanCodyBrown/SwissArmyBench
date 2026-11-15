# /// swissarmybench-blade
# format = 1
# name = "DAX percent of total"
# kind = "snippet"
# description = "Each value's share of the whole (DIVIDE over ALL)"
# tags = ["dax", "ratio"]
# family = "DAX"
# language = "dax"
# ///
snippet = r"""
-- Percent of total: each <<group column>>'s share of <<measure>> over every <<group column>>.
DEFINE
    MEASURE '<<table>>'[<<measure>> % of total] =
        DIVIDE ( [<<measure>>], CALCULATE ( [<<measure>>], ALL ( '<<group table>>'[<<group column>>] ) ) )
EVALUATE
SUMMARIZECOLUMNS (
    '<<group table>>'[<<group column>>],
    "<<measure>>", [<<measure>>],
    "% of total", [<<measure>> % of total]
)
ORDER BY [<<measure>>] DESC
"""
