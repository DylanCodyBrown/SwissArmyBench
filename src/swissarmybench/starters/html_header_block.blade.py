# /// swissarmybench-blade
# format = 1
# name = "HTML header block"
# kind = "snippet"
# description = "A title, a line under it and the date: the top of a report"
# tags = ["html", "report"]
# family = "HTML"
# language = "html"
# ///
snippet = r"""
<!-- A header block: the top of a report or a story. -->
<header style="font-family:'Segoe UI',system-ui,-apple-system,sans-serif;padding:4px 0 10px;border-bottom:3px solid #c8102e;margin-bottom:12px">
  <div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;opacity:.7"><<kicker: Monthly report>></div>
  <h1 style="margin:2px 0 4px;font-size:26px;line-height:1.2"><<title: Sales by region>></h1>
  <div style="font-size:14px;opacity:.8"><<subtitle: Made-up figures, January 2026>></div>
</header>
"""
