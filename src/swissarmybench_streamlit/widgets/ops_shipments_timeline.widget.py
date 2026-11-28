# /// swissarmybench-widget
# format = 1
# name = "ops_shipments_timeline"
# description = "Each shipment from shipped to delivered, its promised day marked"
# framework = "streamlit"
# group = "Charts"
# pack = "Operations"
# tags = []
# size = [8, 5]
# min_size = [4, 3]
# ///
import datetime

import altair as alt
import pandas as pd
import streamlit as st
from sab_canvas import In, Table, key

# The shipments table (empty: made-up sample data)
table_name: In[Table] = None
id_column = "shipment_id"  # column of table_name
shipped_column = "shipped_on"  # column of table_name
delivered_column = "delivered_on"  # column of table_name
promised_column = "promised_on"  # column of table_name
status_column = "status"  # column of table_name
# How many of the latest shipments
rows: int = 20  # 1..200


def _sample():
    """Made-up shipments over three weeks (the shape of shipments)."""
    start = datetime.date(2026, 10, 5)
    carriers = ["Swiftpost", "Parcelwing", "Roadrunner Freight", "Kestrel Couriers"]
    rows = []
    for at in range(24):
        shipped = start + datetime.timedelta(days=at % 18)
        promised = shipped + datetime.timedelta(days=3 + at % 3)
        delivered = None if at % 7 == 6 else shipped + datetime.timedelta(days=1 + (at * 5) % 7)
        status = "In transit" if delivered is None else ("Late" if delivered > promised else "On time")
        rows.append(
            {
                "shipment_id": 5000 + at,
                "order_id": 81000 + at * 3,
                "carrier": carriers[at % 4],
                "shipped_on": shipped,
                "promised_on": promised,
                "delivered_on": delivered,
                "status": status,
            }
        )
    frame = pd.DataFrame(rows)
    for column in ("shipped_on", "promised_on", "delivered_on"):
        frame[column] = pd.to_datetime(frame[column])
    return frame


frame = table_name if table_name is not None else _sample()
needed = [id_column, shipped_column, promised_column]
missing = [c for c in needed if c not in frame.columns]
if missing:
    st.warning(f"Pick the shipment columns: {', '.join(missing)} is not in the table.")
else:
    shown = frame.copy()
    shown["start"] = pd.to_datetime(shown[shipped_column], errors="coerce")
    promised = pd.to_datetime(shown[promised_column], errors="coerce")
    delivered = (
        pd.to_datetime(shown[delivered_column], errors="coerce")
        if delivered_column in shown.columns
        else promised
    )
    shown["end"] = delivered.fillna(promised)
    shown["promised"] = promised
    shown["shipment"] = shown[id_column].astype(str)
    shown["state"] = shown[status_column].astype(str) if status_column in shown.columns else "Shipped"
    shown = shown.sort_values("start").tail(int(rows))
    bars = (
        alt.Chart(shown)
        .mark_bar(height=10)
        .encode(
            x=alt.X("start:T", title=None),
            x2="end:T",
            y=alt.Y("shipment:N", sort="-x", title=None),
            color=alt.Color("state:N", title=None),
            tooltip=["shipment", "start:T", "end:T", "promised:T", "state"],
        )
    )
    ticks = (
        alt.Chart(shown)
        .mark_tick(color="#444", thickness=2)
        .encode(x="promised:T", y=alt.Y("shipment:N", sort="-x"))
    )
    st.altair_chart(bars + ticks, use_container_width=True, key=key("chart"))
