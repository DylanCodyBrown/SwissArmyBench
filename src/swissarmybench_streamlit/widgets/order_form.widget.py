# /// swissarmybench-widget
# format = 1
# name = "order_form"
# description = "Pick a product and an amount, then Add"
# framework = "streamlit"
# group = "Forms"
# tags = []
# size = [5, 3]
# min_size = [3, 2]
# ///
import streamlit as st
from sab_canvas import Event, Out, Table, key

products = ["Alpha", "Beta", "Gamma"]
button = "Add to order"
# Fired on Add ({"product", "amount"}); the Canvas wires what it does
added_line: Event[dict] = None
# The order's lines so far, for the widgets on the page that read them
lines: Out[Table] = None

with st.form(key("order")):
    product = st.selectbox("Product", products, key=key("product"))
    amount = st.number_input("Amount", 1, 1000, 1, key=key("amount"))
    added = st.form_submit_button(button)
if added:
    line = {"product": product, "amount": amount}
    lines = [*(lines or []), line]
    added_line(line)
if lines:
    st.dataframe(lines, hide_index=True)
