# /// swissarmybench-widget
# format = 1
# name = "kpi_row_4"
# description = "Four numbers in a row"
# framework = "streamlit"
# group = "Data"
# tags = []
# size = [10, 2]
# min_size = [4, 1]
# ///
import streamlit as st

labels = ["Revenue", "Orders", "Customers", "Margin"]
values = ["€ 48,200", "1,284", "312", "21%"]
changes = ["+4.5%", "+2.1%", "-0.8%", "+1.2%"]

for at, column in enumerate(st.columns(4)):
    column.metric(
        labels[at] if at < len(labels) else "",
        values[at] if at < len(values) else "",
        changes[at] if at < len(changes) else None,
    )
