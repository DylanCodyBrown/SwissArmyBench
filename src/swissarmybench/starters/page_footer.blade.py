# /// swissarmybench-blade
# format = 1
# name = "Page footer"
# kind = "snippet"
# description = "Where the figures come from and when they were read; it can stay at the bottom"
# tags = ["streamlit", "text", "layout"]
# family = "Text and layout"
# language = "streamlit"
# cell_name = "Footer"
# ///
snippet = r"""
# Footer: where the figures come from, how many rows, and when they were read, at the end of the
# page. With Pin set to yes it stays at the bottom of the window while the page scrolls.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.container(key)   a box; given a key, the page marks it with a class of its own,
#                       st-key-<key>, that a style can find
#   st.caption(text)    small, quiet text
#   st.html(body)       HTML on the page itself: here only a <style>, which takes no room
#
# The time is when this run read the rows: each rerun (a click, a pick) reads them again.
import datetime

import streamlit as st

_PIN = "<<pin to the bottom: yes>>" == "yes"  # "yes": it stays at the bottom of the window
_rows = len(<<table>>)
_read = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
# key= gives the box a name of its own on the page, as it does a widget: two with one name would
# stop the page, as a "duplicate widget" error does.
with st.container(key="<<name: page_footer>>"):
    st.caption(f"Source: <<source: Made-up sales data>> · {_rows:,} rows · read {_read}")
if _PIN:
    # Pinned: the box leaves the flow of the page and sits on the window's bottom edge; the page
    # gets room at its end so the box covers nothing.
    st.html(
        "<style>"
        ".st-key-<<name>> {position: fixed; left: 0; right: 0; bottom: 0; z-index: 99;"
        " padding: 0.25rem 1rem; backdrop-filter: blur(8px);"
        " border-top: 1px solid rgba(128, 128, 128, 0.3);}"
        "[data-testid='stMainBlockContainer'] {padding-bottom: 4rem;}"
        "</style>"
    )
"""
