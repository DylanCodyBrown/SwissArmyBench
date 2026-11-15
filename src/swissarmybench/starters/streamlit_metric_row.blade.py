# /// swissarmybench-blade
# format = 1
# name = "Streamlit metric row"
# kind = "snippet"
# description = "Three numbers side by side: rows, total and average"
# tags = ["streamlit", "display", "metric"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<total label>> row"
# ///
snippet = r"""
# Metric row: three numbers side by side: how many rows, the total of a column and its average.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.columns(n)            n columns side by side; each one is drawn into with `with`
#   st.metric(label, value)  a big number with its label
#
# A name that starts with _ is this piece's own: other pieces do not read it.
import streamlit as st

_average = <<table>>["<<value column>>"].mean() if len(<<table>>) else 0
_first, _second, _third = st.columns(3)
with _first:
    st.metric("<<count label: Orders>>", f"{len(<<table>>):,}")
with _second:
    st.metric("<<total label: Total sales>>", f"{<<table>>['<<value column>>'].sum():,.0f}")
with _third:
    st.metric("<<average label: Average sale>>", f"{_average:,.2f}")
"""
