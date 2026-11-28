# /// swissarmybench-blade
# format = 1
# name = "Streamlit bar chart"
# kind = "snippet"
# description = "A bar for each value of a column: a total of another (st.bar_chart)"
# tags = ["streamlit", "display", "chart"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<y column>> by <<x column>>"
# ///
snippet = r"""
# Bar chart: one bar for each value of a column, as tall as the total of another.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.bar_chart(table, x, y)   a bar chart of a table: x the column along the bottom, y the bars' height
#
# The totals are worked out first (groupby ... sum): Streamlit draws the values it is given.
# A database's decimals arrive as Python Decimals, which a chart draws as names: numbers first.
import streamlit as st

st.bar_chart(
    <<table>>.astype({"<<y column: amount>>": float}).groupby("<<x column: region>>", as_index=False)["<<y column: amount>>"].sum(),
    x="<<x column: region>>",
    y="<<y column: amount>>",
)
"""
