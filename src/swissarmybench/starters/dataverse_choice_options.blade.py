# /// swissarmybench-blade
# format = 1
# name = "Dataverse choice options"
# kind = "other"
# description = "A choice column's options (each number and its label), as a table"
# tags = ["dataverse", "choice", "labels"]
# family = "Dataverse"
# variable = "choice_options"
# ///
"""A choice column's options in your Dataverse environment, as a table (a pandas DataFrame): each
number Dataverse keeps and the label people see. For SQL on the SQL endpoint, where a choice column
holds its numbers, or for a lookup table of your own.

    choice_options = sab.blade("Dataverse choice options")
    choice_options("opportunity", "salesstage")      # columns: value, label

It reads through your Dataverse connection: ENVIRONMENT below names it (or pass environment="...").
The connection's own sign-in is borrowed, never a copy of its secret. Errors from Dataverse arrive as
DataverseActionError, in plain words.

Dataverse's request: GET .../EntityDefinitions(LogicalName='<table>')/Attributes(LogicalName=
'<column>')/Microsoft.Dynamics.CRM.PicklistAttributeMetadata?$expand=OptionSet (State and Status
columns: StateAttributeMetadata, StatusAttributeMetadata)

Laid out top to bottom: its helpers, each under a line saying what it is for; `choice_options`, the one
you call, is last.
"""

import re
from typing import Any

import pandas as pd

import swissarmybench as sab

# Your Dataverse connection's name (the Connections window).
ENVIRONMENT = "Sales CRM"

# A choice column's type -> the metadata that holds its options.
_KINDS = {
    "Picklist": "PicklistAttributeMetadata",
    "State": "StateAttributeMetadata",
    "Status": "StatusAttributeMetadata",
    "MultiSelectPicklist": "MultiSelectPicklistAttributeMetadata",
}


class DataverseActionError(RuntimeError):
    """Dataverse refused, or the connection is not a Dataverse environment: the message says why."""


def _environment(connection: Any = None) -> Any:
    """The Dataverse connection, signed in its own way: the request borrows that sign-in and never
    holds a copy of the secret."""
    named = connection is None or isinstance(connection, str)
    conn = sab.connection(connection or ENVIRONMENT) if named else connection
    if not hasattr(conn, "fetch") or not hasattr(conn, "tables"):
        raise DataverseActionError(f"{connection or ENVIRONMENT} is not a Dataverse connection.")
    return conn


def _label(label: Any) -> str:
    """A metadata label's words: the user's own language's, else the first one given."""
    if not isinstance(label, dict):
        return ""
    own = label.get("UserLocalizedLabel") or {}
    if own.get("Label"):
        return str(own["Label"])
    return next((str(e["Label"]) for e in label.get("LocalizedLabels") or [] if e.get("Label")), "")


def choice_options(table: str, column: str, environment: Any = None) -> pd.DataFrame:
    """The column's options: one row each, its number and its label, in Dataverse's order."""
    conn = _environment(environment)
    try:
        logical = conn.table(table)["table"]
        kind = next((c["type"] for c in conn.columns(logical) if c["column"] == column.lower()), None)
        if kind is None:
            raise DataverseActionError(f"{logical} has no column {column!r}.")
        if kind not in _KINDS or not re.fullmatch(r"[a-z0-9_]+", column.lower()):
            raise DataverseActionError(f"{logical}.{column} is a {kind} column, not a choice.")
        path = (
            f"EntityDefinitions(LogicalName='{logical}')/Attributes(LogicalName='{column.lower()}')/"
            f"Microsoft.Dynamics.CRM.{_KINDS[kind]}?$select=LogicalName&$expand=OptionSet($select=Options)"
        )
        answer = conn.get(path, f"Reading {logical}.{column}'s options")
    except DataverseActionError:
        raise
    except RuntimeError as error:  # the connection's own DataverseError, in plain words
        raise DataverseActionError(str(error)) from None
    options = (answer.get("OptionSet") or {}).get("Options") or []
    rows = [{"value": o.get("Value"), "label": _label(o.get("Label"))} for o in options]
    return pd.DataFrame(rows, columns=["value", "label"])
