# /// swissarmybench-blade
# format = 1
# name = "Streamlit progress bar"
# kind = "snippet"
# description = "A bar filled to how far a total is towards a goal"
# tags = ["streamlit", "display", "progress"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>>"
# ///
snippet = r"""
# Progress bar: how far the total of a column is towards a goal, as a bar and in words.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.progress(value, text)   a bar filled from 0.0 (empty) to 1.0 (full), with words over it
#
# A name that starts with _ is this piece's own: other pieces do not read it.
import streamlit as st

_total = float(<<table>>["<<value column>>"].sum())
_goal = <<goal: 50000>>
# Past the goal the bar stays full: a progress bar takes 0.0 to 1.0, nothing more.
st.progress(min(max(_total / _goal, 0.0), 1.0), text=f"<<label: Sales>>: {_total:,.0f} of {_goal:,}")
"""
