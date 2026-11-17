# /// swissarmybench-blade
# format = 1
# name = "Page spacer"
# kind = "snippet"
# description = "Empty room of a height you choose, between two parts of the page"
# tags = ["streamlit", "text", "layout"]
# family = "Text and layout"
# language = "streamlit"
# cell_name = "Spacer"
# ///
snippet = r"""
# Spacer: empty room between two parts of the page, as tall as you choose.
#
# Makes: nothing (it only shows)
# Reads: nothing
#
# Streamlit functions:
#   st.html(body)   HTML on the page itself: here one empty box of a fixed height
import streamlit as st

st.html('<div style="height: <<height in pixels: 32>>px"></div>')
"""
