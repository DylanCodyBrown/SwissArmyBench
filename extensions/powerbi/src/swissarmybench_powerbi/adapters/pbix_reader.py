"""A .pbix read with pbixray (the one way a .pbix is read: domain/pbix_file.py), its model's metadata and M
only
(the import, the card); a table's rows only when a table is read (the connection's own code does that, in its
child process). The file is never changed. pbixray is the extension's own dependency, imported here only.

A thin report (no model of its own) is told by its Connections part (a zip entry, JSON), read before pbixray.
`Reader` is the seam: tests hand the service a fake that answers the same records.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Protocol

from swissarmybench_powerbi.domain import pbix_file as rules


class Reader(Protocol):
    def __call__(self, path: str) -> rules.PbixModel: ...


def _records(frame: Any) -> list[dict[str, Any]]:
    try:
        return list(frame.to_dict("records")) if frame is not None else []
    except Exception:  # an older pbixray's shape: nothing rather than a failure
        return []


def _text(value: Any) -> str:
    return "" if value is None or (isinstance(value, float) and value != value) else str(value)


def read(path: str) -> rules.PbixModel:
    target = Path(path)
    if target.suffix.lower() != ".pbix":
        raise rules.PbixError("Use a .pbix file.")
    if not target.is_file():
        raise FileNotFoundError(f"{target.name} is not there.")
    try:
        with zipfile.ZipFile(target) as archive:
            names = set(archive.namelist())
            connections = (
                archive.read("Connections").decode("utf-8-sig", "replace") if "Connections" in names else ""
            )
            has_model = "DataModel" in names
    except zipfile.BadZipFile:
        raise rules.PbixError(f"{target.name} is not a Power BI file (it is not a zip).") from None
    if not has_model:
        dataset, workspace = rules.thin_target(connections)
        if dataset:
            return rules.PbixModel(target.stem, thin_dataset=dataset, thin_workspace=workspace)
        raise rules.PbixError(f"{target.name} holds no model and names no published dataset.")
    try:
        from pbixray import PBIXRay  # type: ignore[import-not-found]  # the extension's own dependency
    except ImportError:
        raise rules.PbixError("Reading a .pbix needs pbixray (the Power BI extension installs it).") from None
    try:
        model: Any = PBIXRay(str(target))
    except Exception as error:  # pbixray refuses a file it cannot decode
        raise rules.PbixError(
            f"pbixray could not read {target.name}: {str(error).splitlines()[0][:160]}"
        ) from None
    return from_pbixray(model, target.stem)


def from_pbixray(model: Any, name: str) -> rules.PbixModel:
    """pbixray's frames (schema, power_query, dax_tables, relationships, dax_measures, m_parameters, metadata)
    as the domain's records."""
    columns: dict[str, list[rules.PColumn]] = {}
    for row in _records(getattr(model, "schema", None)):
        table = _text(row.get("TableName"))
        columns.setdefault(table, []).append(
            rules.PColumn(_text(row.get("ColumnName")), _text(row.get("PandasDataType")))
        )
    m = {
        _text(r.get("TableName")): _text(r.get("Expression"))
        for r in _records(getattr(model, "power_query", None))
    }
    dax = {
        _text(r.get("TableName")): _text(r.get("Expression"))
        for r in _records(getattr(model, "dax_tables", None))
    }
    names = list(dict.fromkeys([*columns, *m, *dax]))
    tables = tuple(
        rules.PTable(t, tuple(columns.get(t, ())), m.get(t, ""), dax.get(t, "")) for t in names if t
    )
    relationships = tuple(
        rules.PRelationship(
            _text(r.get("FromTableName")),
            _text(r.get("FromColumnName")),
            _text(r.get("ToTableName")),
            _text(r.get("ToColumnName")),
            bool(r.get("IsActive", True)),
            {"M:1": "many_to_one", "1:1": "one_to_one", "M:M": "many_to_many"}.get(
                _text(r.get("Cardinality")), "many_to_one"
            ),
            _text(r.get("CrossFilteringBehavior")).lower() in ("both", "bothdirections", "2"),
        )
        for r in _records(getattr(model, "relationships", None))
    )
    measures = tuple(
        rules.PMeasure(
            _text(r.get("TableName")),
            _text(r.get("Name")),
            _text(r.get("Expression")),
            _text(r.get("DisplayFolder")),
            _text(r.get("FormatString")),
            _text(r.get("Description")),
        )
        for r in _records(getattr(model, "dax_measures", None))
    )
    parameters = {
        _text(r.get("ParameterName")): rules.m_parameter_value(_text(r.get("Expression")))
        for r in _records(getattr(model, "m_parameters", None))
        if r.get("ParameterName")
    }
    meta = {_text(r.get("Name")): _text(r.get("Value")) for r in _records(getattr(model, "metadata", None))}
    refreshed = meta.get("LastProcessedTime") or meta.get("LastUpdate") or meta.get("LastRefreshTime") or ""
    return rules.PbixModel(name, tables, relationships, measures, parameters, refreshed)
