# /// swissarmybench-blade
# format = 1
# name = "Page title with subtitle"
# kind = "snippet"
# description = "The page's title, and a quiet line under it"
# tags = ["streamlit", "text", "layout"]
# family = "Text and layout"
# language = "streamlit"
# cell_name = "<<title: Sales overview>> title"
# ///
snippet = r"""
# Title with subtitle: the page's big title, and a line of quiet words under it.
#
# Makes: nothing (it only shows)
# Reads: nothing
#
# Streamlit functions:
#   st.title(text)     the page's title: the biggest heading, once at the top
#   st.caption(text)   small, quiet text
#
# The title is Markdown: **bold** and *italic* work in it. The browser tab's own title is set apart,
# in the page settings.
import streamlit as st

st.title("<<title: Sales overview>>")
st.caption("<<subtitle: Made-up figures for the regions, read each morning>>")
"""
