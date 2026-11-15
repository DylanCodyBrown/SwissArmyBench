# /// swissarmybench-blade
# format = 1
# name = "Streamlit line chart"
# kind = "snippet"
# description = "A column's total for each day, as a line (st.line_chart)"
# tags = ["streamlit", "display", "chart"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<value column>> over time"
# ///
snippet = r"""
# Line chart: the total of a column for each day, as a line over time.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.line_chart(table, x, y)   a line chart of a table: x along the bottom (here the day), y its height
#
# The totals are worked out first (one per day): Streamlit draws the values it is given.
import streamlit as st

st.line_chart(
    <<table>>.groupby("<<date column>>", as_index=False)["<<value column>>"].sum(),
    x="<<date column>>",
    y="<<value column>>",
)
"""
