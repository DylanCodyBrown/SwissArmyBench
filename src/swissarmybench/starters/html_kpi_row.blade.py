# /// swissarmybench-blade
# format = 1
# name = "HTML KPI row"
# kind = "snippet"
# description = "A row of three KPI cards"
# tags = ["html", "kpi"]
# family = "HTML"
# language = "html"
# ///
snippet = r"""
<!-- A row of KPI cards: three numbers side by side (a value may be a variable of the kernel in double
     braces, filled when the cell runs). Copy a card for a fourth. -->
<div style="display:flex;flex-wrap:wrap;gap:12px">
  <div style="display:inline-block;min-width:170px;padding:14px 16px;border-radius:10px;border:1px solid color-mix(in srgb, currentColor 18%, transparent);background:color-mix(in srgb, currentColor 5%, transparent);vertical-align:top;font-family:'Segoe UI',system-ui,-apple-system,sans-serif">
    <div style="font-size:12px;letter-spacing:.04em;text-transform:uppercase;opacity:.75"><<first label: Revenue>></div>
    <div style="font-size:28px;font-weight:650;font-variant-numeric:tabular-nums;margin-top:2px"><<first value: 1,284,000>></div>
    <div style="font-size:12.5px;margin-top:4px;font-variant-numeric:tabular-nums;color:color-mix(in srgb, #1f9d4c 75%, currentColor)"><<first change: ▲ 12.4%>></div>
  </div>
  <div style="display:inline-block;min-width:170px;padding:14px 16px;border-radius:10px;border:1px solid color-mix(in srgb, currentColor 18%, transparent);background:color-mix(in srgb, currentColor 5%, transparent);vertical-align:top;font-family:'Segoe UI',system-ui,-apple-system,sans-serif">
    <div style="font-size:12px;letter-spacing:.04em;text-transform:uppercase;opacity:.75"><<second label: Orders>></div>
    <div style="font-size:28px;font-weight:650;font-variant-numeric:tabular-nums;margin-top:2px"><<second value: 3,210>></div>
    <div style="font-size:12.5px;margin-top:4px;font-variant-numeric:tabular-nums;color:color-mix(in srgb, #1f9d4c 75%, currentColor)"><<second change: ▲ 4.1%>></div>
  </div>
  <div style="display:inline-block;min-width:170px;padding:14px 16px;border-radius:10px;border:1px solid color-mix(in srgb, currentColor 18%, transparent);background:color-mix(in srgb, currentColor 5%, transparent);vertical-align:top;font-family:'Segoe UI',system-ui,-apple-system,sans-serif">
    <div style="font-size:12px;letter-spacing:.04em;text-transform:uppercase;opacity:.75"><<third label: Average order>></div>
    <div style="font-size:28px;font-weight:650;font-variant-numeric:tabular-nums;margin-top:2px"><<third value: 400>></div>
    <div style="font-size:12.5px;margin-top:4px;font-variant-numeric:tabular-nums;opacity:.75"><<third change: ▬ 0.2%>></div>
  </div>
</div>
"""
