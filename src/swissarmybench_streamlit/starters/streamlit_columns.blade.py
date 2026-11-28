# /// swissarmybench-blade
# format = 1
# name = "Streamlit columns"
# kind = "snippet"
# description = "Two columns side by side: a number on the left, a chart on the right"
# tags = ["streamlit", "layout"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>> beside its chart"
# ///
snippet = r"""
# Columns: two columns side by side, a number on the left and a chart on the right.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.columns(spec)            columns side by side; [1, 2]: the second twice as wide
#   st.metric(label, value)     a big number with its label
#   st.bar_chart(table, x, y)   a bar chart of a table
#
# On a narrow screen the columns stack, one under the other.
import streamlit as st

_left, _right = st.columns([1, 2])
with _left:
    st.metric("<<label: Total sales>>", f"{<<table>>['<<y column: amount>>'].sum():,.0f}")
with _right:
    st.bar_chart(
        <<table>>.groupby("<<x column: region>>", as_index=False)["<<y column: amount>>"].sum(),
        x="<<x column: region>>",
        y="<<y column: amount>>",
    )
"""
