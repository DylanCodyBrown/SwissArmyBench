# /// swissarmybench-widget
# format = 1
# name = "sales_revenue_trend"
# description = "Revenue by week, month or quarter as a line"
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
date_column = "month"  # column of table_name
value_column = "revenue"  # column of table_name
period = "month"  # choices: week, month, quarter
colour = "#1f77b4"
title = "Revenue by month"
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
if date_column not in frame.columns or value_column not in frame.columns:
    st.warning(f"Pick a date column and a value column: {date_column} or {value_column} is not in the table.")
else:
    code = {"week": "W", "month": "M", "quarter": "Q"}[period]
    when = pd.to_datetime(frame[date_column], errors="coerce").dt.to_period(code).dt.start_time
    totals = (
        pd.DataFrame({"period": when, "value": pd.to_numeric(frame[value_column], errors="coerce")})
        .groupby("period", as_index=False)["value"]
        .sum()
    )
    chart = (
        alt.Chart(totals, title=title or alt.Undefined)
        .mark_line(point=True, color=colour)
        .encode(
            x=alt.X("period:T", title=None),
            y=alt.Y("value:Q", title=value_column),
            tooltip=["period:T", "value:Q"],
        )
    )
    st.altair_chart(chart, use_container_width=True, key=key("chart"))
