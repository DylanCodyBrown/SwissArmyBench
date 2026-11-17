# /// swissarmybench-blade
# format = 1
# name = "Component gauge"
# kind = "snippet"
# description = "A half-circle gauge of a total against its target, drawn in SVG (a frame)"
# tags = ["streamlit", "component", "frame", "kpi"]
# family = "Components"
# language = "streamlit"
# cell_name = "<<label>> gauge"
# ///
snippet = r"""
# Gauge: the total of a column against a target, as a half circle that fills as far as the total
# reaches (green at the target or past it, amber from three quarters, red below). Drawn in SVG, with
# nothing fetched from the internet.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left (the gauge moves after each pick)
#
# Streamlit functions:
#   st.iframe(html, height)   a frame holding a page of its own: its HTML, styles and script
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
# This piece uses 2, a frame: the gauge is a small page of its own, so two gauges on one page never
# share an id or a style, and its animation runs inside its frame. It only shows, so one way is all
# it needs. (st.iframe is Streamlit 1.67's name for st.components.v1.html, which now warns that it is
# going.)
import json
from string import Template

import streamlit as st

_label = "<<label: Sales against target>>"
_target = float(<<target: 1000000>>)
_total = float(<<table>>["<<value column>>"].sum())
_share = _total / _target if _target else 0.0
_colour = "#1f9d4c" if _share >= 1 else "#c98a00" if _share >= 0.75 else "#d1343b"

# What the frame shows, as data: numbers, and text already written as the reader sees it.
_data = json.dumps(
    {
        "label": _label,
        "share": max(0.0, min(_share, 1.0)),
        "percent": f"{_share:.0%}",
        "words": f"{_total:,.0f} of {_target:,.0f}",
        "colour": _colour,
    }
)
# The data goes in a <script type="application/json">, which the browser never runs. A value holding
# "</script>" would end it early, so < > & are written as \u003c \u003e \u0026: JSON.parse reads
# them back as the same characters, and the script below puts the text in with textContent.
_data = _data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

_page = Template('''<!doctype html>
<meta charset="utf-8">
<style>
  :root { color-scheme: light dark; font-family: "Segoe UI", system-ui, -apple-system, sans-serif; }
  body { margin: 0; color: #1f2430; text-align: center; }
  @media (prefers-color-scheme: dark) { body { color: #e8eaf0; } }
  .track { stroke: color-mix(in srgb, currentColor 14%, transparent); }
  .fill { transition: stroke-dasharray 0.9s cubic-bezier(.2, .7, .2, 1); }
  @media (prefers-reduced-motion: reduce) { .fill { transition: none; } }
  .percent { font-size: 34px; font-weight: 650; fill: currentColor; }
  .label { font-size: 13px; opacity: .75; margin: 0; }
  .words { font-size: 13px; font-variant-numeric: tabular-nums; margin: 2px 0 0; }
</style>
<svg viewBox="0 0 240 132" width="240" height="132" role="img">
  <path class="track" d="M 20 120 A 100 100 0 0 1 220 120" fill="none" stroke-width="18" stroke-linecap="round"/>
  <path class="fill" d="M 20 120 A 100 100 0 0 1 220 120" fill="none" stroke-width="18" stroke-linecap="round"
        pathLength="100" style="stroke-dasharray: 0 100"/>
  <text class="percent" x="120" y="112" text-anchor="middle"></text>
</svg>
<p class="label"></p>
<p class="words"></p>
<script type="application/json" id="sab-data">$data</script>
<script>
  var data = JSON.parse(document.getElementById("sab-data").textContent);
  var fill = document.querySelector(".fill");
  document.querySelector(".percent").textContent = data.percent;
  document.querySelector(".label").textContent = data.label;
  document.querySelector(".words").textContent = data.words;
  document.querySelector("svg").setAttribute("aria-label", data.label + ": " + data.percent);
  fill.setAttribute("stroke", data.colour);
  // Drawn empty first, then filled on the next frame, so the fill sweeps round (the CSS transition).
  window.requestAnimationFrame(function () {
    window.requestAnimationFrame(function () {
      fill.style.strokeDasharray = (data.share * 100).toFixed(2) + " 100";
    });
  });
</script>
''')
st.iframe(_page.substitute(data=_data), height=<<height: 200>>)
"""
