# /// swissarmybench-widget
# format = 1
# name = "sales_region_map"
# description = "Revenue by region on a map"
# framework = "streamlit"
# group = "Charts"
# pack = "Sales dashboard"
# tags = []
# size = [6, 5]
# min_size = [3, 3]
# ///
import pandas as pd
import streamlit as st
from sab_canvas import table

# The table to show (empty: made-up sample data)
table_name = ""  # table
region_column = "region"  # column of table_name
latitude_column = "lat"  # column of table_name
longitude_column = "lon"  # column of table_name
value_column = "revenue"  # column of table_name
colour = "#d62728"
zoom: int = 4  # 1..15
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
needed = [region_column, latitude_column, longitude_column, value_column]
missing = [c for c in needed if c not in frame.columns]
if missing:
    st.warning(f"Pick the map's columns: {', '.join(missing)} is not in the table.")
else:
    places = (
        frame.assign(_value=pd.to_numeric(frame[value_column], errors="coerce"))
        .groupby(region_column, as_index=False)
        .agg(lat=(latitude_column, "mean"), lon=(longitude_column, "mean"), value=("_value", "sum"))
    )
    biggest = float(places["value"].max() or 1)
    places["size"] = 5000 + 45000 * places["value"] / biggest
    st.map(places, latitude="lat", longitude="lon", size="size", color=colour, zoom=int(zoom))
    st.caption(" · ".join(f"{r[region_column]}: {r['value']:,.0f}" for _, r in places.iterrows()))
