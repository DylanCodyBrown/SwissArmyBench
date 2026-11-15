# /// swissarmybench-blade
# format = 1
# name = "Page caption"
# kind = "snippet"
# description = "A line of small, quiet text: a note under a chart or a table"
# tags = ["streamlit", "text", "layout"]
# family = "Text and layout"
# language = "streamlit"
# cell_name = "Caption"
# ///
snippet = r"""
# Caption: a line of small, quiet text, for a note under a chart or a table.
#
# Makes: nothing (it only shows)
# Reads: nothing
#
# Streamlit functions:
#   st.caption(text)   small, quiet text (Markdown: **bold**, *italic* and links work)
import streamlit as st

st.caption("<<words: Amounts are in euros, before tax.>>")
"""
