# /// swissarmybench-blade
# format = 1
# name = "Component animated KPI counter"
# kind = "snippet"
# description = "A big total that counts up from zero when the page draws (HTML and JavaScript)"
# tags = ["streamlit", "component", "html", "kpi"]
# family = "Components"
# language = "streamlit"
# cell_name = "<<label>> counter"
# ///
snippet = r"""
# Animated KPI counter: the total of a column as one big number that counts up from zero when the
# page draws. Without JavaScript (or with "reduce motion" set on the computer) it simply shows the total.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left (it counts again after each pick)
#
# Streamlit functions:
#   st.html(body, unsafe_allow_javascript=True)   HTML on the page itself; True lets its <script> run
#
# Three ways to put your own HTML and JavaScript on a Streamlit page:
#   1. st.html(body, unsafe_allow_javascript=True)  on the page itself. One way: Python to the page.
#   2. st.iframe(html)                              a frame, a little page of its own. One way.
#   3. st.components.v2.component(...)              on the page, and TWO-WAY: its JavaScript sends a
#                                                   value back, and Python reads it on the rerun.
# The HTML, CSS and JavaScript you give them are code: they run as written. So a value from your data
# (or anything typed) is never pasted into them as code. Text is escaped with html.escape, a frame's
# data goes in as JSON, and a component gets its data in data= and puts it on the page as text.
#
# This piece uses 1, st.html: the number is worked out in Python and only shown, so nothing comes
# back; JavaScript only moves it. On the page it sits in a row with st.metric and matches its font.
import html
from string import Template

import streamlit as st

_label = "<<label: Total sales>>"
_decimals = int(<<decimals: 0>>)  # digits after the point
_total = float(<<table>>["<<value column>>"].sum())

_tile = Template('''
<div data-sab-count="$target" data-decimals="$decimals" style="display:inline-block;min-width:180px;padding:14px 18px;border-radius:10px;border:1px solid color-mix(in srgb, currentColor 16%, transparent);font-family:inherit">
  <div style="font-size:12px;letter-spacing:.05em;text-transform:uppercase;opacity:.7">$label</div>
  <div class="sab-number" style="font-size:34px;font-weight:650;font-variant-numeric:tabular-nums">$shown</div>
</div>
<script>
  // Each counter on the page starts once (data-ready marks the ones started).
  document.querySelectorAll("[data-sab-count]:not([data-ready])").forEach(function (tile) {
    tile.dataset.ready = "1";
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;  // the total is already there
    var target = Number(tile.dataset.sabCount), digits = Number(tile.dataset.decimals);
    var number = tile.querySelector(".sab-number"), start = performance.now(), length = 900;
    function step(now) {
      var done = Math.min(1, (now - start) / length), eased = 1 - Math.pow(1 - done, 3);
      number.textContent = (target * eased).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
      if (done < 1) window.requestAnimationFrame(step);
    }
    window.requestAnimationFrame(step);
  });
</script>
''')
# The number goes in as a number (Python writes it), the label as escaped text: nothing from the data
# can become markup or code.
st.html(
    _tile.substitute(
        target=repr(_total),
        decimals=_decimals,
        label=html.escape(_label),
        shown=html.escape(f"{_total:,.{_decimals}f}"),
    ),
    unsafe_allow_javascript=True,
)
"""
