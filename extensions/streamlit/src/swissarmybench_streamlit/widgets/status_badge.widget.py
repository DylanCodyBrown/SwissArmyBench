# /// swissarmybench-widget
# format = 1
# name = "status_badge"
# description = "A short coloured status"
# framework = "streamlit"
# group = "Data"
# tags = []
# size = [2, 1]
# min_size = [1, 1]
# ///
import streamlit as st

text = "On track"
colour = "#2e7d32"

st.markdown(
    f"<span style='background:{colour};color:white;padding:0.15rem 0.6rem;border-radius:1rem;"
    f"font-size:0.85rem'>{text}</span>",
    unsafe_allow_html=True,
)
