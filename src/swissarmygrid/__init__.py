"""SwissArmyGrid is now Swiss Army Bench: `import swissarmybench as sab`. This package keeps the old name
working for one release, and the next release removes it.

`import swissarmygrid as sag` gives the new package's names (sag.push, sag.sql, sag.blade...), with a
DeprecationWarning naming the new import. Every module under the old name is the new one itself, not a
copy (`swissarmygrid.client.push_client is swissarmybench.client.push_client`), so old code, an old
notebook's imports and `python -m swissarmygrid.server` all run the one package.

Standard library only, like the plain client.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import warnings
from types import CodeType, ModuleType
from typing import Any

import swissarmybench as _new

OLD: str = "swissarmygrid"
NEW: str = "swissarmybench"
MESSAGE: str = (
    "swissarmygrid is now swissarmybench: write `import swissarmybench as sab`. "
    "The old name goes in the next release."
)


def _new_name(fullname: str) -> str:
    return NEW + fullname[len(OLD) :]


class _Renamed(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """`swissarmygrid.x.y` is `swissarmybench.x.y`: the same module object, under both names."""

    def find_spec(
        self, fullname: str, path: Any = None, target: ModuleType | None = None
    ) -> importlib.machinery.ModuleSpec | None:
        if not fullname.startswith(OLD + "."):
            return None
        real = importlib.util.find_spec(_new_name(fullname))
        if real is None:
            return None
        spec = importlib.util.spec_from_loader(
            fullname, self, origin=real.origin, is_package=real.submodule_search_locations is not None
        )
        return spec

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        return importlib.import_module(_new_name(spec.name))

    def exec_module(self, module: ModuleType) -> None:
        """Nothing to run: the module ran once, under its new name."""

    def get_code(self, fullname: str) -> CodeType | None:
        """For `python -m swissarmygrid.server`: runpy runs the new module's own code."""
        real = importlib.util.find_spec(_new_name(fullname))
        loader = real.loader if real is not None else None
        get_code = getattr(loader, "get_code", None)
        return get_code(_new_name(fullname)) if get_code is not None else None


if not any(isinstance(finder, _Renamed) for finder in sys.meta_path):
    sys.meta_path.insert(0, _Renamed())

__version__: str = _new.__version__
__all__ = list(_new.__all__)


def __getattr__(name: str) -> Any:
    return getattr(_new, name)


def __dir__() -> list[str]:
    return dir(_new)


warnings.warn(MESSAGE, DeprecationWarning, stacklevel=2)
