# /// swissarmybench-blade
# format = 1
# name = "Streamlit toast"
# kind = "snippet"
# description = "A button that shows a short message in the corner for a few seconds"
# tags = ["streamlit", "feedback", "toast"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>> toast"
# ///
snippet = r"""
# Toast: a button that shows a short message in the page's corner for a few seconds.
#
# Makes: nothing (it only shows)
# Reads: nothing
#
# Streamlit functions:
#   st.button(label)        a button: True on the rerun its click starts, False on every other
#   st.toast(text, icon)    a short message that pops up in the corner and goes by itself
#
# A toast is for "done" after an action; a message that must stay is st.success or st.info.
import streamlit as st

# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
if st.button("<<label: Save>>", key="<<label: Save>>_toast"):
    st.toast("<<message: Saved>>", icon="✅")
"""
