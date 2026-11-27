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
from sab_canvas import Event, Out, key

# The button's words
label = "Click me"
kind = "primary"  # choices: primary, secondary, tertiary
# Stretch across its place
full_width = False
# Fired on each click ({"clicks": n}); the Canvas wires what it does
clicked: Event[dict] = None
# How many times it was clicked, for the widgets on the page that read it
clicks: Out[int] = 0

if st.button(label, type=kind, key=key("button"), use_container_width=full_width):
    clicks = (clicks or 0) + 1
    clicked({"clicks": clicks})
if clicks:
    st.caption(f"Clicked {clicks} times")
