# /// swissarmybench-blade
# format = 1
# name = "Files combine CSVs"
# kind = "other"
# description = "A folder of CSV files as one table"
# tags = ["files", "csv"]
# family = "Files"
# variable = "combine_csvs"
# ///
"""A folder of CSV files as one table (a pandas DataFrame): their rows one after another, the
columns lined up by name, and a column saying which file each row came from.

    combine_csvs = sab.blade("Files combine CSVs")
    orders = combine_csvs("C:/exports/daily")                    # every .csv file in the folder
    orders = combine_csvs("C:/exports", "orders_2026-*.csv")     # only some
    orders = combine_csvs("C:/exports", recursive=True)          # its folders too

A column one file lacks is empty in its rows. Values are read as text first, then pandas finds numbers
and dates, as it does for one file. The files are only read.

Laid out top to bottom: its helpers, each under a line saying what it is for; `combine_csvs`, the one
you call, is last.
"""

from pathlib import Path

import pandas as pd


class FilesError(ValueError):
    """The folder or files cannot be used as asked: the message says why."""


def combine_csvs(
    folder: str | Path,
    pattern: str = "*.csv",
    recursive: bool = False,
    source_column: str | None = "source_file",
    delimiter: str | None = None,
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    """Every file in `folder` matching `pattern` (in its folders too when `recursive`), as one table.
    `source_column` (None: none) holds each row's file name; `delimiter` None: found from each file."""
    base = Path(folder).expanduser()
    if not base.is_dir():
        raise FilesError(f"There is no folder at {base}.")
    files = sorted(base.rglob(pattern) if recursive else base.glob(pattern))
    files = [f for f in files if f.is_file()]
    if not files:
        raise FilesError(f"No file in {base} matches {pattern}.")
    parts = []
    for file in files:
        if delimiter is None:  # the python engine finds each file's delimiter itself
            part = pd.read_csv(file, sep=None, engine="python", encoding=encoding)
        else:
            part = pd.read_csv(file, sep=delimiter, encoding=encoding)
        if source_column:
            part.insert(0, source_column, str(file.relative_to(base)))
        parts.append(part)
    return pd.concat(parts, ignore_index=True, sort=False)
