"""Structures' files and formats (services/structures.py; the rules are domain/structures.py).

files    a structure's file read (50 MB at most, UTF-8) and written whole or not at all (a file
         beside it, then moved into place); a folder's structure files listed
codecs   JSON, XML and TOML by the domain's rules; YAML by PyYAML when this Python has it (it is not
         the app's dependency: without it, the one missing-package answer, which the page's prompt
         offers to install)
table    a list of records as an Arrow table for Open as grid (a column of mixed kinds as text)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from swissarmybench.domain import structures as rules
from swissarmybench.domain.packages import MissingPackagesError, missing_packages
from swissarmybench.domain.structures import StructureError


class StructureFiles:
    def full(self, path: str) -> str:
        file = Path(path).expanduser()
        if not file.is_file():
            raise FileNotFoundError(f"{path[:300]} is not a file.")
        return str(file.resolve())

    def read(self, path: str) -> str:
        file = Path(path)
        if file.stat().st_size > rules.MAX_CHARS:
            raise StructureError(f"{file.name} is too big (50 MB at most).")
        try:
            return file.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise StructureError(f"{file.name} is not text (UTF-8).") from None

    def write(self, path: str, text: str) -> None:
        file = Path(path).expanduser()
        if not file.parent.is_dir():
            file.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=f".{file.stem}-", suffix=".saving", dir=file.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
                out.write(text)
            os.replace(temporary, file)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def join(self, folder: str, name: str) -> str:
        return str(Path(folder) / name)

    def exists(self, path: str) -> bool:
        return Path(path).is_file()

    def listing(self, folder: str) -> list[tuple[str, int, float]]:
        root = Path(folder)
        if not root.is_dir():
            return []
        found = []
        for file in sorted(root.iterdir(), key=lambda f: f.name.casefold()):
            if file.is_file() and not file.name.startswith(".") and rules.format_of(file.name):
                stat = file.stat()
                found.append((file.name, stat.st_size, stat.st_mtime))
        return found

    def inside(self, path: str, folder: str) -> bool:
        try:
            Path(path).resolve().relative_to(Path(folder).resolve())
        except ValueError:
            return False
        return True

    def relative(self, path: str, folder: str) -> str:
        return Path(path).resolve().relative_to(Path(folder).resolve()).as_posix()


def _yaml() -> Any:
    try:
        import yaml  # type: ignore[import-untyped]  # optional: PyYAML is not a dependency of the app
    except ImportError:
        raise MissingPackagesError(
            missing_packages("Reading and writing YAML", ["PyYAML"], sys.executable, own=True)
        ) from None
    return yaml


class Codecs:
    def parse(self, text: str, fmt: str) -> Any:
        if fmt != "yaml":
            return rules.parse(text, fmt)
        yaml = _yaml()
        if len(text) > rules.MAX_CHARS:
            raise StructureError("The document is too big (50 MB at most).")
        try:
            found = list(yaml.safe_load_all(text))
        except yaml.YAMLError as error:
            mark = getattr(error, "problem_mark", None)
            where = f"line {mark.line + 1}, column {mark.column + 1}: " if mark is not None else ""
            problem = getattr(error, "problem", None) or str(error).splitlines()[0]
            raise StructureError(f"Not YAML: {where}{problem}.") from None
        value = found[0] if len(found) == 1 else found
        return json.loads(json.dumps(value, default=str))  # dates as text, as JSON holds them

    def dump(self, value: Any, fmt: str) -> str:
        if fmt != "yaml":
            return rules.dump(value, fmt)
        yaml = _yaml()
        return str(yaml.safe_dump(value, sort_keys=False, allow_unicode=True, default_flow_style=False))


def rows_to_table(rows: list[dict[str, Any]]) -> Any:
    """Records as an Arrow table: every key a column (in the order first met), a column whose values
    are of more than one kind (numbers and text) as text."""
    import pyarrow as pa

    columns: dict[str, list[Any]] = {}
    for n, row in enumerate(rows):
        for key in row:
            if key not in columns:
                columns[key] = [None] * n
        for key, values in columns.items():
            values.append(row.get(key))
    arrays = {}
    for key, values in columns.items():
        kinds = {type(v) for v in values if v is not None}
        try:
            if not kinds:
                arrays[key] = pa.array(values, type=pa.string())
            elif kinds <= {int, float} or kinds in ({bool}, {str}):
                arrays[key] = pa.array(values)
            else:
                raise ValueError("mixed")
        except (ValueError, OverflowError, pa.ArrowException):
            arrays[key] = pa.array([None if v is None else _text(v) for v in values], type=pa.string())
    return pa.table(arrays)


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
