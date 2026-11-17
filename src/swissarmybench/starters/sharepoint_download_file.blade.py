# /// swissarmybench-blade
# format = 1
# name = "SharePoint download file"
# kind = "other"
# description = "A document downloaded into a folder of yours (the project's, by default)"
# tags = ["sharepoint", "files", "download"]
# family = "SharePoint"
# variable = "download_file"
# ///
"""A document from a SharePoint library saved into a folder on this computer: the project's folder
when none is named. It runs only when you run it (your click), and says where the file went.

    download_file = sab.blade("SharePoint download file")
    download_file("Documents/Policies/Travel.docx")
    download_file("Documents/Finance/Budget 2026.xlsx", folder=r"C:/Reports")
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


def download_file(path: Any, folder: str = "", connection: Any = None) -> str:
    """The document at `path` (library/folders/name, or a file index row) written into `folder` (the
    current folder: a project's own when the Workbench runs it there). An existing file of that name is
    replaced. The file's path."""
    from pathlib import Path

    conn = _documents(connection)
    if hasattr(path, "to_dict"):
        path = path.to_dict()
    try:
        data = conn.download(path)
    except RuntimeError as error:
        raise SharePointFileError(str(error)) from None
    name = path.get("name") if isinstance(path, dict) else str(path).replace("\\", "/").rsplit("/", 1)[-1]
    target = Path(folder or ".").expanduser().resolve() / str(name)
    target.write_bytes(data)
    return str(target)
