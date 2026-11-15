# /// swissarmybench-blade
# format = 1
# name = "Streamlit number range filter"
# kind = "snippet"
# description = "A slider with two handles; only the rows in its range go on"
# tags = ["streamlit", "filter", "numbers"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>> filter"
# ///
snippet = r"""
# Number range filter: a slider with two handles; only the rows in its range go on.
#
# Makes: <<name: {value column}_in_range>>
#   the rows of <<table>> whose <<value column>> is from the low handle to the high one
# Reads: <<table>>
#   a table: an open one, or the rows another filter left
#
# Streamlit functions:
#   st.slider(label, min, max, value)   a slider; given two values, it has two handles and gives
#                                       back both
#
# Each pick reruns the whole page from the top, so every piece that reads <<name>> shows the
# rows for what is picked now.
import streamlit as st

_low = float(<<table>>["<<value column>>"].min())
_high = float(<<table>>["<<value column>>"].max())
if _low == _high:  # a slider needs room to slide
    _high = _low + 1
# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
_span = st.slider("<<label>>", _low, _high, (_low, _high), key="<<name>>_pick")
<<name>> = <<table>>[<<table>>["<<value column>>"].between(_span[0], _span[1])]
"""
