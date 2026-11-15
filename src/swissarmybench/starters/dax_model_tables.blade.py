# /// swissarmybench-blade
# format = 1
# name = "DAX model tables"
# kind = "snippet"
# description = "Every table of the model, for documenting it (INFO.VIEW.TABLES)"
# tags = ["dax", "document"]
# family = "DAX"
# language = "dax"
# ///
snippet = r"""
-- Every table of the model: its name, description and whether it is hidden.
EVALUATE INFO.VIEW.TABLES ()
"""
