# /// swissarmybench-blade
# format = 1
# name = "Streamlit file upload"
# kind = "snippet"
# description = "A box to drop a CSV or Excel file on; its rows as a table"
# tags = ["streamlit", "interaction", "upload"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>>"
# ///
snippet = r"""
# File upload: a box to drop a CSV or Excel file on (or browse for one); its rows become a table.
#
# Makes: <<name: uploaded>>
#   the file's rows as a table (pandas DataFrame); None until a file is given
# Reads: nothing
#
# Streamlit functions:
#   st.file_uploader(label, type)   a drop box: gives back the file given (None before), which pandas
#                                   reads as it reads a file on disk
#   st.info(text)                   a blue message box
#
# The file stays in the page's memory; nothing is saved. Pieces that read <<name>> should allow for
# None (no file yet).
import pandas as pd
import streamlit as st

# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
_file = st.file_uploader("<<label: A CSV or Excel file>>", type=["csv", "xlsx"], key="<<name>>_file")
if _file is None:
    <<name>> = None
    st.info("<<waiting: Drop a file here to see its rows.>>")
elif _file.name.lower().endswith(".xlsx"):
    <<name>> = pd.read_excel(_file)
else:
    <<name>> = pd.read_csv(_file)
"""
