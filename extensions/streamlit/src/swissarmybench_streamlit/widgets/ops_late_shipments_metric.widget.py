# /// swissarmybench-widget
# format = 1
# name = "ops_late_shipments_metric"
# description = "The share of shipments delivered late, against a target"
# framework = "streamlit"
# group = "Data"
# pack = "Operations"
# tags = []
# size = [3, 2]
# min_size = [2, 1]
# ///
import datetime

import pandas as pd
import streamlit as st
from sab_canvas import table

# The shipments table (empty: made-up sample data)
table_name = ""  # table
delivered_column = "delivered_on"  # column of table_name
promised_column = "promised_on"  # column of table_name
label = "Late shipments"
# The share of late shipments you aim to stay under
target: float = 0.1  # 0..1 step 0.01


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


frame = table(table_name) if table_name else _sample()
if delivered_column not in frame.columns or promised_column not in frame.columns:
    st.warning(f"Pick the shipment columns: {delivered_column} or {promised_column} is not in the table.")
else:
    delivered = pd.to_datetime(frame[delivered_column], errors="coerce")
    promised = pd.to_datetime(frame[promised_column], errors="coerce")
    done = delivered.notna()
    late = int((delivered[done] > promised[done]).sum())
    share = late / int(done.sum()) if done.any() else 0.0
    st.metric(
        label, f"{share:.1%}", f"{share - target:+.1%} against the {target:.0%} target", delta_color="inverse"
    )
    st.caption(f"{late} of {int(done.sum())} delivered shipments arrived after their promised day")
