# /// swissarmybench-widget
# format = 1
# name = "logo"
# description = "A name and a mark"
# framework = "streamlit"
# group = "Text"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import streamlit as st

name = "Contoso Analytics"
colour = "#d52b1e"

st.markdown(
    f"<div style='display:flex;align-items:center;gap:0.5rem;font-weight:700;font-size:1.2rem'>"
    f"<span style='width:1.4rem;height:1.4rem;border-radius:0.3rem;background:{colour};display:inline-block'></span>"
    f"{name}</div>",
    unsafe_allow_html=True,
)
