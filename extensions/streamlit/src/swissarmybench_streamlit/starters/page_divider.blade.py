# /// swissarmybench-blade
# format = 1
# name = "Page divider"
# kind = "snippet"
# description = "A thin line across the page, between two parts"
# tags = ["streamlit", "text", "layout"]
# family = "Text and layout"
# language = "streamlit"
# cell_name = "Divider"
# ///
snippet = r"""
# Divider: a thin line across the page (or across its column), between two parts.
#
# Makes: nothing (it only shows)
# Reads: nothing
#
# Streamlit functions:
#   st.divider()   a horizontal line
import streamlit as st

st.divider()
"""
