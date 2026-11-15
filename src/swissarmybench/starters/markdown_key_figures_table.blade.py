# /// swissarmybench-blade
# format = 1
# name = "Markdown key figures table"
# kind = "snippet"
# description = "A table of key figures (reads total_sales, order_count, average_order)"
# tags = ["markdown", "kpi", "table", "live"]
# family = "Markdown"
# language = "markdown"
# ///
snippet = r"""
| <<figure heading: Figure>> | <<value heading: Value>> |
| --- | ---: |
| <<first label: Total sales>> | {{ <<first name: total_sales>> }} |
| <<second label: Orders>> | {{ <<second name: order_count>> }} |
| <<third label: Average order>> | {{ <<third name: average_order>> }} |
"""
