# /// swissarmybench-blade
# format = 1
# name = "DAX top N by a measure"
# kind = "snippet"
# description = "The top rows of a column by a measure (TOPN)"
# tags = ["dax", "ranking"]
# family = "DAX"
# language = "dax"
# ///
snippet = r"""
-- Top <<count: 10>> values of <<group column>> by <<measure>>, largest first.
EVALUATE
TOPN (
    <<count: 10>>,
    SUMMARIZECOLUMNS ( '<<group table>>'[<<group column>>], "<<measure>>", [<<measure>>] ),
    [<<measure>>], DESC
)
ORDER BY [<<measure>>] DESC
"""
