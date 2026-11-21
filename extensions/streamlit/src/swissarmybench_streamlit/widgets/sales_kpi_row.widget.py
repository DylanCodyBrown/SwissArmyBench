# /// swissarmybench-widget
# format = 1
# name = "sales_kpi_row"
# description = "Revenue, units, average price and margin, with the change on the month before"
# framework = "streamlit"
# group = "Data"
# pack = "Sales dashboard"
# tags = []
# size = [12, 2]
# min_size = [6, 1]
# ///
import pandas as pd
import streamlit as st
from sab_canvas import In, Table, sample

# The table to show (empty: made-up sample data)
table_name: In[Table] = None
date_column = "month"  # column of table_name
revenue_column = "revenue"  # column of table_name
units_column = "units"  # column of table_name
margin_column = "margin"  # column of table_name
currency = "€"
# The filter bar's picks (wired by itself to the page's sales_filter_bar; not wired: no filter)
sales_filter: In[dict] = None


def _filtered(frame):
    """The filter bar's picks applied where this table has those columns."""
    picked = sales_filter or {}
    column = picked.get("region_column")
    if column in frame.columns and picked.get("regions"):
        frame = frame[frame[column].astype(str).isin([str(r) for r in picked["regions"]])]
    column = picked.get("date_column")
    if column in frame.columns and picked.get("start") and picked.get("end"):
        dates = pd.to_datetime(frame[column], errors="coerce")
        frame = frame[(dates >= pd.Timestamp(picked["start"])) & (dates <= pd.Timestamp(picked["end"]))]
    return frame


frame = _filtered(table_name if table_name is not None else sample())
dates = pd.to_datetime(frame[date_column], errors="coerce") if date_column in frame.columns else None
last = previous = frame.iloc[0:0]
if dates is not None and dates.notna().any():
    months = dates.dt.to_period("M")
    latest = months.max()
    last, previous = frame[months == latest], frame[months == latest - 1]


def _total(rows, column):
    return float(pd.to_numeric(rows[column], errors="coerce").sum()) if column in rows.columns else 0.0


def _delta(now, before):
    return f"{(now - before) / before:+.1%} on the month before" if before else None


revenue, units = _total(frame, revenue_column), _total(frame, units_column)
first, second, third, fourth = st.columns(4)
first.metric(
    "Revenue",
    f"{currency} {revenue:,.0f}",
    _delta(_total(last, revenue_column), _total(previous, revenue_column)),
)
second.metric("Units", f"{units:,.0f}", _delta(_total(last, units_column), _total(previous, units_column)))
third.metric("Average price", f"{currency} {revenue / units:,.2f}" if units else "—")
if margin_column in frame.columns and len(frame):
    fourth.metric("Margin", f"{pd.to_numeric(frame[margin_column], errors='coerce').mean():.0%}")
else:
    fourth.metric("Margin", "—")
