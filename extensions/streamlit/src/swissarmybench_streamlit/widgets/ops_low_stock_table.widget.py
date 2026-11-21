# /// swissarmybench-widget
# format = 1
# name = "ops_low_stock_table"
# description = "The items at or under their reorder point, most short first"
# framework = "streamlit"
# group = "Data"
# pack = "Operations"
# tags = []
# size = [6, 4]
# min_size = [3, 2]
# ///
import pandas as pd
import streamlit as st
from sab_canvas import table

# The stock table (empty: made-up sample data)
table_name = ""  # table
name_column = "product_name"  # column of table_name
on_hand_column = "on_hand"  # column of table_name
reorder_column = "reorder_point"  # column of table_name
on_order_column = "on_order"  # column of table_name
# How many rows at most
rows: int = 20  # 1..500
# Leave out what is already on order
hide_on_order = False


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
    low = frame[on_hand <= reorder].assign(short_by=(reorder - on_hand)[on_hand <= reorder])
    if hide_on_order and on_order_column in low.columns:
        low = low[pd.to_numeric(low[on_order_column], errors="coerce").fillna(0) <= 0]
    low = low.sort_values("short_by", ascending=False).head(int(rows))
    st.caption(f"{len(low)} items at or under their reorder point")
    st.dataframe(
        low,
        hide_index=True,
        use_container_width=True,
        column_config={
            "short_by": st.column_config.ProgressColumn(
                "Short by", min_value=0, max_value=float(reorder.max() or 1), format="%d"
            )
        },
    )
