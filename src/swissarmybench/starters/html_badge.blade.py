# /// swissarmybench-blade
# format = 1
# name = "HTML badge"
# kind = "snippet"
# description = "A small rounded label for a state or a kind"
# tags = ["html", "badge"]
# family = "HTML"
# language = "html"
# ///
snippet = r"""
<!-- A badge: a small rounded label. Its text says the state, so it reads without the colour too. -->
<span style="display:inline-block;padding:1px 9px;border-radius:999px;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;font-size:12px;font-weight:600;
             border:1px solid color-mix(in srgb, <<colour: #1f9d4c>> 60%, transparent);
             color:color-mix(in srgb, <<colour: #1f9d4c>> 75%, currentColor);
             background:color-mix(in srgb, <<colour: #1f9d4c>> 12%, transparent)"><<text: Shipped>></span>
"""
