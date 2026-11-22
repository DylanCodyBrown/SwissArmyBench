"""What an update would lose (services/updates.py what_is_open) on fakes, and the local sandbox API's
address put in an environment (adapters/variables.py publish_api) on a plain dict (craft review, item 8)."""

from __future__ import annotations

import asyncio
from typing import Any

from swissarmybench.adapters.variables import publish_api
from swissarmybench.services.updates import what_is_open

TABLES = [{"grid": "g1", "name": "orders"}]


def _ask(answer: Any) -> Any:
    async def ask() -> Any:
        if isinstance(answer, Exception):
            raise answer
        return answer

    return ask


def test_no_workbench_window_lists_the_tables_and_kernels_and_what_extensions_hold() -> None:
    found = asyncio.run(
        what_is_open(lambda: TABLES, lambda: False, _ask({}), lambda: ["Sales app"], lambda: 2)
    )
    assert found == {"tables": TABLES, "documents": [], "unsaved": ["Sales app"], "kernels": 2}


def test_the_window_s_documents_and_their_unsaved_titles_once() -> None:
    listed = {
        "documents": [
            {"index": 0, "title": "data.ipynb", "kind": "notebook", "unsaved_changes": True},
            {"index": 1, "title": "load.py", "kind": "script", "unsaved_changes": False},
            {"index": 2, "title": "orders", "kind": "table", "unsaved_changes": True},
        ]
    }
    found = asyncio.run(
        what_is_open(lambda: [], lambda: True, _ask(listed), lambda: ["data.ipynb"], lambda: 0)
    )
    assert [d["title"] for d in found["documents"]] == ["data.ipynb", "load.py"]
    assert found["unsaved"] == ["data.ipynb"]


def test_a_window_that_does_not_answer_lists_nothing() -> None:
    found = asyncio.run(what_is_open(lambda: [], lambda: True, _ask(TimeoutError()), lambda: [], lambda: 0))
    assert found["documents"] == []


def test_publish_puts_the_address_in_and_takes_a_name_not_given_out() -> None:
    environ = {"SAB_API_KEY": "old", "PATH": "/bin"}
    publish_api({"SAB_API_URL": "http://127.0.0.1:9", "SAB_API_BASE": "/api"}, environ)
    assert environ == {"PATH": "/bin", "SAB_API_URL": "http://127.0.0.1:9", "SAB_API_BASE": "/api"}
    publish_api({}, environ)
    assert environ == {"PATH": "/bin"}
