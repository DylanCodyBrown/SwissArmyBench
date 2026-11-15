# /// swissarmybench-blade
# format = 1
# name = "Streamlit selectbox filter"
# kind = "snippet"
# description = "A dropdown that picks one value of a column; only its rows go on"
# tags = ["streamlit", "filter"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>> filter"
# ///
snippet = r"""
# Selectbox filter: pick one value of a column from a dropdown; only its rows go on.
#
# Makes: <<name: by_{column}>>
#   the rows of <<table>> whose <<column>> is the one picked ("All": every row)
# Reads: <<table>>
#   a table: an open one, or the rows another filter left
#
# Streamlit functions:
#   st.selectbox(label, options)   a dropdown: shows the options, gives back the one picked
#
# Each pick reruns the whole page from the top, so every piece that reads <<name>> shows the
# rows for what is picked now.
import streamlit as st

# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
_pick = st.selectbox(
    "<<label>>",
    ["All", *sorted(<<table>>["<<column>>"].dropna().unique())],
    key="<<name>>_pick",
)
# A name that starts with _ is this piece's own: other pieces do not read it.
<<name>> = <<table>> if _pick == "All" else <<table>>[<<table>>["<<column>>"] == _pick]
"""
