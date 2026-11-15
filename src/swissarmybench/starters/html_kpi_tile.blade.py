# /// swissarmybench-blade
# format = 1
# name = "HTML KPI tile"
# kind = "snippet"
# description = "One number with its label and its change"
# tags = ["html", "kpi"]
# family = "HTML"
# language = "html"
# ///
snippet = r"""
<!-- A KPI tile: one number, its label and its change. A value may be a name, {{ total }}, filled
     from the kernel when the cell runs. -->
<div style="display:inline-block;min-width:170px;padding:14px 16px;border-radius:10px;border:1px solid color-mix(in srgb, currentColor 18%, transparent);background:color-mix(in srgb, currentColor 5%, transparent);vertical-align:top;font-family:'Segoe UI',system-ui,-apple-system,sans-serif">
  <div style="font-size:12px;letter-spacing:.04em;text-transform:uppercase;opacity:.75"><<label: Revenue>></div>
  <div style="font-size:28px;font-weight:650;font-variant-numeric:tabular-nums;margin-top:2px"><<value: 1,284,000>></div>
  <div style="font-size:12.5px;margin-top:4px;font-variant-numeric:tabular-nums;color:color-mix(in srgb, #1f9d4c 75%, currentColor)"><<change: ▲ 12.4% on last month>></div>
</div>
"""
