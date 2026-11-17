# /// swissarmybench-blade
# format = 1
# name = "Component callout banner"
# kind = "snippet"
# description = "A coloured callout with a title, a message and a close button (HTML and JavaScript)"
# tags = ["streamlit", "component", "html"]
# family = "Components"
# language = "streamlit"
# cell_name = "<<title: Figures are provisional>> callout"
# ///
snippet = r"""
# Callout banner: a coloured box with a title and a message, and an x that closes it. Your own HTML
# and a few lines of JavaScript, straight on the page.
#
# Makes: nothing (it only shows)
# Reads: nothing
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
# This piece uses 1, st.html: a box that only shows needs no frame and sends nothing back, and on the
# page it takes the app's own font and colours (its text is currentColor, so it reads in dark mode).
import html
from string import Template

import streamlit as st

_title = "<<title: Figures are provisional>>"
_message = "<<message: The month closes on the 5th; until then the numbers can still change.>>"
_tone = "<<tone: info>>"  # info, success, warning or error: the colour of its edge

_colours = {"info": "#2f6fdf", "success": "#1f9d4c", "warning": "#c98a00", "error": "#d1343b"}
_colour = _colours.get(_tone.strip().lower(), _colours["info"])

# The page's HTML, with $title, $message and $colour filled in below. string.Template is used
# rather than an f-string because CSS and JavaScript are full of { } that an f-string would read.
_box = Template('''
<div data-sab-callout role="note" style="position:relative;padding:12px 40px 12px 16px;border-radius:8px;border-left:4px solid $colour;background:color-mix(in srgb, $colour 10%, transparent);font-family:inherit;line-height:1.45">
  <strong style="display:block;margin-bottom:2px">$title</strong>
  <span style="opacity:.85">$message</span>
  <button type="button" aria-label="Close" style="position:absolute;top:6px;right:8px;border:0;background:none;color:inherit;font-size:18px;line-height:1;cursor:pointer;opacity:.6">&times;</button>
</div>
<script>
  // Each callout on the page gets its close button once (data-ready marks the ones done).
  document.querySelectorAll("[data-sab-callout]:not([data-ready])").forEach(function (box) {
    box.dataset.ready = "1";
    box.querySelector("button").onclick = function () { box.hidden = true; };
  });
</script>
''')
# html.escape turns < > & " into &lt; &gt; &amp; &quot;: a title like "<b>" shows as the text <b>,
# never as markup, and no value can end the <script> or start one of its own.
st.html(
    _box.substitute(title=html.escape(_title), message=html.escape(_message), colour=_colour),
    unsafe_allow_javascript=True,
)
"""
