# /// swissarmybench-blade
# format = 1
# name = "Files change delimiter or encoding"
# kind = "other"
# description = "Rewrite a CSV with another delimiter or encoding"
# tags = ["files", "csv"]
# family = "Files"
# variable = "convert_csv"
# ///
"""Rewrite a CSV file with another delimiter (comma, semicolon, tab, pipe) or another encoding.

    convert_csv = sab.blade("Files change delimiter or encoding")
    convert_csv("C:/in/orders.csv", "C:/out/orders.csv", delimiter=";")                 # for a European Excel
    convert_csv("C:/in/legacy.csv", "C:/out/legacy.csv", from_encoding="cp1252")   # old Windows text
    convert_csv("C:/in/orders.csv", "C:/out/orders.tsv", delimiter="\\t", encoding="utf-8-sig")

The file's own delimiter is found from its first lines unless `from_delimiter` names it. The source is
never changed, and a file already at the new path is written over only with overwrite=True. Returns the
new file's path. Standard library only.
"""

import csv
import io
from pathlib import Path


class FilesError(ValueError):
    """The file cannot be used as asked: the message says why."""


def _delimiter(text: str) -> str:
    """The delimiter a CSV's first lines use (a comma when it cannot be told)."""
    try:
        return csv.Sniffer().sniff(text[:64_000], delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def convert_csv(
    path: str | Path,
    out: str | Path,
    delimiter: str = ",",
    encoding: str = "utf-8",
    from_delimiter: str | None = None,
    from_encoding: str = "utf-8-sig",
    overwrite: bool = False,
) -> str:
    """Read `path` (in `from_encoding`, split by `from_delimiter` or the one found) and write it to
    `out` split by `delimiter`, in `encoding`."""
    source, target = Path(path).expanduser(), Path(out).expanduser()
    if not source.is_file():
        raise FilesError(f"There is no file at {source}.")
    if len(delimiter) != 1:
        raise FilesError(f"A delimiter is one character, such as , ; or a tab (not {delimiter!r}).")
    if target.exists() and target.resolve() == source.resolve():
        raise FilesError("Write the new file somewhere else: the source is never changed.")
    if target.exists() and not overwrite:
        raise FilesError(f"{target} already exists: pass overwrite=True to write over it.")
    try:
        with source.open(newline="", encoding=from_encoding) as handle:
            text = handle.read()
    except UnicodeDecodeError as error:
        hint = "try from_encoding='cp1252'"
        raise FilesError(f"{source.name} is not {from_encoding} text ({hint}): {error}.") from None
    found = from_delimiter or _delimiter(text)
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=found))
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("w", newline="", encoding=encoding) as handle:
            csv.writer(handle, delimiter=delimiter).writerows(rows)
    except UnicodeEncodeError as error:
        target.unlink(missing_ok=True)
        raise FilesError(f"Some text cannot be written in {encoding} (try utf-8): {error}") from None
    return str(target)
