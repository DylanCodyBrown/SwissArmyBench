# /// swissarmybench-blade
# format = 1
# name = "Streamlit toggle filter"
# kind = "snippet"
# description = "A switch: on, only the rows where a yes/no column is yes"
# tags = ["streamlit", "filter"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>> switch"
# ///
snippet = r"""
# Toggle filter: a switch; when it is on, only the rows where a yes/no column is yes go on.
#
# Makes: <<name: only_{flag column}>>
#   the rows of <<table>> where <<flag column>> is yes while the switch is on (off: every row)
# Reads: <<table>>
#   a table: an open one, or the rows another filter left
#
# Streamlit functions:
#   st.toggle(label)   an on/off switch: gives back True while it is on
#
# Each pick reruns the whole page from the top, so every piece that reads <<name>> shows the
# rows for what is picked now.
import streamlit as st

# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
_on = st.toggle("<<label: Only shipped>>", key="<<name>>_pick")
<<name>> = <<table>>[<<table>>["<<flag column>>"].fillna(False).astype(bool)] if _on else <<table>>
"""
