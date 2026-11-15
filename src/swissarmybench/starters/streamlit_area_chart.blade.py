# /// swissarmybench-blade
# format = 1
# name = "Streamlit area chart"
# kind = "snippet"
# description = "Totals over time, one coloured area for each value of a column"
# tags = ["streamlit", "display", "chart"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<value column>> by <<colour column>>"
# ///
snippet = r"""
# Area chart: the total of a column for each day, one coloured area for each value of another
# column, stacked.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.area_chart(table, x, y, color)   an area chart: x along the bottom, y the height, one area
#                                       (and colour) for each value of color
#
# The totals are worked out first (one per day and value): Streamlit draws the values it is given.
# A database's decimals arrive as Python Decimals, which a chart draws as names: numbers first.
import streamlit as st

st.area_chart(
    <<table>>.astype({"<<value column>>": float}).groupby(["<<date column>>", "<<colour column: region>>"], as_index=False)["<<value column>>"].sum(),
    x="<<date column>>",
    y="<<value column>>",
    color="<<colour column: region>>",
)
"""
