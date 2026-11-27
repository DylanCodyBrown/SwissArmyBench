# /// swissarmybench-blade
# format = 1
# name = "Streamlit metric with change"
# kind = "snippet"
# description = "One big number, this month's total, with its change from last month"
# tags = ["streamlit", "display", "metric"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>>"
# ///
snippet = r"""
# Metric with its change: the total of a column for the latest month, with its change from the
# month before (an arrow and a percent, green up and red down).
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.metric(label, value, delta)   a big number with its change under it
#
# A name that starts with _ is this piece's own: other pieces do not read it.
import pandas as pd
import streamlit as st

# Each month's total: the dates become months (2026-01), then the values are added up per month.
_months = pd.to_datetime(<<table>>["<<date column>>"]).dt.to_period("M")
_totals = <<table>>.groupby(_months)["<<value column>>"].sum()
_now = float(_totals.iloc[-1]) if len(_totals) else 0.0
_before = float(_totals.iloc[-2]) if len(_totals) > 1 else 0.0
# delta: the change. As text with a sign (+12.4%), Streamlit draws its arrow and colour from the sign.
st.metric(
    "<<label: Sales this month>>",
    f"{_now:,.0f}",
    delta=f"{(_now - _before) / _before:+.1%}" if _before else None,
)
"""
