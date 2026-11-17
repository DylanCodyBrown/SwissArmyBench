# /// swissarmybench-blade
# format = 1
# name = "Page logo"
# kind = "snippet"
# description = "The app's logo in the top corner, from a picture beside the app"
# tags = ["streamlit", "text", "layout"]
# family = "Text and layout"
# language = "streamlit"
# cell_name = "Logo"
# ///
snippet = r"""
# Logo: the app's logo, in the top corner of the page (and of the sidebar when there is one).
#
# Makes: nothing (it only shows)
# Reads: nothing
#
# Streamlit functions:
#   st.logo(image)     a picture in the page's top corner, on every rerun
#   st.caption(text)   small, quiet text
#
# The picture is read from the app's own folder (where `streamlit run` starts), so it goes with
# the app: put it beside app.py. A missing picture is said, instead of stopping the page.
from pathlib import Path

import streamlit as st

_picture = Path("<<image file: logo.png>>")
if _picture.is_file():
    st.logo(str(_picture))
else:
    st.caption(f"{_picture.name} is not beside the app yet")
"""
