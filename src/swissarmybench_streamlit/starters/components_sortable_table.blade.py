# /// swissarmybench-blade
# format = 1
# name = "Component sortable table"
# kind = "snippet"
# description = "An HTML table of your own: click a heading to sort, type to filter (a frame)"
# tags = ["streamlit", "component", "frame", "table"]
# family = "Components"
# language = "streamlit"
# cell_name = "<<table>> sortable table"
# ///
snippet = r"""
# Sortable table: the first rows of a table as an HTML table of your own design. Click a heading to
# sort by it (again to turn the order round); type in the box to keep only the rows holding the words.
#
# Makes: nothing (it only shows: the sorting and filtering stay in the frame)
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
# This piece uses 2, a frame: a whole page with its own <style> and script, which cannot leak onto
# the app's page or clash with another table's. It is one way: what is sorted or typed here does not
# reach Python (for that, use st.dataframe, or a two-way component). A frame is its own page, so the
# app's theme does not reach it: it follows the computer's light or dark setting instead.
# (st.iframe is Streamlit 1.67's name for st.components.v1.html, which now warns that it is going.)
import json
from string import Template

import streamlit as st

_shown = <<table>>.head(<<rows: 200>>).copy()
# A date as its day (2026-01-28), which also sorts as text.
for _column in _shown.select_dtypes(include=["datetime", "datetimetz"]).columns:
    _shown[_column] = _shown[_column].dt.strftime("%Y-%m-%d")
# The rows as plain JSON (a missing value as null).
_rows = json.loads(_shown.to_json(orient="values", date_format="iso"))
_data = json.dumps({"columns": [str(c) for c in _shown.columns], "rows": _rows, "total": len(<<table>>)})
# The data goes in a <script type="application/json">, which the browser never runs. A value holding
# "</script>" would end it early, so < > & are written as \u003c \u003e \u0026: JSON.parse reads
# them back as the same characters, and the script below puts each value on the page with textContent
# (as text, never as markup).
_data = _data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

_page = Template('''<!doctype html>
<meta charset="utf-8">
<style>
  :root { color-scheme: light dark; font: 13px/1.4 "Segoe UI", system-ui, -apple-system, sans-serif; }
  body { margin: 0; color: #1f2430; background: transparent; }
  @media (prefers-color-scheme: dark) { body { color: #e8eaf0; } }
  input { width: 100%; box-sizing: border-box; padding: 6px 9px; margin-bottom: 8px; border-radius: 6px;
          border: 1px solid color-mix(in srgb, currentColor 25%, transparent); background: transparent; color: inherit; font: inherit; }
  table { border-collapse: collapse; width: 100%; }
  th { position: sticky; top: 0; text-align: left; cursor: pointer; user-select: none; padding: 6px 9px;
       background: color-mix(in srgb, currentColor 8%, Canvas); border-bottom: 1px solid color-mix(in srgb, currentColor 25%, transparent); }
  th[aria-sort="ascending"]::after { content: " ▲"; }
  th[aria-sort="descending"]::after { content: " ▼"; }
  td { padding: 5px 9px; border-bottom: 1px solid color-mix(in srgb, currentColor 10%, transparent); }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  tbody tr:hover { background: color-mix(in srgb, currentColor 5%, transparent); }
  .count { opacity: .7; margin: 6px 0 0; }
</style>
<input type="search" placeholder="Filter rows" aria-label="Filter rows">
<table><thead><tr></tr></thead><tbody></tbody></table>
<p class="count"></p>
<script type="application/json" id="sab-data">$data</script>
<script>
  var data = JSON.parse(document.getElementById("sab-data").textContent);
  var box = document.querySelector("input"), head = document.querySelector("thead tr");
  var body = document.querySelector("tbody"), count = document.querySelector(".count");
  var order = { column: -1, up: true };
  data.columns.forEach(function (name, i) {
    var th = document.createElement("th");
    th.textContent = name;  // textContent: the column's name as text, whatever it holds
    th.onclick = function () {
      order = { column: i, up: order.column === i ? !order.up : true };
      draw();
    };
    head.append(th);
  });
  function compare(a, b) {
    if (a === b) return 0;
    if (a === null) return 1;
    if (b === null) return -1;
    return typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
  }
  function draw() {
    var words = box.value.trim().toLowerCase();
    var rows = data.rows.filter(function (row) {
      return !words || row.some(function (v) { return String(v === null ? "" : v).toLowerCase().includes(words); });
    });
    if (order.column >= 0) {
      rows = rows.slice().sort(function (a, b) {
        var c = compare(a[order.column], b[order.column]);
        return order.up ? c : -c;
      });
    }
    head.querySelectorAll("th").forEach(function (th, i) {
      th.setAttribute("aria-sort", i === order.column ? (order.up ? "ascending" : "descending") : "none");
    });
    body.replaceChildren.apply(body, rows.map(function (row) {
      var tr = document.createElement("tr");
      row.forEach(function (v) {
        var td = document.createElement("td");
        td.textContent = v === null ? "" : String(v);
        if (typeof v === "number") td.className = "num";
        tr.append(td);
      });
      return tr;
    }));
    count.textContent = rows.length + " of " + data.rows.length + " rows shown" +
      (data.total > data.rows.length ? " (the first " + data.rows.length + " of " + data.total + ")" : "");
  }
  box.oninput = draw;
  draw();
</script>
''')
st.iframe(_page.substitute(data=_data), height=<<height: 380>>)
"""
