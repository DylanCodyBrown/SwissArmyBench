# /// swissarmybench-blade
# format = 1
# name = "Page section heading"
# kind = "snippet"
# description = "A heading for a part of the page, with a line under it"
# tags = ["streamlit", "text", "layout"]
# family = "Text and layout"
# language = "streamlit"
# cell_name = "<<heading: Regions>> heading"
# ///
snippet = r"""
# Section heading: a heading for a part of the page, with a thin line under it.
#
# Makes: nothing (it only shows)
# Reads: nothing
#
# Streamlit functions:
#   st.header(text, divider)   a heading, a size under the title; divider draws a line under it
#                              (True: the theme's colour, or one of blue, green, orange, red,
#                              violet, gray, rainbow)
#
# st.subheader is the next size down, for a part inside a part.
import streamlit as st

st.header("<<heading: Regions>>", divider="<<line colour: gray>>")
"""
