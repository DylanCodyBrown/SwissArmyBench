"""What the kernel-side helpers share about a Python value and the namespace it lives in: a value's type
by name, whether it is a table (pandas, polars, Arrow), and the namespace of the running IPython (else
__main__'s). Standard library only.

(client/lineage_values.py keeps its own copies: a live Streamlit page carries it as a file of its own.)
"""

from __future__ import annotations

import sys
from typing import Any


def type_name(value: Any) -> str:
    """`int`, `pandas.DataFrame`: a builtin's bare, any other with its top-level module."""
    kind = type(value)
    module = kind.__module__.split(".")[0]
    return kind.__qualname__ if module == "builtins" else f"{module}.{kind.__qualname__}"


def is_table(value: Any) -> bool:
    """A DataFrame-like table (pandas, polars, Arrow): what the grid opens, sab.push takes and DuckDB reads
    by its variable's name."""
    module = type(value).__module__.split(".")[0]
    try:
        return module in ("pandas", "polars", "pyarrow") and hasattr(value, "columns")
    except Exception:  # a property that raises something other than AttributeError
        return False


def namespace() -> dict[str, Any]:
    """The user's names: the running IPython's, else __main__'s."""
    ipython = sys.modules.get("IPython")
    shell = ipython.get_ipython() if ipython is not None else None
    if shell is not None:
        return shell.user_ns  # type: ignore[no-any-return]
    main = sys.modules.get("__main__")
    return vars(main) if main is not None else {}
