# /// swissarmybench-blade
# format = 1
# name = "Streamlit status message"
# kind = "snippet"
# description = "A box that says what was checked, folded to one line once done (st.status)"
# tags = ["streamlit", "display", "status"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>>"
# ///
snippet = r"""
# Status message: a box that says what it is doing while it works, then folds to one line that says
# how it went (st.status, for anything that takes a moment).
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.status(label, expanded)   a box with a spinner while its `with` block runs; .update() changes
#                                its words and its state (complete, error) once it is done
#   st.write(text)               a line of text (or a table, a number: whatever it is given)
#
# A name that starts with _ is this piece's own: other pieces do not read it.
import streamlit as st

_missing = int(<<table>>.isna().sum().sum())  # empty cells in every column, added up
with st.status("<<label: Checking the rows>>", expanded=False) as _status:
    st.write(f"{len(<<table>>):,} rows, {len(<<table>>.columns)} columns")
    st.write(f"{_missing:,} empty cells")
    _status.update(
        label=f"<<label: Checking the rows>>: {'done' if _missing == 0 else f'{_missing:,} empty cells'}",
        state="complete" if _missing == 0 else "error",
    )
"""
