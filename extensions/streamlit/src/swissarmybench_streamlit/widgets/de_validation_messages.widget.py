# /// swissarmybench-widget
# format = 1
# name = "de_validation_messages"
# description = "Each cell that breaks its rules, by row"
# framework = "streamlit"
# group = "Data"
# pack = "Data entry"
# tags = []
# size = [6, 4]
# min_size = [3, 2]
# ///
import pandas as pd
import streamlit as st
from sab_canvas import In, Table, problem, sample

# The table to check (empty: made-up sample data)
table_name: In[Table] = None
# The rules: each a column and what it must be (required, type: text | number | date, min, max, choices, pattern)
rules = [
    {"column": "product_name", "required": True},
    {"column": "unit_price", "type": "number", "min": 1, "max": 50},
    {
        "column": "category",
        "choices": ["Lighting", "Storage", "Textiles", "Planters", "Garden tools", "Hand tools", "Paper"],
    },
    {"column": "sku", "pattern": "^LG-[0-9]{6}$"},
]
# How many messages at most
rows: int = 50  # 1..1000
all_good = "Every row passes its rules."


def _problems(frame, rules):
    """Each cell that breaks a rule: its row (from 1), column, value and the problem in words."""
    import re

    found = []
    for rule in rules:
        column = rule.get("column")
        if column not in frame.columns:
            found.append({"row": None, "column": column, "value": None, "problem": "is not in the table"})
            continue
        for at, value in frame[column].items():
            empty = value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""
            said = None
            if empty:
                said = "is required" if rule.get("required") else None
            elif rule.get("type") == "number" and pd.isna(
                pd.to_numeric(pd.Series([value]), errors="coerce")[0]
            ):
                said = "is not a number"
            elif rule.get("type") == "date" and pd.isna(
                pd.to_datetime(pd.Series([value]), errors="coerce")[0]
            ):
                said = "is not a date"
            elif rule.get("choices") and str(value) not in [str(c) for c in rule["choices"]]:
                said = "is not one of the choices"
            elif rule.get("pattern") and not re.fullmatch(str(rule["pattern"]), str(value)):
                said = "does not match its pattern"
            else:
                number = pd.to_numeric(pd.Series([value]), errors="coerce")[0]
                if "min" in rule and not pd.isna(number) and number < rule["min"]:
                    said = f"is under {rule['min']}"
                elif "max" in rule and not pd.isna(number) and number > rule["max"]:
                    said = f"is over {rule['max']}"
            if said:
                found.append({"row": int(at) + 1, "column": column, "value": str(value), "problem": said})
    return found


frame = (table_name if table_name is not None else sample(kind="products")).reset_index(drop=True)
found = _problems(frame, rules)
if not found:
    st.success(all_good)
else:
    bad_rows = len({p["row"] for p in found if p["row"] is not None})
    st.markdown(f"**{len(found)} problems in {bad_rows} of {len(frame)} rows**")
    for problem in found[: int(rows)]:
        where = f"Row {problem['row']}, " if problem["row"] is not None else ""
        st.markdown(f":red[{where}{problem['column']}: {problem['value'] or ''} {problem['problem']}.]")
