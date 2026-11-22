"""The composition root checks its own wiring at the end (craft review 2026-11-22, item 8): every part built
what it names, and every attribute a part sets on a service after it is built really was set."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from swissarmybench import bootstrap as root


class Service:
    def __init__(self) -> None:
        self.learned: Any = lambda: None  # a constructor's stand-in, as the services' own defaults are


def _built() -> Any:
    """A stand-in Built whose every field and every late-bound attribute is set."""
    b = SimpleNamespace(**{name: object() for name in root.Built.__annotations__})
    for path in root.LATE_BOUND:
        owner = b
        *parts, last = path.split(".")
        for part in parts:
            if not isinstance(getattr(owner, part, None), SimpleNamespace):
                setattr(owner, part, SimpleNamespace())
            owner = getattr(owner, part)
        setattr(owner, last, print)
    return b


def test_a_whole_wiring_passes() -> None:
    root._check_wired(_built())


def test_a_part_that_did_not_run_fails_at_start() -> None:
    b = _built()
    del b.sandbox
    with pytest.raises(RuntimeError, match="sandbox was not built"):
        root._check_wired(b)


def test_a_late_attribute_left_as_its_constructor_gave_it_fails_at_start() -> None:
    b = _built()
    b.local_api = Service()
    for name in ("target_ids", "targets"):
        setattr(b.local_api, name, print)
    with pytest.raises(RuntimeError, match=r"local_api\.learned was not set"):
        root._check_wired(b)
    b.local_api.learned = None
    with pytest.raises(RuntimeError, match=r"local_api\.learned was not set"):
        root._check_wired(b)
