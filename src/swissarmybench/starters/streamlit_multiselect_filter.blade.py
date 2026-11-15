# /// swissarmybench-blade
# format = 1
# name = "Streamlit multiselect filter"
# kind = "snippet"
# description = "Pick any number of a column's values; only their rows go on"
# tags = ["streamlit", "filter"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>> filter"
# ///
snippet = r"""
# Multiselect filter: pick any number of a column's values; only their rows go on.
#
# Makes: <<name: by_{column}>>
#   the rows of <<table>> whose <<column>> is one of those picked (none picked: every row)
# Reads: <<table>>
#   a table: an open one, or the rows another filter left
#
# Streamlit functions:
#   st.multiselect(label, options)   a box of choices: gives back a list of the ones picked
#
# Each pick reruns the whole page from the top, so every piece that reads <<name>> shows the
# rows for what is picked now.
import streamlit as st

# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
_picked = st.multiselect(
    "<<label>>",
    sorted(<<table>>["<<column>>"].dropna().unique()),
    key="<<name>>_pick",
)
# A name that starts with _ is this piece's own: other pieces do not read it.
<<name>> = <<table>>[<<table>>["<<column>>"].isin(_picked)] if _picked else <<table>>
"""
