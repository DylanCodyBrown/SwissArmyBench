# /// swissarmybench-widget
# format = 1
# name = "metric"
# description = "One number, with its change"
# framework = "streamlit"
# group = "Data"
# tags = []
# size = [3, 2]
# min_size = [2, 1]
# ///
import streamlit as st

label = "Revenue"
value = "€ 48,200"
change = "+4.5%"
# Down is good (costs)
inverse = False

st.metric(label, value, change, delta_color="inverse" if inverse else "normal")
