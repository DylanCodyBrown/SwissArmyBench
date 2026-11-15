# /// swissarmybench-blade
# format = 1
# name = "HTML styled table"
# kind = "snippet"
# description = "A table from a DataFrame, styled: banded rows, numbers lined up"
# tags = ["html", "table"]
# family = "HTML"
# language = "html"
# ///
snippet = r"""
<!-- A styled table: {{ <<table>> }} is filled with the table's first rows when the cell runs. -->
<style>
  .styled { font-family:'Segoe UI',system-ui,-apple-system,sans-serif; font-size: 13px; }
  .styled table { border-collapse: collapse; min-width: 320px; }
  .styled caption { caption-side: bottom; text-align: left; padding-top: 6px; opacity: .7; font-size: 12px; }
  .styled th { text-align: left; font-weight: 650; padding: 6px 10px; border-bottom: 2px solid #c8102e; }
  .styled td { padding: 5px 10px; border-bottom: 1px solid color-mix(in srgb, currentColor 18%, transparent); font-variant-numeric: tabular-nums; }
  .styled tbody tr:nth-child(even) { background: color-mix(in srgb, currentColor 5%, transparent); }
</style>
<div class="styled">
  <h3 style="margin:0 0 8px;font-size:15px"><<title: Orders>></h3>
  {{ <<table>> }}
</div>
"""
