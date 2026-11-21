# /// swissarmybench-widget
# format = 1
# name = "input_camera"
# description = "Take a picture with the camera"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [4, 4]
# min_size = [3, 3]
# ///
import streamlit as st
from sab_canvas import key, marked, problem

# The words above the input
label = "Take a picture"
# Shown beside the label as a ?
help_text = ""
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# Said under the input while it is required and missing, or does not fit
validation_message = "Take a picture."


_key = key("value")
value = st.camera_input(marked(label, required), key=_key, help=help_text or None, disabled=disabled)
if required and value is None:
    problem(validation_message)
