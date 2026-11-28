# /// swissarmybench-blade
# format = 1
# name = "Streamlit text search"
# kind = "snippet"
# description = "Type a few letters; only the rows whose column holds them go on"
# tags = ["streamlit", "filter", "search"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>>"
# ///
snippet = r"""
# Text search: type a few letters; only the rows whose column holds them go on.
#
# Makes: <<name: {column}_found>>
#   the rows of <<table>> whose <<column>> holds the text typed, in any case (nothing typed: every row)
# Reads: <<table>>
#   a table: an open one, or the rows another filter left
#
# Streamlit functions:
#   st.text_input(label)   a box to type in: gives back the text in it
#
# The page reruns when the typing is done (Enter, or a click elsewhere), not at every letter.
import streamlit as st

# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
_text = st.text_input("<<label: Search>>", key="<<name>>_pick")
_found = <<table>>["<<column>>"].astype(str).str.contains(_text, case=False, regex=False)
<<name>> = <<table>>[_found] if _text else <<table>>
"""
