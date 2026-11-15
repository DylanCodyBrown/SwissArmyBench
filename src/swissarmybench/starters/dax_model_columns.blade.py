# /// swissarmybench-blade
# format = 1
# name = "DAX model columns"
# kind = "snippet"
# description = "A table's columns and their types, for documenting it (INFO.VIEW.COLUMNS)"
# tags = ["dax", "document"]
# family = "DAX"
# language = "dax"
# ///
snippet = r"""
-- The columns of <<table>>: their names, data types and descriptions.
EVALUATE FILTER ( INFO.VIEW.COLUMNS (), [Table] = "<<table>>" )
"""
