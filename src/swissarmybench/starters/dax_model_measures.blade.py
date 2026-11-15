# /// swissarmybench-blade
# format = 1
# name = "DAX model measures"
# kind = "snippet"
# description = "Every measure of the model and its formula (INFO.VIEW.MEASURES)"
# tags = ["dax", "document"]
# family = "DAX"
# language = "dax"
# ///
snippet = r"""
-- Every measure of the model: its table, name, formula and format.
EVALUATE INFO.VIEW.MEASURES ()
"""
