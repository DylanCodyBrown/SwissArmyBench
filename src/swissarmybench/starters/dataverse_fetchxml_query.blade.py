# /// swissarmybench-blade
# format = 1
# name = "Dataverse FetchXML query"
# kind = "other"
# description = "A FetchXML query's rows from your Dataverse environment, as a table"
# tags = ["dataverse", "fetchxml", "query"]
# family = "Dataverse"
# variable = "fetch_xml"
# ///
"""A FetchXML query's rows from your Dataverse environment, as a table (a pandas DataFrame): its joins
(link-entity), filters, order and aggregates, as Advanced Find and the maker portal write them.

    fetch_xml = sab.blade("Dataverse FetchXML query")
    fetch_xml('''
    <fetch top="50">
      <entity name="opportunity">
        <attribute name="name" />
        <attribute name="estimatedvalue" />
        <attribute name="parentaccountid" />
        <filter><condition attribute="statecode" operator="eq" value="1" /></filter>
        <order attribute="estimatedvalue" descending="true" />
      </entity>
    </fetch>''')

It reads through your Dataverse connection: ENVIRONMENT below names it (or pass environment="...").
The connection's own sign-in is borrowed, never a copy of its secret. A choice column comes as its
labels (Won, not 1), a lookup as its id with its name beside it; the first page only (5,000 rows, or
the query's own top). Errors from Dataverse arrive as DataverseActionError, in plain words.

Dataverse's request: GET .../api/data/v9.2/<entity set>?fetchXml=...

Laid out top to bottom: its helpers, each under a line saying what it is for; `fetch_xml`, the one you
call, is last.
"""

from typing import Any

import pandas as pd

import swissarmybench as sab

# Your Dataverse connection's name (the Connections window).
ENVIRONMENT = "Sales CRM"


class DataverseActionError(RuntimeError):
    """Dataverse refused, or the connection is not a Dataverse environment: the message says why."""


def _environment(connection: Any = None) -> Any:
    """The Dataverse connection, signed in its own way (as you, a managed identity, an app
    registration): the query borrows that sign-in and never holds a copy of the secret."""
    named = connection is None or isinstance(connection, str)
    conn = sab.connection(connection or ENVIRONMENT) if named else connection
    if not hasattr(conn, "fetch") or not hasattr(conn, "tables"):
        raise DataverseActionError(f"{connection or ENVIRONMENT} is not a Dataverse connection.")
    return conn


def fetch_xml(query: str, environment: Any = None) -> pd.DataFrame:
    """The query's rows: one row each, its columns as the query names them."""
    conn = _environment(environment)
    try:
        found = conn.fetch(query)
    except RuntimeError as error:  # the connection's own DataverseError, in plain words
        raise DataverseActionError(str(error)) from None
    return found if isinstance(found, pd.DataFrame) else pd.DataFrame(found)
