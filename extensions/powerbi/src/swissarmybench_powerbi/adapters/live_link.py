"""The live link to a running Power BI Desktop (Windows only; rules: domain/live_link.py). Never reads a
.pbix.

  discover()     each Desktop's Analysis Services port (msmdsrv.port.txt under AnalysisServicesWorkspaces, the
                 installer's and the Microsoft Store's places) and the file it has open (PBIDesktop.exe's
                 command
                 line, by one PowerShell CIM query). Local only; run off the event loop
  libraries()    Microsoft's model client libraries (Microsoft.AnalysisServices and AdomdClient, their .NET
                 Framework builds from NuGet, a pinned version, each package's SHA-256 checked), fetched once
                 on
                 first use into the state folder: never in the wheel. Windows' own .NET Framework runs them
  TomModel       the open model through pythonnet: its metadata (names only), DAX for E's Local source, and
  the
                 allowed edits (TOM: measures, calculated columns and tables, relationships, calculation
                 groups),
                 each saved with Model.SaveChanges()

Not run in this repository's tests (no Windows, no .NET here): tests/powerbi_live_fake.py stands in at this
seam.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from swissarmybench_powerbi.domain import live_link as rules

VERSION = "19.82.0"
PACKAGES: dict[str, str] = {
    # NuGet id -> the .nupkg's SHA-256 (checked 2026-11-19; lib/net45 is the .NET Framework build)
    "microsoft.analysisservices.retail.amd64": (
        "cd2939ca30af97b1a8d2aedd6a00c467d392187059cc0e7c4f82f992f89c165b"
    ),
    "microsoft.analysisservices.adomdclient.retail.amd64": (
        "b63ba802580ab7ec5c517a13ba75b72f984ac760d82960e1d5a96308bddd878c"
    ),
}
DLLS = (
    "Microsoft.AnalysisServices.Core.dll",
    "Microsoft.AnalysisServices.Tabular.dll",
    "Microsoft.AnalysisServices.AdomdClient.dll",
)


def windows() -> bool:
    return sys.platform == "win32"


def _roots() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    home = Path(os.environ.get("USERPROFILE", ""))
    return [
        local / "Microsoft" / "Power BI Desktop" / "AnalysisServicesWorkspaces",
        home / "Microsoft" / "Power BI Desktop Store App" / "AnalysisServicesWorkspaces",
    ]


def _command_lines() -> list[str]:
    """Each running Power BI Desktop's command line (one PowerShell CIM query; values never in its text)."""
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='PBIDesktop.exe'\" | "
        "Select-Object -ExpandProperty CommandLine | ConvertTo-Json"
    )
    try:
        done = subprocess.run(  # noqa: S603 (a fixed script, no input)
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        found = json.loads(done.stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return [found] if isinstance(found, str) else [str(f) for f in found or []]


def discover() -> list[rules.Instance]:
    """The running Desktops (none off Windows). A workspace folder whose port file is there is one; the open
    files are matched to them in start order (one Desktop each)."""
    if not windows():
        return []
    ports: list[tuple[float, int, str]] = []
    for root in _roots():
        for port_file in root.glob("*/Data/msmdsrv.port.txt") if root.is_dir() else []:
            try:
                port = rules.port_of(port_file.read_bytes())
                if port:
                    ports.append((port_file.stat().st_mtime, port, str(port_file.parent.parent)))
            except OSError:
                continue
    files = [rules.file_of(c) for c in _command_lines()]
    ports.sort()
    return [rules.Instance(p, w, files[n] if n < len(files) else "") for n, (_t, p, w) in enumerate(ports)]


def libraries(state_dir: Path) -> Path:
    """The model client libraries' folder, fetched once (pinned, hash checked). Raises when they cannot be."""
    folder = state_dir / "powerbi" / f"tom-{VERSION}"
    if all((folder / d).is_file() for d in DLLS):
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    for package, digest in PACKAGES.items():
        url = f"https://api.nuget.org/v3-flatcontainer/{package}/{VERSION}/{package}.{VERSION}.nupkg"
        with urllib.request.urlopen(url, timeout=120) as answer:
            data = answer.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise rules.LiveError(f"{package} did not match its pinned hash: nothing was installed.")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.namelist():
                if entry.startswith("lib/net45/") and entry.count("/") == 2 and entry.endswith(".dll"):
                    (folder / entry.rsplit("/", 1)[1]).write_bytes(archive.read(entry))
    return folder


class TomModel:
    """The open model through pythonnet and TOM (Windows; .NET Framework)."""

    def __init__(self, port: int, state_dir: Path) -> None:
        try:
            import clr  # type: ignore[import-not-found]  # pythonnet, the extension's Windows dependency
        except ImportError:
            raise rules.LiveError(
                "Edit in Power BI Desktop needs pythonnet (the Power BI extension installs it)."
            ) from None
        folder = libraries(state_dir)
        sys.path.append(str(folder))
        for dll in DLLS:
            clr.AddReference(str(folder / dll))
        from Microsoft.AnalysisServices import Tabular  # type: ignore[import-not-found]

        self._tom = Tabular
        self._server = Tabular.Server()
        self._server.Connect(f"Data Source=localhost:{port}")
        self._model = self._server.Databases[0].Model
        self._port = port

    def metadata(self) -> rules.OpenModel:
        out = rules.OpenModel()
        for table in self._model.Tables:
            out.tables[str(table.Name)] = [str(c.Name) for c in table.Columns]
            for m in table.Measures:
                out.measures[(str(table.Name), str(m.Name))] = str(m.Expression)
        for r in self._model.Relationships:
            out.relationships.append(
                (
                    str(r.FromTable.Name),
                    str(r.FromColumn.Name),
                    str(r.ToTable.Name),
                    str(r.ToColumn.Name),
                    bool(r.IsActive),
                )
            )
        return out

    def evaluate(self, dax: str) -> Any:
        import pyarrow as pa
        from Microsoft.AnalysisServices.AdomdClient import AdomdConnection  # type: ignore[import-not-found]

        with AdomdConnection(f"Data Source=localhost:{self._port}") as connection:
            connection.Open()
            command = connection.CreateCommand()
            command.CommandText = dax
            reader = command.ExecuteReader()
            names = [str(reader.GetName(i)) for i in range(reader.FieldCount)]
            rows: list[list[Any]] = []
            while reader.Read():
                rows.append(
                    [None if reader.IsDBNull(i) else reader.GetValue(i) for i in range(reader.FieldCount)]
                )
        return pa.table({n.split("[")[-1].rstrip("]"): [r[i] for r in rows] for i, n in enumerate(names)})

    def apply(self, change: rules.Change) -> None:
        tom, model = self._tom, self._model
        if change.kind in ("measure_add", "measure_change", "measure_delete"):
            table = model.Tables.Find(change.table)
            found = table.Measures.Find(change.name)
            if change.kind == "measure_delete":
                table.Measures.Remove(found)
            else:
                measure = found or tom.Measure()
                measure.Name, measure.Expression = change.name, change.expression
                if change.format:
                    measure.FormatString = change.format
                if change.folder:
                    measure.DisplayFolder = change.folder
                if found is None:
                    table.Measures.Add(measure)
        elif change.kind == "relationship_add":
            r = tom.SingleColumnRelationship()
            r.FromColumn = model.Tables.Find(change.table).Columns.Find(change.column)
            r.ToColumn = model.Tables.Find(change.to_table).Columns.Find(change.to_column)
            r.IsActive = change.active
            model.Relationships.Add(r)
        elif change.kind == "relationship_delete":
            for r in list(model.Relationships):
                ends = (str(r.FromTable.Name), str(r.FromColumn.Name), str(r.ToTable.Name))
                if (*ends, str(r.ToColumn.Name)) == (
                    change.table,
                    change.column,
                    change.to_table,
                    change.to_column,
                ):
                    model.Relationships.Remove(r)
        elif change.kind == "calculated_column":
            column = tom.CalculatedColumn()
            column.Name, column.Expression = change.name, change.expression
            model.Tables.Find(change.table).Columns.Add(column)
        elif change.kind == "calculated_table":
            table = tom.Table()
            table.Name = change.name
            partition = tom.Partition()
            partition.Name = change.name
            source = tom.CalculatedPartitionSource()
            source.Expression = change.expression
            partition.Source = source
            table.Partitions.Add(partition)
            model.Tables.Add(table)
        elif change.kind == "calculation_group":
            table = tom.Table()
            table.Name = change.name
            table.CalculationGroup = tom.CalculationGroup()
            for name, expression in change.items:
                item = tom.CalculationItem()
                item.Name, item.Expression = name, expression
                table.CalculationGroup.CalculationItems.Add(item)
            model.Tables.Add(table)
        model.SaveChanges()
