# /// swissarmybench-blade
# format = 1
# name = "Component timeline"
# kind = "snippet"
# description = "A table's latest rows as a timeline: a dot, a date and a title for each (a frame)"
# tags = ["streamlit", "component", "frame"]
# family = "Components"
# language = "streamlit"
# cell_name = "<<table>> timeline"
# ///
snippet = r"""
# Timeline: the latest rows of a table, newest first, as a line of dots, each with its date and its
# title (the value of a column you pick: an event, an order, a note).
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
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
# This piece uses 2, a frame: a long list scrolls inside its own frame (the height below) and its
# styles stay its own. It only shows, so one way is all it needs. (st.iframe is Streamlit 1.67's
# name for st.components.v1.html, which now warns that it is going.)
import json
from string import Template

import pandas as pd
import streamlit as st

_latest = <<table>>.assign(_when=pd.to_datetime(<<table>>["<<date column>>"]))
_latest = _latest.sort_values("_when", ascending=False).head(<<count: 12>>)
# Each row as text, written in Python the way the reader sees it.
_items = [
    {
        "when": _row["_when"].strftime("%d %b %Y"),
        "title": str(_row["<<title column>>"]),
    }
    for _, _row in _latest.iterrows()
]
# The data goes in a <script type="application/json">, which the browser never runs. A value holding
# "</script>" would end it early, so < > & are written as \u003c \u003e \u0026: JSON.parse reads
# them back as the same characters, and the script below puts each one in with textContent.
_data = json.dumps(_items).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

_page = Template('''<!doctype html>
<meta charset="utf-8">
<style>
  :root { color-scheme: light dark; font: 13px/1.4 "Segoe UI", system-ui, -apple-system, sans-serif; }
  body { margin: 0; color: #1f2430; }
  @media (prefers-color-scheme: dark) { body { color: #e8eaf0; } }
  ol { list-style: none; margin: 0 0 0 8px; padding: 4px 0 4px 18px; border-left: 2px solid color-mix(in srgb, currentColor 18%, transparent); }
  li { position: relative; padding: 0 0 14px 14px; }
  li::before { content: ""; position: absolute; left: -25px; top: 3px; width: 10px; height: 10px; border-radius: 50%;
               background: #2f6fdf; box-shadow: 0 0 0 3px color-mix(in srgb, #2f6fdf 22%, transparent); }
  .when { font-size: 11.5px; letter-spacing: .04em; text-transform: uppercase; opacity: .65; }
  .title { font-weight: 600; }
  .none { opacity: .7; }
</style>
<ol></ol>
<script type="application/json" id="sab-data">$data</script>
<script>
  var items = JSON.parse(document.getElementById("sab-data").textContent);
  var list = document.querySelector("ol");
  function line(kind, text) {
    var div = document.createElement("div");
    div.className = kind;
    div.textContent = text;  // textContent: the value as text, whatever it holds
    return div;
  }
  items.forEach(function (item) {
    var li = document.createElement("li");
    li.append(line("when", item.when), line("title", item.title));
    list.append(li);
  });
  if (!items.length) list.replaceWith(line("none", "No rows to show."));
</script>
''')
st.iframe(_page.substitute(data=_data), height=<<height: 360>>)
"""
