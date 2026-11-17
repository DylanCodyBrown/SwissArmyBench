# /// swissarmybench-blade
# format = 1
# name = "Streamlit editable table"
# kind = "snippet"
# description = "A table the page's user can change; the changed rows go on"
# tags = ["streamlit", "display", "table"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "Editable <<table>>"
# ///
snippet = r"""
# Editable table: a table the page's user can type into, add rows to and take rows from.
#
# Makes: <<name: edited>>
#   the rows as they are after the changes (<<table>> itself stays as it was)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.data_editor(table, num_rows="dynamic")   an editable table; "dynamic" adds a row of its own to
#                                               type a new one in. It gives back the table as changed
#
# The changes live in the page while it is open (Streamlit keeps them under the editor's key);
# nothing is written back to <<table>> or to a file. Send <<name>> on to save it somewhere.
import streamlit as st

# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
<<name>> = st.data_editor(<<table>>, num_rows="dynamic", hide_index=True, key="<<name>>_editor")
"""
