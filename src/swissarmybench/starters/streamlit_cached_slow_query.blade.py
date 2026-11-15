# /// swissarmybench-blade
# format = 1
# name = "Streamlit cached slow query"
# kind = "snippet"
# description = "A slow summary worked out once and kept (st.cache_data)"
# tags = ["streamlit", "interaction", "cache"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "Cached <<name>>"
# ///
snippet = r"""
# Cached slow query: a summary that takes a while to work out, worked out once and then kept.
#
# Makes: <<name: summary>>
#   <<table>>'s numbers added up for each <<column>>
# Reads: <<table>>
#   a table: an open one, or the rows a filter left
#
# Streamlit functions:
#   st.cache_data(ttl)    put over a function: its answer is kept for each set of arguments, so the
#                         next rerun with the same ones gets it at once instead of running it again
#   st.dataframe(table)   the table, sortable and scrollable
#
# What cache_data keeps, and when it forgets: one answer per set of arguments (here the rows and
# the column), for `ttl` seconds; it also forgets when the function's code changes. Different
# rows (a filter changed) are a new set of arguments: worked out once, then kept too.
import time

import pandas as pd
import streamlit as st


@st.cache_data(ttl=<<keep seconds: 600>>)
def _summary(rows: pd.DataFrame, column: str) -> pd.DataFrame:
    time.sleep(<<wait seconds: 1>>)  # stands in for a slow query or a slow file
    return rows.groupby(column, as_index=False).sum(numeric_only=True)


<<name>> = _summary(<<table>>, "<<column>>")
st.dataframe(<<name>>, hide_index=True)
"""
