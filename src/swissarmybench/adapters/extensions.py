"""The installed extensions: the entry points under `swissarmybench.extensions`, read once at start.

An extension's package declares, in its pyproject:

    [project.entry-points."swissarmybench.extensions"]
    accounting = "swissarmybench_accounting:describe"

where `describe` is a dict, or a function giving one: {"id", "name", "description", "version", "adds"}.
SWISSARMYBENCH_EXTENSIONS (ids, comma separated) treats more as installed: tests and development only.
"""

from __future__ import annotations

import importlib.metadata
import os
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from swissarmybench.domain import extensions as rules
from swissarmybench.domain.extensions import Found


def _entry_points() -> Iterable[Any]:
    return importlib.metadata.entry_points(group=rules.GROUP)


def discover(
    environ: Mapping[str, str] | None = None, entry_points: Callable[[], Iterable[Any]] = _entry_points
) -> dict[str, Found]:
    """Every installed extension by its id; one that fails to load is left out (the app starts anyway)."""
    found: dict[str, Found] = {}
    try:
        points = list(entry_points())
    except Exception:  # a broken install's metadata: no extensions rather than no app
        points = []
    for point in points:
        try:
            value = point.load()
            dist = getattr(point, "dist", None)
            said = rules.describe(
                str(point.name),
                value,
                str(getattr(dist, "name", "") or ""),
                str(getattr(dist, "version", "") or ""),
            )
        except Exception:  # noqa: S112 (an extension that cannot load is not installed)
            continue
        if said is not None:
            found.setdefault(said.id, said)
    for ident in rules.from_env((environ if environ is not None else os.environ).get(rules.ENV)):
        found.setdefault(ident, Found(id=ident))
    return found
