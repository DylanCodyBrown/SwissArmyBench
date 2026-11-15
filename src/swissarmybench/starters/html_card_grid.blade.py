# /// swissarmybench-blade
# format = 1
# name = "HTML card grid"
# kind = "snippet"
# description = "Cards in a grid that wraps: a title and words each"
# tags = ["html", "cards"]
# family = "HTML"
# language = "html"
# ///
snippet = r"""
<!-- A card grid: as many columns as fit, each card a title and a few words (copy a card for more). -->
<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;font-family:'Segoe UI',system-ui,-apple-system,sans-serif">
  <div style="padding:14px;border-radius:10px;border:1px solid color-mix(in srgb, currentColor 18%, transparent);background:color-mix(in srgb, currentColor 5%, transparent)">
    <div style="font-weight:650;margin-bottom:4px"><<first title: North>></div>
    <div style="font-size:13px;opacity:.8"><<first text: 12 stores, the most orders>></div>
  </div>
  <div style="padding:14px;border-radius:10px;border:1px solid color-mix(in srgb, currentColor 18%, transparent);background:color-mix(in srgb, currentColor 5%, transparent)">
    <div style="font-weight:650;margin-bottom:4px"><<second title: South>></div>
    <div style="font-size:13px;opacity:.8"><<second text: 9 stores, growing fastest>></div>
  </div>
  <div style="padding:14px;border-radius:10px;border:1px solid color-mix(in srgb, currentColor 18%, transparent);background:color-mix(in srgb, currentColor 5%, transparent)">
    <div style="font-weight:650;margin-bottom:4px"><<third title: East>></div>
    <div style="font-size:13px;opacity:.8"><<third text: 7 stores, two opening>></div>
  </div>
</div>
"""
