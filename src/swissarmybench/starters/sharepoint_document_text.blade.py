# /// swissarmybench-blade
# format = 1
# name = "SharePoint document text"
# kind = "other"
# description = "A Word or PDF document's text (or a text file's), as one string"
# tags = ["sharepoint", "files", "text", "word", "pdf"]
# family = "SharePoint"
# variable = "document_text"
# ///
"""A document's text from a SharePoint library: a Word document's paragraphs, a PDF's pages (with the
pypdf package), a text file as it is. A document that is not a table, read as words.

    document_text = sab.blade("SharePoint document text")
    document_text("Documents/Policies/Travel.docx")
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


def document_text(path: Any, connection: Any = None) -> str:
    """The text of the document at `path` (library/folders/name, or a file index row)."""
    conn = _documents(connection)
    if hasattr(path, "to_dict"):
        path = path.to_dict()
    try:
        return str(conn.text(path))
    except RuntimeError as error:
        raise SharePointFileError(str(error)) from None
