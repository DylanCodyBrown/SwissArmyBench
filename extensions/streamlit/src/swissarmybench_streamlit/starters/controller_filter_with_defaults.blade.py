# /// swissarmybench-blade
# format = 1
# name = "Controller filter with defaults"
# kind = "snippet"
# description = "A dropdown filter whose contract gives each name a type and a default"
# tags = ["streamlit", "controller", "filter"]
# family = "Controllers"
# language = "streamlit"
# cell_name = "<<label>> filter"
# ///
snippet = r"""
# Filter with defaults: pick one value of a column; the Makes line below is its contract.
#
# Makes: <<pick name: {column}>>: str = "All"; <<name: by_{column}>>: table = <<table>>
#   <<pick name>>: the value picked, as text ("All": every value)
#   <<name>>: the rows of <<table>> whose <<column>> is the one picked
# Reads: <<table>>
#   a table: an open one, or the rows another filter left
#
# Streamlit functions:
#   st.selectbox(label, options)   a dropdown: shows the options, gives back the one picked
#
# The contract: each name this cell makes, its type (str, int, float, bool, date, list, table or
# any) and its default. A page that reads <<name>> without this filter on it reads the defaults
# instead ("All", and every row of <<table>>), and the canvas says so quietly, so a page of charts
# still runs before its filter is placed. The app reads the line with Python's own parser: it is
# Python, one `name: type = default` after another with a `;` between.
import streamlit as st

# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
<<pick name>> = st.selectbox(
    "<<label>>",
    ["All", *sorted(<<table>>["<<column>>"].dropna().astype(str).unique())],
    key="<<name>>_pick",
)
# Each pick reruns the whole page from the top, so every piece that reads <<name>> shows the
# rows for what is picked now.
if <<pick name>> == "All":
    <<name>> = <<table>>
else:
    <<name>> = <<table>>[<<table>>["<<column>>"].astype(str) == <<pick name>>]
"""
