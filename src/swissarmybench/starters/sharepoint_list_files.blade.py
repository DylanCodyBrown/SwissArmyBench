# /// swissarmybench-blade
# format = 1
# name = "SharePoint list files"
# kind = "other"
# description = "A document library's files as a small table: names, folders, sizes, dates"
# tags = ["sharepoint", "files", "documents"]
# family = "SharePoint"
# variable = "list_files"
# ///
"""A document library's files (in a folder and below, or all of them) as a small table: each file's
name, folder, extension, size, when it was last changed and by whom, and its web link.

    list_files = sab.blade("SharePoint list files")
    list_files("Documents", "Finance")

It reads through your SharePoint documents connection (DOCUMENTS below names it, or pass
connection="..."), borrowing its sign-in. This is a blade's result, not a table of the connection: the
connection's own file index is [Team Docs].Documents in DuckDB SQL.
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


def list_files(library: str = "", folder: str = "", connection: Any = None) -> Any:
    """The files of `library` (the site's first one when not named) under `folder` ("" every folder)."""
    conn = _documents(connection)
    try:
        return conn.files(library or None, folder or None)
    except RuntimeError as error:  # the connection's own SharePointError, in plain words
        raise SharePointFileError(str(error)) from None
