# /// swissarmybench-widget
# format = 1
# name = "ops_inventory_status"
# description = "How many items are in stock, low and out of stock"
# framework = "streamlit"
# group = "Data"
# pack = "Operations"
# tags = []
# size = [6, 4]
# min_size = [3, 2]
# ///
import altair as alt
import pandas as pd
import streamlit as st
from sab_canvas import key, table

# The stock table (empty: made-up sample data)
table_name = ""  # table
on_hand_column = "on_hand"  # column of table_name
reorder_column = "reorder_point"  # column of table_name
in_stock_colour = "#2ca02c"
low_colour = "#ff7f0e"
out_colour = "#d62728"


def _sample():
    """Made-up stock: twelve products in two stores (the shape of inventory_snapshots)."""
    names = [
        "Desk lamp",
        "Storage box",
        "Cushion",
        "Planter",
        "Trowel",
        "Kettle",
        "Claw hammer",
        "Screw pack",
        "Notebook",
        "Shipping box",
        "Wok",
        "Bench",
    ]
    rows = []
    for at, name in enumerate(names):
        for store in ("Larkfield Shop", "Marshby Depot"):
            on_hand = (at * 37 + len(store) * 11) % 140 - 15
            rows.append(
                {
                    "store": store,
                    "product_id": 100 + at,
                    "product_name": name,
                    "on_hand": max(on_hand, 0),
                    "on_order": 48 if on_hand < 20 else 0,
                    "reorder_point": 20 + (at % 4) * 5,
                }
            )
    return pd.DataFrame(rows)


frame = table(table_name) if table_name else _sample()
if on_hand_column not in frame.columns or reorder_column not in frame.columns:
    st.warning(f"Pick the stock columns: {on_hand_column} or {reorder_column} is not in the table.")
else:
    on_hand = pd.to_numeric(frame[on_hand_column], errors="coerce").fillna(0)
    reorder = pd.to_numeric(frame[reorder_column], errors="coerce").fillna(0)
    state = pd.Series("In stock", index=frame.index)
    state[on_hand <= reorder] = "Low"
    state[on_hand <= 0] = "Out of stock"
    counts = state.value_counts()
    first, second, third = st.columns(3)
    first.metric("In stock", int(counts.get("In stock", 0)))
    second.metric("Low", int(counts.get("Low", 0)))
    third.metric("Out of stock", int(counts.get("Out of stock", 0)))
    shown = pd.DataFrame({"state": counts.index, "items": counts.values})
    colours = alt.Scale(
        domain=["In stock", "Low", "Out of stock"], range=[in_stock_colour, low_colour, out_colour]
    )
    chart = (
        alt.Chart(shown)
        .mark_bar()
        .encode(
            x=alt.X("items:Q", title=None),
            y=alt.Y("state:N", title=None, sort=["In stock", "Low", "Out of stock"]),
            color=alt.Color("state:N", scale=colours, legend=None),
        )
    )
    st.altair_chart(chart, use_container_width=True, key=key("chart"))
