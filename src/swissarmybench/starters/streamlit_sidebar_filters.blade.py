# /// swissarmybench-blade
# format = 1
# name = "Streamlit sidebar filters"
# kind = "snippet"
# description = "Three filters in the sidebar: a list, a range and a search"
# tags = ["streamlit", "filter", "sidebar"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<title>>"
# ///
snippet = r"""
# Sidebar filters: three filters in the sidebar (the strip at the page's left) that work together:
# values of a column picked from a list, a range of numbers, and a text search.
#
# Makes: <<name: filtered>>, <<category name>>, <<number name: {number column}_range>>
#   <<name>>: the rows of <<table>> all three filters leave
#   <<category name>>: the list of <<category column>> values picked (empty: all of them)
#   <<number name>>: the (low, high) range of <<number column>> on the slider
# Reads: <<table>>
#   a table: an open one, or the rows another filter left
#
# Streamlit functions:
#   st.sidebar                          the sidebar: what is drawn inside `with st.sidebar:` goes there
#   st.header(text)                     a heading
#   st.multiselect(label, options)      a box of choices: gives back a list of the ones picked
#   st.slider(label, min, max, value)   a slider; given two values, it has two handles
#   st.text_input(label)                a box to type in: gives back the text in it
#
# Each pick reruns the whole page from the top, so every piece that reads these names shows the
# rows for what is picked now.
import streamlit as st

_low = float(<<table>>["<<number column>>"].min())
_high = float(<<table>>["<<number column>>"].max()) or _low + 1
# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
with st.sidebar:
    st.header("<<title: Filters>>")
    <<category name>> = st.multiselect(
        "<<category label>>",
        sorted(<<table>>["<<category column>>"].dropna().unique()),
        key="<<name>>_category",
    )
    <<number name>> = st.slider(
        "<<number label>>", _low, max(_high, _low + 1), (_low, max(_high, _low + 1)), key="<<name>>_range"
    )
    _text = st.text_input("<<search label: Search>>", key="<<name>>_search")

# A name that starts with _ is this piece's own: other pieces do not read it.
_rows = <<table>>
if <<category name>>:
    _rows = _rows[_rows["<<category column>>"].isin(<<category name>>)]
_rows = _rows[_rows["<<number column>>"].between(<<number name>>[0], <<number name>>[1])]
if _text:
    _rows = _rows[_rows["<<search column>>"].astype(str).str.contains(_text, case=False, regex=False)]
<<name>> = _rows
"""
