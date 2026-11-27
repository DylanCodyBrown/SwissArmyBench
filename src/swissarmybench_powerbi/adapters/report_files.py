"""A dropped report read (rules: domain/report_swap.py): a .pbix or .pbit as a zip (its report part and a
.pbit's DataModelSchema only; DataModel is never opened), a .pbip's .Report folder and its SemanticModel's
TMDL, and a .pbix's model measures through pbixray (imported here only, when installed). The file is read,
never changed, and its cached rows are never read.
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from swissarmybench_powerbi.domain import report_swap as rules

MAX_FOLDER_FILES: int = 5_000


def read(path: str | None = None, data: bytes | None = None, name: str = "") -> rules.Report:
    """The report at `path` (a .pbix, .pbit, .pbip or its folder), or uploaded `data` named `name`."""
    target = Path(path) if path else None
    kind = (target.suffix if target is not None else Path(name).suffix).lower()
    if target is not None and target.is_dir():
        return _pbip_folder(target)
    if kind == ".pbip":
        if target is None:
            raise rules.ReportError(
                "A .pbip is a folder of files: choose it on this computer (not uploaded)."
            )
        return _pbip_folder(target.parent, target.stem)
    if kind not in (".pbix", ".pbit"):
        raise rules.ReportError("Use a .pbix, a .pbit or a .pbip.")
    if target is not None:
        if not target.is_file():
            raise FileNotFoundError(f"{target} is not there.")
        data = target.read_bytes()
    if data is None:
        raise rules.ReportError("No file was given.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise rules.ReportError("The file is not a Power BI file (it is not a zip).") from None
    with archive:
        names = rules.wanted_entries((i.filename, i.file_size) for i in archive.infolist())
        parts = {n: archive.read(n) for n in names}
    report = rules.from_archive(kind[1:], parts)
    if kind == ".pbix":
        _pbix_measures(report, target, data)
    return report


def _pbix_measures(report: rules.Report, target: Path | None, data: bytes) -> None:
    """A .pbix's measures through pbixray (its model's metadata only; never its rows)."""
    try:
        from pbixray import PBIXRay  # type: ignore[import-not-found]  # the extension's own dependency
    except ImportError:
        report.measures_note = rules.unreadable_pbix("pbixray is not installed")
        return
    temporary = None
    try:
        if target is None:
            handle, temporary = tempfile.mkstemp(suffix=".pbix")
            with os.fdopen(handle, "wb") as out:
                out.write(data)
        model: Any = PBIXRay(str(target) if target is not None else temporary)
        rows = model.dax_measures.to_dict("records")
        report.measures = rules.pbix_measures(rows)
        report.measures_note = ""
    except Exception as error:  # pbixray refuses a file: the fallback sentence
        report.measures_note = rules.unreadable_pbix(
            str(error).splitlines()[0][:160] if str(error) else "unknown"
        )
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _pbip_folder(folder: Path, stem: str | None = None) -> rules.Report:
    """A Power BI Project: its .Report folder (by the .pbip's name, else the only one) and its SemanticModel's
    TMDL (definition/), read as files."""
    reports = sorted(folder.glob(f"{stem}.Report" if stem else "*.Report"))
    if folder.suffix.lower() == ".report":
        reports = [folder]
        folder = folder.parent
    if len(reports) != 1:
        raise rules.ReportError("Choose the project's .pbip file (its folder holds no single report).")
    report = reports[0]
    files = _files(report)
    model = report.parent / (report.name[: -len(".Report")] + ".SemanticModel")
    tmdl = (
        {p: d.decode("utf-8-sig") for p, d in _files(model).items() if p.endswith(".tmdl")}
        if model.is_dir()
        else {}
    )
    return rules.from_folder(files, tmdl)


def _files(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".pbi" in path.relative_to(root).parts:
            continue
        size = path.stat().st_size
        total += size
        if len(out) >= MAX_FOLDER_FILES or size > rules.MAX_ENTRY_BYTES or total > rules.MAX_TOTAL_BYTES:
            raise rules.ReportError("The report folder is too large to read.")
        out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out
