# /// swissarmybench-blade
# format = 1
# name = "Streamlit expander"
# kind = "snippet"
# description = "A folded section that opens on a click: the rows inside"
# tags = ["streamlit", "layout"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>>"
# ///
snippet = r"""
# Expander: a folded section with a title; a click opens it to show the rows.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.expander(label, expanded)   a section that folds; what is drawn inside `with` goes in it
#   st.dataframe(table)            the table, sortable and scrollable
#   st.caption(text)               small, quiet text
#
# What is inside is drawn on every rerun, open or folded.
import streamlit as st

with st.expander("<<label: Show the rows>>", expanded=False):
    st.dataframe(<<table>>, hide_index=True)
    st.caption(f"{len(<<table>>):,} rows")
"""
