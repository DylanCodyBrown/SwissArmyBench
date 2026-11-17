# /// swissarmybench-blade
# format = 1
# name = "Streamlit CSV download"
# kind = "snippet"
# description = "A button that downloads the rows as a CSV file"
# tags = ["streamlit", "interaction", "download"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>>"
# ///
snippet = r"""
# CSV download: a button that downloads the rows as a CSV file.
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left (the file holds what the filters left)
#
# Streamlit functions:
#   st.download_button(label, data, file_name, mime)   a button; a click saves `data` as a file in
#                                                      the browser's downloads
#
# The file is made on every rerun, so it always holds the rows as they are now.
import streamlit as st

# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
st.download_button(
    "<<label: Download as CSV>>",
    <<table>>.to_csv(index=False).encode("utf-8"),
    file_name="<<file: orders.csv>>",
    mime="text/csv",
    key="<<table>>_csv",
)
"""
