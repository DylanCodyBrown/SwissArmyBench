# /// swissarmybench-blade
# format = 1
# name = "Streamlit bordered container"
# kind = "snippet"
# description = "A box with a border around a title, a number and a note"
# tags = ["streamlit", "layout"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<title>> box"
# ///
snippet = r"""
# Bordered container: a box with a border around what is drawn in it: a title, a number and a note.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.container(border=True)   a box; what is drawn inside `with` goes in it, in order
#   st.subheader(text)          a small heading
#   st.metric(label, value)     a big number with its label
#   st.caption(text)            small, quiet text
import streamlit as st

with st.container(border=True):
    st.subheader("<<title: This month>>")
    st.metric("<<label: Orders>>", f"{len(<<table>>):,}")
    st.caption("<<note: Made-up figures>>")
"""
