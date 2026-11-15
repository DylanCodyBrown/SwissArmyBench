# /// swissarmybench-blade
# format = 1
# name = "HTML invoice layout"
# kind = "snippet"
# description = "An invoice: who from and to, its lines from a table, and the total"
# tags = ["html", "invoice"]
# family = "HTML"
# language = "html"
# ///
snippet = r"""
<!-- An invoice: {{ <<lines table>> }} is filled with the invoice's lines when the cell runs; the total
     may be a name in double braces too. Made-up names only in examples. -->
<style>
  .invoice { font-family:'Segoe UI',system-ui,-apple-system,sans-serif; font-size: 13px; max-width: 720px; }
  .invoice table { border-collapse: collapse; width: 100%; margin-top: 12px; }
  .invoice th { text-align: left; padding: 6px 8px; border-bottom: 2px solid currentColor; }
  .invoice td { padding: 5px 8px; border-bottom: 1px solid color-mix(in srgb, currentColor 18%, transparent); font-variant-numeric: tabular-nums; }
  .invoice caption { caption-side: bottom; text-align: left; opacity: .7; padding-top: 4px; }
</style>
<div class="invoice">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px">
    <div>
      <div style="font-size:22px;font-weight:700;color:#c8102e"><<from: Example Trading Co.>></div>
      <div style="opacity:.8"><<from address: 1 Made-up Street, Sampletown>></div>
    </div>
    <div style="text-align:right">
      <div style="font-size:20px;font-weight:650">Invoice <<number: 0001>></div>
      <div style="opacity:.8"><<date: 2026-01-31>></div>
    </div>
  </div>
  <div style="margin-top:14px">
    <div style="font-size:12px;text-transform:uppercase;letter-spacing:.05em;opacity:.7">Bill to</div>
    <div style="font-weight:600"><<to: A Made-up Customer Ltd>></div>
    <div style="opacity:.8"><<to address: 2 Sample Road, Exampleton>></div>
  </div>
  {{ <<lines table>> }}
  <div style="display:flex;justify-content:flex-end;margin-top:10px;font-size:16px">
    <span style="opacity:.8;margin-right:12px">Total</span>
    <strong style="font-variant-numeric:tabular-nums"><<total: 1,250.00>></strong>
  </div>
</div>
"""
