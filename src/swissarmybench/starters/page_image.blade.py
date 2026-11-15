# /// swissarmybench-blade
# format = 1
# name = "Page image"
# kind = "snippet"
# description = "A picture from beside the app, with a caption under it"
# tags = ["streamlit", "text", "layout"]
# family = "Text and layout"
# language = "streamlit"
# cell_name = "<<caption: Our stores>> picture"
# ///
snippet = r"""
# Image: a picture with a caption under it, as wide as its block.
#
# Makes: nothing (it only shows)
# Reads: nothing
#
# Streamlit functions:
#   st.image(image, caption)   a picture (a file, or bytes), with words under it
#   st.caption(text)           small, quiet text
#
# The picture is read from the app's own folder (where `streamlit run` starts), so it goes with
# the app: put it beside app.py. A missing picture is said, instead of stopping the page.
from pathlib import Path

import streamlit as st

_picture = Path("<<image file: picture.png>>")
if _picture.is_file():
    st.image(str(_picture), caption="<<caption: Our stores>>")
else:
    st.caption(f"{_picture.name} is not beside the app yet")
"""
