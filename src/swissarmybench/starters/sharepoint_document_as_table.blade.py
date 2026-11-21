# /// swissarmybench-blade
# format = 1
# name = "SharePoint document as a table"
# kind = "other"
# description = "A CSV, Parquet or JSON-lines document, or a workbook's sheet, as a DataFrame"
# tags = ["sharepoint", "files", "excel", "csv"]
# family = "SharePoint"
# variable = "document_table"
# ///
"""A tabular document from a SharePoint library as a table (a pandas DataFrame): a CSV, Parquet or
JSON-lines file, or a workbook's sheet or named table (its first sheet when none is named).

    document_table = sab.blade("SharePoint document as a table")
    document_table("Documents/Finance/Budget 2026.xlsx", sheet="Summary")
    document_table(row)           # a row of the library's file index (its folder and name)

Downloaded into memory only, never written to disk; an unchanged file is downloaded once (kept by its
eTag). header_row is the row holding the column names (1: the first).

Laid out top to bottom: its helpers, each under a line saying what it is for; `document_table`, the one
you call, is last.
"""

from typing import Any

import swissarmybench as sab

# Your SharePoint documents connection's name (the Connections page).
DOCUMENTS = "Team Docs"


class SharePointFileError(RuntimeError):
    """SharePoint refused, or the connection is not a SharePoint documents connection: the message says
    why."""


def _documents(connection: Any = None) -> Any:
    """The SharePoint documents connection, signed in its own way (a username and password, as you, a
    managed identity, an app registration): the blade borrows that sign-in and never holds a copy of a
    password or secret."""
    named = connection is None or isinstance(connection, str)
    conn = sab.connection(connection or DOCUMENTS) if named else connection
    if not hasattr(conn, "download") or not hasattr(conn, "libraries"):
        raise SharePointFileError(f"{connection or DOCUMENTS} is not a SharePoint documents connection.")
    return conn


def document_table(path: Any, sheet: str = "", header_row: int = 1, connection: Any = None) -> Any:
    """The document at `path` (library/folders/name, or a file index row) as a DataFrame."""
    conn = _documents(connection)
    if hasattr(path, "to_dict"):  # a row of a DataFrame
        path = path.to_dict()
    try:
        found = conn.frame(path, sheet=sheet or None, header_row=header_row)
    except RuntimeError as error:
        raise SharePointFileError(str(error)) from None
    return found.to_pandas() if hasattr(found, "to_pandas") else found
