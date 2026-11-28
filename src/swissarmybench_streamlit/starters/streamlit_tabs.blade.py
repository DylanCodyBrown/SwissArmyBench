# /// swissarmybench-blade
# format = 1
# name = "Streamlit tabs"
# kind = "snippet"
# description = "Two tabs: a chart in one, the rows in the other"
# tags = ["streamlit", "layout"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<table>> tabs"
# ///
snippet = r"""
# Tabs: two tabs over the same place on the page, a chart in one and the rows in the other.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.tabs(labels)             tabs; each is drawn into with `with`, and only the one picked shows
#   st.bar_chart(table, x, y)   a bar chart of a table
#   st.dataframe(table)         the table, sortable and scrollable
#
# Every tab is drawn on every rerun; picking a tab only shows it (the page does not rerun).
import streamlit as st

_chart, _rows = st.tabs(["<<first tab: Chart>>", "<<second tab: Rows>>"])
with _chart:
    st.bar_chart(
        <<table>>.groupby("<<x column: region>>", as_index=False)["<<y column: amount>>"].sum(),
        x="<<x column: region>>",
        y="<<y column: amount>>",
    )
with _rows:
    st.dataframe(<<table>>, hide_index=True)
"""
