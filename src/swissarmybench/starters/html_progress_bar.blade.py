# /// swissarmybench-blade
# format = 1
# name = "HTML progress bar"
# kind = "snippet"
# description = "A bar filled to a percentage, with its label"
# tags = ["html", "progress"]
# family = "HTML"
# language = "html"
# ///
snippet = r"""
<!-- A progress bar: <<percent: 72>>% of the way. -->
<div style="max-width:420px;font-family:'Segoe UI',system-ui,-apple-system,sans-serif">
  <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
    <span><<label: Orders shipped>></span>
    <span style="font-variant-numeric:tabular-nums"><<percent: 72>>%</span>
  </div>
  <div role="progressbar" aria-label="<<label: Orders shipped>>" aria-valuenow="<<percent: 72>>" aria-valuemin="0"
       aria-valuemax="100" style="height:10px;border-radius:5px;background:color-mix(in srgb, currentColor 18%, transparent);overflow:hidden">
    <div style="width:<<percent: 72>>%;height:100%;border-radius:5px;background:<<colour: #c8102e>>"></div>
  </div>
</div>
"""
