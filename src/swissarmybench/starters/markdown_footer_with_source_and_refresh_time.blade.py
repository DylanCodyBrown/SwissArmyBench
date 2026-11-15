# /// swissarmybench-blade
# format = 1
# name = "Markdown footer with source and refresh time"
# kind = "snippet"
# description = "The page's last line: where the data comes from and when it was read (reads refreshed_at)"
# tags = ["markdown", "report", "live"]
# family = "Markdown"
# language = "markdown"
# ///
snippet = r"""
*<<source label: Source>>: <<source: made-up orders (orders.csv)>> · <<refreshed label: Read at>> {{ <<refreshed name: refreshed_at>> }}*
"""
