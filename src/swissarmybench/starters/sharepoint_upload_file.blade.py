# /// swissarmybench-blade
# format = 1
# name = "SharePoint upload file"
# kind = "other"
# description = "A DataFrame (as Excel or CSV) or a file of yours uploaded to a library"
# tags = ["sharepoint", "files", "upload"]
# family = "SharePoint"
# variable = "upload_file"
# ///
"""A DataFrame or a file of yours uploaded to a SharePoint library: a DataFrame goes as Excel (a path
ending .xlsx) or CSV; a file on this computer as it is. A document of that name is replaced.

    upload_file = sab.blade("SharePoint upload file")
    upload_file(summary, "Documents/Finance/Summary.xlsx")
    upload_file(r"C:/Reports/q3.pdf", "Documents/Reports/q3.pdf")

Dry run first: as it stands it says what it would upload and changes nothing; pass dry_run=False to
upload. An agent uploads only after you said to, in your own words.

Laid out top to bottom: its helpers, each under a line saying what it is for; `upload_file`, the one you
call, is last.
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


def upload_file(data: Any, path: str, dry_run: bool = True, connection: Any = None) -> dict[str, Any]:
    """Upload `data` (a DataFrame, bytes, or a file's path on this computer) to library/folders/name."""
    import os

    conn = _documents(connection)
    if isinstance(data, str) and os.path.isfile(data):
        what = f"the file {data} ({os.path.getsize(data):,} bytes)"
    elif isinstance(data, (bytes, bytearray)):
        what = f"{len(data):,} bytes"
    elif hasattr(data, "shape"):
        what = f"a table of {data.shape[0]:,} rows as {'Excel' if path.lower().endswith('.xlsx') else 'CSV'}"
    else:
        raise SharePointFileError("Upload a DataFrame, bytes, or a file's path on this computer.")
    if dry_run:
        return {"dry_run": True, "would": f"upload {what} to {path}", "uploaded": 0}
    try:
        done = conn.upload(path, data)
    except RuntimeError as error:
        raise SharePointFileError(str(error)) from None
    return {"dry_run": False, "uploaded": 1} | dict(done)
