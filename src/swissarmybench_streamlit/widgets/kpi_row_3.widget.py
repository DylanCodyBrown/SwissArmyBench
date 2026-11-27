# /// swissarmybench-widget
# format = 1
# name = "kpi_row_3"
# description = "Three numbers in a row"
# framework = "streamlit"
# group = "Data"
# tags = []
# size = [8, 2]
# min_size = [4, 1]
# ///
import streamlit as st

first_label = "Revenue"
first_value = "€ 48,200"
second_label = "Orders"
second_value = "1,284"
third_label = "Customers"
third_value = "312"

for column, (label, value) in zip(
    st.columns(3),
    [(first_label, first_value), (second_label, second_value), (third_label, third_value)],
    strict=True,
):
    column.metric(label, value)
