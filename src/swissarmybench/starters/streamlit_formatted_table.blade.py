# /// swissarmybench-blade
# format = 1
# name = "Streamlit formatted table"
# kind = "snippet"
# description = "A table with its numbers and dates formatted (column_config)"
# tags = ["streamlit", "display", "table"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<title>>"
# ///
snippet = r"""
# Formatted table: the rows as a table that sorts and scrolls, a money column with two decimals and
# a date column as dates.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.subheader(text)                        a small heading
#   st.dataframe(table, column_config=...)    the table, drawn with each column as configured
#   st.column_config.NumberColumn(label, format)   a number column's label and format (%.2f: two decimals)
#   st.column_config.DateColumn(label, format)     a date column's label and format
#
# A click on a column's head sorts by it in the browser; the page does not rerun for that.
import streamlit as st

st.subheader("<<title: Orders>>")
st.dataframe(
    <<table>>,
    hide_index=True,
    column_config={
        "<<value column>>": st.column_config.NumberColumn("<<value label>>", format="%.2f"),
        "<<date column>>": st.column_config.DateColumn("<<date label>>", format="YYYY-MM-DD"),
    },
)
"""
