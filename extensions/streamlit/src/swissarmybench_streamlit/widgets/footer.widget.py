# /// swissarmybench-widget
# format = 1
# name = "footer"
# description = "A line at the page's foot"
# framework = "streamlit"
# group = "Text"
# tags = []
# size = [12, 1]
# min_size = [2, 1]
# ///
import streamlit as st

text = "Made-up data · Updated daily · Contoso"

st.markdown(
    f"<div style='text-align:center;opacity:0.7;font-size:0.8rem;padding-top:0.5rem;"
    f"border-top:1px solid rgba(127,127,127,0.3)'>{text}</div>",
    unsafe_allow_html=True,
)
