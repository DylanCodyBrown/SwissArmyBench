"""Which Python cells use Streamlit (docs/ideas.md, the Streamlit canvas, 2026-11-15).

There is no Streamlit kind of cell: any Python cell can go on a Streamlit app's canvas. A cell that
CALLS Streamlit is drawn live in its cell and does not run in the kernel (Streamlit code in a kernel
only warns). The rule, by Python's own parser:

  a call through Streamlit's name     `st.metric(...)`, `st.sidebar.selectbox(...)`: `st` is the name
                                      every page has, or the name the cell itself imports streamlit
                                      under (`import streamlit as sl` -> `sl.write(...)`)
  a call of a name from streamlit     `from streamlit import metric` -> `metric(...)`
  not an import alone                 `import streamlit as st` beside `import pandas as pd` draws
                                      nothing, and the kernel still needs the other names
  not another `st`                    a cell (or, the caller says, a document) that gives `st` another
                                      value (`from scipy import stats as st`, `st = ...`) does not mean
                                      Streamlit by it

Standard library only: the client (a kernel's Run file) reads a script's cells by the same rule.
"""

from __future__ import annotations

import ast
from functools import lru_cache

USUAL: str = "st"


def _parsed(code: str) -> ast.Module | None:
    try:
        return ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return None


def _is_streamlit(module: str | None) -> bool:
    return module == "streamlit" or (module or "").startswith("streamlit.")


@lru_cache(maxsize=4096)
def other_st(code: str) -> bool:
    """The code gives `st` a value that is not Streamlit (another module, or anything assigned)."""
    tree = _parsed(code)
    if tree is None:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                if bound == USUAL and not _is_streamlit(alias.name):
                    return True
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if (alias.asname or alias.name) == USUAL and not _is_streamlit(node.module):
                    return True
        elif isinstance(node, ast.Name) and node.id == USUAL and isinstance(node.ctx, ast.Store):
            return True
        elif isinstance(node, ast.arg) and node.arg == USUAL:
            return True
    return False


def _root(node: ast.expr) -> str | None:
    """The name an attribute chain starts from: `st` for `st.sidebar.selectbox`."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


@lru_cache(maxsize=4096)
def _uses(code: str, usual: bool) -> bool:
    tree = _parsed(code)
    if tree is None:
        return False
    modules: set[str] = set()  # the names streamlit itself has here
    members: set[str] = set()  # the names imported from it
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_streamlit(alias.name):
                    modules.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and _is_streamlit(node.module):
            members.update(alias.asname or alias.name for alias in node.names)
    if usual and not other_st(code):
        modules.add(USUAL)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and _root(func) in modules | members:
            return True
        if isinstance(func, ast.Name) and func.id in members:
            return True
    # `with st.sidebar:` and `with st.container():` draw too; the first is no call.
    for node in ast.walk(tree):
        if isinstance(node, ast.With | ast.AsyncWith):
            for item in node.items:
                if isinstance(item.context_expr, ast.Attribute) and _root(item.context_expr) in modules:
                    return True
    return False


def uses_streamlit(code: str, usual: bool = True) -> bool:
    """The code calls Streamlit. `usual` false: the document gives `st` another value somewhere, so
    only a name the code itself imports streamlit under counts. Code that is not whole Python yet
    does not (it is still being typed)."""
    return _uses(code, usual)


def usual_name(codes: list[str] | tuple[str, ...]) -> bool:
    """Whether `st` means Streamlit in a document: true unless one of its cells gives `st` another value."""
    return not any(other_st(code) for code in codes)
