# /// swissarmybench-blade
# format = 1
# name = "Markdown KPI sentence"
# kind = "snippet"
# description = "One sentence with a total for the region picked (reads region, total_sales)"
# tags = ["markdown", "kpi", "live"]
# family = "Markdown"
# language = "markdown"
# ///
snippet = r"""
<<label: Total for>> {{ <<group name: region>> }}: **{{ <<total name: total_sales>> }}**
"""
