# /// swissarmybench-blade
# format = 1
# name = "Streamlit check messages"
# kind = "snippet"
# description = "A success, warning or error message, by what the rows hold"
# tags = ["streamlit", "feedback", "messages"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "Check of <<table>>"
# ///
snippet = r"""
# Check messages: a green, yellow or red message by what the rows hold: an error when a column the
# page needs is missing, a warning when no rows are left, else a success.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.error(text)     a red message box
#   st.warning(text)   a yellow message box
#   st.success(text)   a green message box
#
# Each has an icon and its words as well as its colour, so it reads without the colour too.
import streamlit as st

if "<<column>>" not in <<table>>.columns:
    st.error("<<table>> has no column <<column>>: this page needs it.")
elif <<table>>.empty:
    st.warning("No rows are left: widen the filters.")
else:
    st.success(f"{len(<<table>>):,} rows, each with its <<column>>.")
"""
