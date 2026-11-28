# /// swissarmybench-widget
# format = 1
# name = "delta_card"
# description = "A number in a coloured card"
# framework = "streamlit"
# group = "Data"
# tags = []
# size = [3, 2]
# min_size = [2, 1]
# ///
import streamlit as st

label = "Revenue"
value = "€ 48,200"
change = "+4.5% on last month"
colour = "#2e7d32"

st.markdown(
    f"<div style='border-left:6px solid {colour};padding:0.5rem 0.75rem;border-radius:0.4rem;"
    f"background:rgba(127,127,127,0.08)'><div style='font-size:0.85rem;opacity:0.8'>{label}</div>"
    f"<div style='font-size:1.6rem;font-weight:600'>{value}</div>"
    f"<div style='color:{colour};font-size:0.85rem'>{change}</div></div>",
    unsafe_allow_html=True,
)
