# /// swissarmybench-blade
# format = 1
# name = "Files split CSV"
# kind = "other"
# description = "Split a CSV into one file per value of a column"
# tags = ["files", "csv"]
# family = "Files"
# variable = "split_csv"
# ///
"""Split a CSV file into one file per value of a column (one file per region, per customer).

    split_csv = sab.blade("Files split CSV")
    split_csv("C:/exports/orders.csv", "Region")
    # ["C:/exports/orders_by_Region/orders_North.csv", "C:/exports/orders_by_Region/orders_South.csv", ...]
    split_csv("C:/exports/orders.csv", "Region", folder="C:/exports/regions", overwrite=True)

Each file keeps the header and the rows of one value, in their order; an empty value goes to
orders_(blank).csv. The new files go into `folder` (default: a folder beside the file, named for the
column). A file already there is written over only with overwrite=True. Standard library only.

Laid out top to bottom: its helpers, each under a line saying what it is for; `split_csv`, the one you
call, is last.
"""

import csv
import re
from pathlib import Path


class FilesError(ValueError):
    """The file or folder cannot be used as asked: the message says why."""


def _safe(value: str) -> str:
    """A value as part of a file name: letters, digits, - and _ kept, the rest as _."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")[:60] or "(blank)"


def split_csv(
    path: str | Path,
    column: str,
    folder: str | Path | None = None,
    overwrite: bool = False,
    encoding: str = "utf-8-sig",
) -> list[str]:
    """Write one CSV per value of `column` into `folder`: the new files' paths, in the order their
    values first appear."""
    file = Path(path).expanduser()
    if not file.is_file():
        raise FilesError(f"There is no file at {file}.")
    target = Path(folder).expanduser() if folder else file.with_name(f"{file.stem}_by_{_safe(column)}")
    with file.open(newline="", encoding=encoding) as handle:
        sample = handle.read(64_000)
        handle.seek(0)
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
        reader = csv.reader(handle, delimiter=delimiter)
        header = next(reader, None)
        if header is None:
            raise FilesError(f"{file.name} is empty.")
        if column not in header:
            raise FilesError(f"{file.name} has no column {column!r}. It has: {', '.join(header)}.")
        at = header.index(column)
        groups: dict[str, list[list[str]]] = {}
        for row in reader:
            groups.setdefault(row[at] if at < len(row) else "", []).append(row)
    names = {value: target / f"{file.stem}_{_safe(value)}.csv" for value in groups}
    if len(set(names.values())) < len(names):
        raise FilesError(f"Two values of {column} make the same file name; split by another column.")
    taken = [str(p) for p in names.values() if p.exists()]
    if taken and not overwrite:
        raise FilesError(f"{taken[0]} already exists: pass overwrite=True to write over it.")
    target.mkdir(parents=True, exist_ok=True)
    for value, rows in groups.items():
        with names[value].open("w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out, delimiter=delimiter)
            writer.writerow(header)
            writer.writerows(rows)
    return [str(p) for p in names.values()]
