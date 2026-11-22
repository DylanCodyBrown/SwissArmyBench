"""The error panel: the facts read in the kernel (client/kernel_errors.py) and the words for them
(domain/errors.py). Made-up code and data only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.client import kernel_errors
from swissarmybench.domain import errors


def _last_error(code: str, folder: Path) -> dict[str, Any]:
    """Run made-up code that fails, as a script would, and read the error as the kernel helper does."""
    script = folder / "made_up_script.py"
    script.write_text(code, encoding="utf-8")
    try:
        exec(compile(code, str(script), "exec"), {"__name__": "__main__"})  # noqa: S102 (the test's own code)
    except BaseException as error:
        if error.__traceback__ is not None and not isinstance(error, SyntaxError):
            error.__traceback__ = error.__traceback__.tb_next  # this helper's own frame
        sys.last_exc = error  # what IPython sets after showing an error
        sys.last_value = error
    detail = json.loads(kernel_errors.detail())
    return dict(detail)


# ===== the words =====


def test_a_missing_name_offers_its_import_or_a_close_name() -> None:
    told = errors.explain(
        {
            "type": "NameError",
            "message": "name 'pd' is not defined",
            "facts": {"name": "pd", "candidates": []},
        }
    )
    assert told["fixes"][0] == {
        "kind": "import",
        "title": "Add `import pandas as pd`",
        "line": "import pandas as pd",
    }
    told = errors.explain(
        {
            "type": "NameError",
            "message": "name 'totl' is not defined",
            "facts": {"name": "totl", "candidates": ["total"]},
        }
    )
    assert {"kind": "replace", "title": "Use 'total'", "target": "totl", "text": "total"} in told["fixes"]
    assert told["fixes"][-1]["kind"] == "define"
    assert "has not run yet" in told["explanation"]


def test_a_missing_module_is_installed_by_its_package_name() -> None:
    told = errors.explain(
        {
            "type": "ModuleNotFoundError",
            "message": "No module named 'sklearn'",
            "facts": {"module": "sklearn.linear_model"},
        }
    )
    assert told["fixes"] == [
        {
            "kind": "install",
            "title": "Install 'scikit-learn' here",
            "package": "scikit-learn",
            "module": "sklearn",
        }
    ]
    assert "'scikit-learn'" in told["explanation"]
    # The kernel's Python known, the run says it in the one missing-package shape (the prompt's).
    detail = {"chain": [{"type": "ModuleNotFoundError", "message": "x", "facts": {"module": "sklearn"}}]}
    assert errors.explain_detail(detail, "/envs/shop/bin/python")["missing"] == {
        "feature": "This code",
        "packages": ["scikit-learn"],
        "python": "/envs/shop/bin/python",
        "command": "uv pip install --python /envs/shop/bin/python scikit-learn",
    }
    assert "missing" not in errors.explain_detail(detail)


def test_a_missing_column_lists_the_columns_and_the_close_one() -> None:
    facts = {
        "key": "'amont'",
        "table": True,
        "keys": ["order_id", "amount", "region"],
        "candidates": ["amount"],
    }
    told = errors.explain({"type": "KeyError", "message": "'amont'", "facts": facts})
    assert (
        told["explanation"]
        == "The table has no column 'amont'. Its columns are 'order_id', 'amount' and 'region'."
    )
    assert told["fixes"] == [
        {"kind": "replace", "title": "Use 'amount'", "target": "amont", "text": "amount"}
    ]


def test_none_and_files_are_said_plainly() -> None:
    told = errors.explain(
        {
            "type": "AttributeError",
            "message": "'NoneType' object has no attribute 'head'",
            "facts": {"name": "head", "is_none": True},
        }
    )
    assert told["explanation"].startswith("The value is None")
    told = errors.explain(
        {
            "type": "FileNotFoundError",
            "message": "No such file",
            "facts": {"full_path": "/data/sales.csv", "cwd": "/home/ana"},
        }
    )
    assert "/data/sales.csv" in told["explanation"] and "/home/ana" in told["explanation"]


def test_sql_errors_point_at_their_place_and_offer_the_candidates() -> None:
    message = (
        'Binder Error: Referenced column "amont" not found in FROM clause!\n'
        'Candidate bindings: "orders.amount", "orders.order_id"\n\n'
        "LINE 1: SELECT sum(amont) FROM orders\n"
        "                   ^"
    )
    where = errors.sql_position(message)
    assert where is not None
    assert (where["line"], where["col"], where["missing"]) == (1, 12, "amont")
    assert where["candidates"] == ["amount", "order_id"]
    told = errors.explain({"type": "UsageError", "message": message, "facts": {}})
    assert told["fixes"][0] == {
        "kind": "replace",
        "title": "Use 'amount'",
        "target": "amont",
        "text": "amount",
    }


def test_where_names_your_own_code() -> None:
    detail = {
        "chain": [
            {
                "type": "ZeroDivisionError",
                "message": "division by zero",
                "facts": {},
                "frames": [
                    {"where": "cell", "cell": 3, "line": 2},
                    {"where": "library", "file": "/x/pandas/core.py", "line": 9},
                ],
                "your_frame": 0,
            }
        ]
    }
    told = errors.explain_detail(detail)
    assert told["where"] == "cell [3], line 2"
    assert told["chain"][0]["explanation"].startswith("A number was divided by zero")


# ===== the facts, read in the kernel's Python =====


def test_the_failing_expression_its_columns_and_values(tmp_path: Path) -> None:
    found = _last_error(
        "rates = {'north': 2}\ndef share(region):\n    return 10 / rates[region]\n\nshare('south')\n",
        tmp_path,
    )
    last = found["chain"][-1]
    assert last["type"] == "KeyError" and last["message"] == "'south'"
    frames = last["frames"]
    assert [f["function"] for f in frames] == ["<module>", "share"]
    inner = frames[last["your_frame"]]
    assert inner["where"] == "file" and inner["line"] == 3
    assert inner["code"] == "    return 10 / rates[region]"
    assert (inner["col"], inner["end_col"]) == (17, 30)  # rates[region], 1-based as the editor counts
    assert {"name": "region", "repr": "'south'", "type": "str", "table": False} in inner["locals"]
    assert last["facts"]["keys"] == ["north"]


def test_a_chain_comes_cause_first(tmp_path: Path) -> None:
    found = _last_error(
        "try:\n    int('x')\nexcept ValueError as e:\n"
        "    raise RuntimeError('could not read the count') from e\n",
        tmp_path,
    )
    assert [e["type"] for e in found["chain"]] == ["ValueError", "RuntimeError"]
    assert found["chain"][0]["relation"] == "cause"


def test_a_name_error_finds_the_close_name(tmp_path: Path) -> None:
    found = _last_error("total = 3\nprint(totl)\n", tmp_path)
    assert found["chain"][-1]["facts"]["candidates"][:1] == ["total"]


@pytest.mark.parametrize("line", ["x = (1 +\n", "for i in range(3)\n    pass\n"])
def test_a_syntax_error_says_where_python_stopped(line: str, tmp_path: Path) -> None:
    syntax = _last_error(line, tmp_path)["chain"][-1]["syntax"]
    assert syntax["line"] >= 1 and syntax["col"] >= 1


def test_columns_count_as_the_editor_does_past_wide_characters() -> None:
    assert (
        kernel_errors._utf16_column("x = '€😀' + 1", 13) == 10
    )  # bytes 13 -> after the emoji (two UTF-16 units)


def test_a_loc_lookup_lists_the_tables_columns(tmp_path: Path) -> None:
    pytest.importorskip("pandas")
    found = _last_error(
        "import pandas as pd\norders = pd.DataFrame({'region': ['North'], 'amount': [10.5]})\n"
        "orders.loc[orders['region'] == 'North', 'amont']\n",
        tmp_path,
    )
    facts = found["chain"][-1]["facts"]
    assert facts["table"] is True and facts["candidates"] == ["amount"]
    assert [e["type"] for e in found["chain"]] == ["KeyError"]  # pandas' own inner KeyError left out


# ===== a DuckDB SQL cell naming a table it cannot see (feel-a, 2026-11-19) =====

MISSING_TABLE = (
    "DuckDB: CatalogException: Catalog Error: Table with name orders does not exist!\n"
    'Did you mean "pg_prepared_statements"?'
)


def test_duckdbs_missing_table_wording_is_caught_and_a_system_guess_dropped() -> None:
    assert errors.missing_table(MISSING_TABLE) == "orders"
    assert errors.missing_table("Catalog Error: Table with name My Orders does not exist!") == "My Orders"
    assert errors.missing_table('Table with name "s.orders" does not exist because schema "s" does not') == (
        "s.orders"
    )
    assert errors.missing_table("Binder Error: Referenced column x not found") is None
    where = errors.sql_position(MISSING_TABLE)
    assert where is not None and where["missing"] == "orders"
    assert "candidates" not in where  # pg_prepared_statements is DuckDB's own, not the user's
    told = errors.explain({"type": "UsageError", "message": MISSING_TABLE, "facts": {}})
    assert "pg_prepared_statements" not in told["message"]
    assert "Did you mean" not in told["message"] and told["message"].endswith("does not exist!")
    assert not any("pg_" in f["title"] for f in told["fixes"])
    assert "below" not in told["explanation"]
    assert "'orders'" in told["explanation"]


def test_a_close_name_of_the_users_own_stays_a_fix() -> None:
    message = 'Catalog Error: Table with name ordrs does not exist!\nDid you mean "orders"?'
    told = errors.explain({"type": "UsageError", "message": message, "facts": {}})
    assert told["fixes"][0] == {
        "kind": "replace",
        "title": "Use 'orders'",
        "target": "ordrs",
        "text": "orders",
    }
    assert 'Did you mean "orders"' in told["message"]


def test_a_table_open_in_grids_offers_its_table_cell() -> None:
    detail = {"chain": [{"type": "UsageError", "message": MISSING_TABLE, "facts": {}}]}
    told = errors.explain_detail(detail, open_tables=["Orders", "regions"])
    entry = told["chain"][-1]
    assert entry["fixes"][0] == {
        "kind": "table",
        "title": "Orders is open in Grids: add its table cell",
        "name": "Orders",
    }
    assert "open in Grids" in entry["explanation"]
    plain = errors.explain_detail(detail, open_tables=["regions"])["chain"][-1]
    assert not any(f["kind"] == "table" for f in plain["fixes"])
    # A Python error never offers a table cell.
    python = {"chain": [{"type": "NameError", "message": "name 'orders' is not defined", "facts": {}}]}
    told_python = errors.explain_detail(python, open_tables=["orders"])["chain"][-1]
    assert not any(f["kind"] == "table" for f in told_python["fixes"])


def test_the_rules_are_a_table_tried_in_order() -> None:
    """explain() is a list of rules, the first match says it (the craft review of 2026-11-22): a narrower
    rule stands before a wider one, the rules that read the message come last, and an error nobody wrote
    a rule for gets no explanation rather than a wrong one."""
    from swissarmybench.domain import errors

    def first(kind: str, message: str = "", **facts: object) -> int:
        seen = errors.Seen(kind, message, facts)
        return next((i for i, (matches, _) in enumerate(errors.RULES) if matches(seen)), -1)

    none_type = first("TypeError", "unsupported operand type(s) for +: 'NoneType' and 'int'")
    assert 0 <= none_type < first("TypeError", "can only concatenate str")
    assert first("ImportError") == -1 and first("ImportError", module="polars") >= 0  # only with its module
    assert first("UsageError") == len(errors.RULES) - 1  # the rules that read the message stand last
    assert first("SomethingNobodyKnows") == -1
    assert errors.explain({"type": "SomethingNobodyKnows", "message": "odd"})["explanation"] == ""
    assert errors.explain({"type": "KeyboardInterrupt"})["title"] == "Interrupted"
    # every call's fixes are its own: one call's are never another's
    one = errors.explain({"type": "ZeroDivisionError", "hint": "Did you mean: 'x'?", "facts": {"name": "y"}})
    two = errors.explain({"type": "ZeroDivisionError"})
    assert one["fixes"] and two["fixes"] == []
