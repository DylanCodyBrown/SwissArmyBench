"""A Power BI dataset's queries read from its file (domain/m_files.py the rules; the owner, 2026-11-27: "those
data sets can all be imported into one power query file"): the files only, never a row.

  .pbit   a zip: its DataModelSchema part (the tabular model as JSON, UTF-16)
  .pbip   a project: the <Name>.SemanticModel (or .Dataset) folder beside it, its definition/ TMDL files, else
          its model.bim
  .pbix   a zip: its DataModelSchema when it has one, else pbixray's power_query and m_parameters frames (the
          model is compressed; pbixray is the Power BI extension's own package, imported only here and only
          when a .pbix is read)
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from swissarmybench.domain import m_files as rules

MAX_PART_BYTES = 64 * 1024 * 1024
_MODEL_FOLDERS = (".SemanticModel", ".Dataset")


def _schema_text(raw: bytes) -> str:
    """A model's JSON part as text: UTF-16 as Power BI Desktop writes it, else UTF-8."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(raw) > 1 and raw[1:2] == b"\x00"):
        return raw.decode("utf-16", "replace").lstrip("﻿")
    return raw.decode("utf-8-sig", "replace")


def _zip_part(file: Path, part: str) -> bytes | None:
    try:
        with zipfile.ZipFile(file) as archive:
            if part not in archive.namelist():
                return None
            if archive.getinfo(part).file_size > MAX_PART_BYTES:
                raise rules.ImportError_(f"{file.name}'s model is too large to read here.")
            return archive.read(part)
    except zipfile.BadZipFile:
        raise rules.ImportError_(f"{file.name} is not a Power BI file (it is not a zip).") from None


def _records(frame: Any) -> list[dict[str, Any]]:
    try:
        return list(frame.to_dict("records")) if frame is not None else []
    except Exception:  # an older pbixray's shape: nothing rather than a failure
        return []


def _from_pbix(file: Path) -> rules.DatasetQueries:
    schema = _zip_part(file, "DataModelSchema")
    if schema is not None:
        return rules.from_schema(_schema_text(schema), file.stem)
    try:
        from pbixray import PBIXRay  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        raise rules.ImportError_(
            "Reading a .pbix needs pbixray (the Power BI extension installs it): save the report as a "
            "template (.pbit) or a project (.pbip) to import it without."
        ) from None
    try:
        model: Any = PBIXRay(str(file))
    except Exception as error:  # pbixray refuses a file it cannot decode
        first = str(error).splitlines()[0][:160] if str(error) else type(error).__name__
        raise rules.ImportError_(f"pbixray could not read {file.name}: {first}") from None
    return from_pbixray(model, file.stem)


def from_pbixray(model: Any, name: str) -> rules.DatasetQueries:
    """pbixray's frames (power_query: TableName, Expression; m_parameters: ParameterName, Expression)."""
    queries = [
        (str(r.get("TableName") or ""), str(r.get("Expression") or ""))
        for r in _records(getattr(model, "power_query", None))
    ]
    parameters = [
        (str(r.get("ParameterName") or ""), str(r.get("Expression") or ""))
        for r in _records(getattr(model, "m_parameters", None))
    ]
    return rules.from_frames(name, queries, parameters)


def _from_pbip(file: Path) -> rules.DatasetQueries:
    folder = file.parent if file.is_file() else file
    name = file.stem if file.is_file() else file.name.rsplit(".", 1)[0]
    if folder.name.endswith(_MODEL_FOLDERS):
        models = [folder]
    else:
        models = sorted(p for p in folder.iterdir() if p.is_dir() and p.name.endswith(_MODEL_FOLDERS))
    named = [m for m in models if m.name.rsplit(".", 1)[0].casefold() == name.casefold()] or models
    if not named:
        raise rules.ImportError_(f"No semantic model folder (<name>.SemanticModel) is beside {file.name}.")
    model = named[0]
    definition = model / "definition"
    if definition.is_dir():
        files = {
            p.relative_to(definition).as_posix(): p.read_text(encoding="utf-8-sig", errors="replace")
            for p in sorted(definition.rglob("*.tmdl"))
            if p.stat().st_size <= MAX_PART_BYTES
        }
        return rules.from_tmdl(files, model.name.rsplit(".", 1)[0])
    bim = model / "model.bim"
    if bim.is_file():
        return rules.from_schema(_schema_text(bim.read_bytes()), model.name.rsplit(".", 1)[0])
    raise rules.ImportError_(f"{model.name} holds no definition/ folder and no model.bim.")


def read(path: str) -> rules.DatasetQueries:
    """The queries of the Power BI file (or project folder) at `path`."""
    file = Path(path).expanduser()
    if file.is_dir():
        return _from_pbip(file)
    if not file.is_file():
        raise FileNotFoundError(f"{file.name} is not there.")
    suffix = file.suffix.lower()
    if suffix == ".pbip":
        return _from_pbip(file)
    if suffix == ".pbit":
        schema = _zip_part(file, "DataModelSchema")
        if schema is None:
            raise rules.ImportError_(f"{file.name} holds no model (no DataModelSchema part).")
        return rules.from_schema(_schema_text(schema), file.stem)
    if suffix == ".pbix":
        return _from_pbix(file)
    raise rules.ImportError_("Pick a Power BI file: a .pbix, a .pbit or a .pbip.")
