# /// swissarmybench-widget
# format = 1
# name = "sales_top_products"
# description = "The best-selling products as bars"
# framework = "streamlit"
# group = "Charts"
# pack = "Sales dashboard"
# tags = []
# size = [6, 4]
# min_size = [3, 2]
# ///
import altair as alt
import pandas as pd
import streamlit as st
from sab_canvas import key, table

# The table to show (empty: made-up sample data)
table_name = ""  # table
product_column = "product"  # column of table_name
value_column = "revenue"  # column of table_name
# How many to show
top: int = 10  # 1..50
colour = "#2ca02c"
title = "Top products"
# The filter bar's session state key (empty: no filter)
filter_key = "sales_filter"


def _filtered(frame):
    """The filter bar's picks (its session state key) applied where this table has those columns."""
    picked = st.session_state.get(filter_key) or {}
    column = picked.get("region_column")
    if column in frame.columns and picked.get("regions"):
        frame = frame[frame[column].astype(str).isin([str(r) for r in picked["regions"]])]
    column = picked.get("date_column")
    if column in frame.columns and picked.get("start") and picked.get("end"):
        dates = pd.to_datetime(frame[column], errors="coerce")
        frame = frame[(dates >= pd.Timestamp(picked["start"])) & (dates <= pd.Timestamp(picked["end"]))]
    return frame


frame = _filtered(table(table_name))
if product_column not in frame.columns or value_column not in frame.columns:
    st.warning(
        f"Pick a product column and a value column: {product_column} or {value_column} is not in the table."
    )
else:
    best = (
        pd.DataFrame(
            {
                "product": frame[product_column].astype(str),
                "value": pd.to_numeric(frame[value_column], errors="coerce"),
            }
        )
        .groupby("product", as_index=False)["value"]
        .sum()
        .nlargest(int(top), "value")
    )
    chart = (
        alt.Chart(best, title=title or alt.Undefined)
        .mark_bar(color=colour)
        .encode(
            x=alt.X("value:Q", title=value_column),
            y=alt.Y("product:N", sort="-x", title=None),
            tooltip=["product", "value"],
        )
    )
    st.altair_chart(chart, use_container_width=True, key=key("chart"))
