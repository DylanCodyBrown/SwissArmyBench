# /// swissarmybench-blade
# format = 1
# name = "DAX model relationships"
# kind = "snippet"
# description = "Every relationship of the model (INFO.VIEW.RELATIONSHIPS)"
# tags = ["dax", "document"]
# family = "DAX"
# language = "dax"
# ///
snippet = r"""
-- Every relationship of the model: from which table and column to which, whether it is active, and
-- which way it filters.
EVALUATE INFO.VIEW.RELATIONSHIPS ()
"""
