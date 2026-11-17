"""Thin cells (docs/ideas.md, controllers, thin cells, 2026-11-15): a view cell that filters, groups or
joins a table is told so quietly, and Move to data.ipynb puts those lines into a named cell of data.ipynb,
leaving one line that reads them back. A filter on a widget's value is a controller's work and stays."""

from __future__ import annotations

import ast

from swissarmybench_streamlit.domain.thin_cells import model_work

VIEW = """# uses orders @cell2
# Sales by product
import numpy as np
import streamlit as st

# the totals, biggest first
sales_by_product = orders.groupby("product", as_index=False)["amount"].sum()
top = sales_by_product.nlargest(5, "amount")
logged = np.log1p(top["amount"])
st.bar_chart(top, x="product", y="amount")
st.write(logged)
"""


def test_a_view_that_groups_a_table_moves_those_lines_to_data_ipynb() -> None:
    move = model_work(VIEW, ["orders"], "Sales by product, sales.ipynb cell 4")
    assert move is not None
    assert move.names == ("sales_by_product", "top", "logged") and move.work == ("filter", "group")
    assert move.words == "Filters and groups a table: sales_by_product, top, logged"
    assert move.title == "sales_by_product"
    assert move.data == (
        "# From Sales by product, sales.ipynb cell 4\n"
        "import numpy as np\n"
        "# the totals, biggest first\n"
        'sales_by_product = orders.groupby("product", as_index=False)["amount"].sum()\n'
        'top = sales_by_product.nlargest(5, "amount")\n'
        'logged = np.log1p(top["amount"])\n'
    )
    assert move.cell == (
        "# uses orders @cell2\n"
        "# Sales by product\n"
        "import numpy as np\n"
        "import streamlit as st\n"
        "\n"
        "from data import sales_by_product, top, logged\n"
        'st.bar_chart(top, x="product", y="amount")\n'
        "st.write(logged)\n"
    )
    ast.parse(move.data)
    ast.parse(move.cell)


def test_a_join_and_a_filter_on_a_table_are_model_work_too() -> None:
    joined = "import streamlit as st\nboth = orders.merge(customers, on='id')\nst.dataframe(both)"
    assert model_work(joined, ["orders", "customers"]).work == ("join",)  # type: ignore[union-attr]
    picked = "import streamlit as st\nbig = orders[orders['amount'] > 100]\nst.dataframe(big)"
    assert model_work(picked, ["orders"]).names == ("big",)  # type: ignore[union-attr]


def test_a_controllers_work_a_plain_cell_and_lines_that_show_stay() -> None:
    # The filter reads the widget's pick: a controller's work, never moved.
    controller = """import streamlit as st
pick = st.selectbox("Region", ["North", "South"])
by_region = orders[orders["region"] == pick]
st.dataframe(by_region)
"""
    assert model_work(controller, ["orders"]) is None
    # A cell that shows nothing is the model already; nothing that works on a table is no hint.
    assert model_work("total = orders.groupby('region').sum()", ["orders"]) is None
    assert model_work("import streamlit as st\nst.dataframe(orders)", ["orders"]) is None
    # A name the cell gives again in a line that stays, or a helper of its own, stays.
    again = "import streamlit as st\nt = orders.groupby('r').sum()\nt = st.data_editor(t)"
    assert model_work(again, ["orders"]) is None
    own = "import streamlit as st\n_t = orders.groupby('r').sum()\nst.write(_t)"
    assert model_work(own, ["orders"]) is None
    # A name no table or data.py gives is not the model's to read.
    assert (
        model_work("import streamlit as st\nt = mystery.groupby('r').sum()\nst.write(t)", ["orders"]) is None
    )
    assert model_work("import streamlit as st\nt = orders.groupby(", ["orders"]) is None
