# /// swissarmybench-widget
# format = 1
# name = "button"
# description = "A button that counts its clicks"
# framework = "streamlit"
# group = "Buttons"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import key

# The button's words
label = "Click me"
kind = "primary"  # choices: primary, secondary, tertiary
# Stretch across its place
full_width = False

if st.button(label, type=kind, key=key("button"), use_container_width=full_width):
    st.session_state[key("clicks")] = st.session_state.get(key("clicks"), 0) + 1
clicks = st.session_state.get(key("clicks"), 0)
if clicks:
    st.caption(f"Clicked {clicks} times")
