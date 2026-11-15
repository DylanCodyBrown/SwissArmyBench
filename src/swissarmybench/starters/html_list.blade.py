# /// swissarmybench-blade
# format = 1
# name = "HTML list"
# kind = "snippet"
# description = "A list of points with a check mark each"
# tags = ["html", "list"]
# family = "HTML"
# language = "html"
# ///
snippet = r"""
<!-- A list: points with a mark each (add or take away <li> lines). -->
<ul style="list-style:none;margin:0;padding:0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;font-size:14px;line-height:1.5">
  <li style="display:flex;gap:8px;padding:4px 0;border-bottom:1px solid color-mix(in srgb, currentColor 18%, transparent)"><span aria-hidden="true" style="color:color-mix(in srgb, #1f9d4c 75%, currentColor)">✔</span><<first point: Orders are in>></li>
  <li style="display:flex;gap:8px;padding:4px 0;border-bottom:1px solid color-mix(in srgb, currentColor 18%, transparent)"><span aria-hidden="true" style="color:color-mix(in srgb, #1f9d4c 75%, currentColor)">✔</span><<second point: Totals tie out>></li>
  <li style="display:flex;gap:8px;padding:4px 0"><span aria-hidden="true" style="color:color-mix(in srgb, #1f9d4c 75%, currentColor)">✔</span><<third point: Report sent>></li>
</ul>
"""
