"""The Dataverse Write starters' helper (docs/ideas.md, "Writing data"): rows written through the Web API,
the Dataverse connection's own (its SQL endpoint, TDS, is read-only). The requests themselves are
written out in each starter's cell.

    w = DataverseWrite("Sales CRM", "account", "upsert", accounts, dry_run=dry_run)
    w.check_columns()                              # each column is one of the table's
    found = w.existing("accountnumber")            # the keys already there
    w.would("PATCH accounts(accountnumber='...')", inserted=..., updated=...)
    if not dry_run:
        answers = w.send(lambda row: ("PATCH", w.address("accountnumber", row), w.body(row), {}))

  $batch        each batch of rows is one change set of one $batch request: all of it or none of it
                (Dataverse's transaction; a change set holds up to 1,000 requests). A refusal names its
                batch and rows; the batches before it stay written
  429           Dataverse's service protection limits: the request waits as long as Retry-After says
                (up to 5 minutes), then goes again, up to 5 times
  choices       a choice column (Picklist, State, Status, multi-select) takes its labels (Won, not 1):
                each label is read from the column's options and sent as its number
  lookups       a lookup is written as `<column>@odata.bind` with "/<entity set>(<id>)" values: a column
                of the rows named so passes through as it is
  keys          a record is found by its id (the table's Uniqueidentifier column) or by an alternate
                key's column: accounts(accountnumber='AC-1001')

Standard library only; the sign-in is the connection's (sab.connection: as you, a managed identity, or
an app registration whose secret is a vault's), never a copy of it.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from swissarmybench.client.writes import Rows, Write, WriteError, live, plain_value, words

CHOICES = frozenset({"Picklist", "State", "Status", "MultiSelectPicklist"})
LOOKUPS = frozenset({"Lookup", "Customer", "Owner"})
_METADATA = {
    "Picklist": "PicklistAttributeMetadata",
    "State": "StateAttributeMetadata",
    "Status": "StatusAttributeMetadata",
    "MultiSelectPicklist": "MultiSelectPicklistAttributeMetadata",
}
MOST_IN_A_CHANGE_SET = 1000
WAITS = 5  # a throttled $batch goes again this many times
LONGEST_WAIT = 300.0
KEYS_IN_A_LOOKUP = 25  # keys asked about in one GET ($filter ... or ...)
_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class DataverseWrite(Write):
    """A write to a Dataverse table through the Web API: its columns, choice labels, keys, and the
    rows sent in $batch change sets."""

    def __init__(
        self,
        connection: Any,
        table: str,
        what: str,
        rows: Any = None,
        dry_run: bool = True,
        batch_size: int = 1000,
    ) -> None:
        name, conn = live(connection)
        if not (hasattr(conn, "api") and hasattr(conn, "access_token") and hasattr(conn, "described")):
            raise WriteError(f"{name} is not a Dataverse connection: these starters write to Dataverse.")
        super().__init__(name, table, what, rows, dry_run)
        self.conn = conn
        self.batch_size = max(1, min(int(batch_size), MOST_IN_A_CHANGE_SET))
        try:
            found = conn.table(table)
            self.logical, self.entity_set = str(found["table"]), str(found["set"])
            self.described: list[dict[str, Any]] = list(conn.described(self.logical))
        except RuntimeError as error:  # the connection's own DataverseError, in plain words
            raise WriteError(str(error)) from None
        self.kinds = {str(c["name"]): str(c["type"]) for c in self.described}
        self._options: dict[str, dict[str, int]] = {}
        self.fact("Table", f"{self.logical} (the Web API's {self.entity_set})")

    # ===== the columns, the values =====

    def check_columns(self, names: Sequence[str] | None = None) -> None:
        """Each column of the rows (or `names`) is the table's (a lookup as <column>@odata.bind)."""
        wanted = list(names or self.need_rows().names)
        missing = [n for n in wanted if "@" not in n and n.lower() not in self.kinds]
        if missing:
            some = ", ".join(sorted(self.kinds)[:20])
            raise WriteError(f"{self.logical} has no column {', '.join(missing)} (it has {some} ...).")
        lookups = [n for n in wanted if self.kinds.get(n.lower()) in LOOKUPS]
        if lookups:
            first = lookups[0]
            raise WriteError(
                f"{first} is a lookup: name the rows' column {first}@odata.bind and give each row "
                f'"/<entity set>(<id>)" (for example "/contacts(00000000-0000-0000-0000-000000000000)").'
            )
        choices = [n for n in wanted if self.kinds.get(n.lower()) in CHOICES]
        if choices:
            self.fact("Choices", f"{', '.join(choices)}: labels sent as their numbers")

    def options(self, column: str) -> dict[str, int]:
        """A choice column's labels (any case) -> their numbers, read once."""
        column = column.lower()
        if column not in self._options:
            kind = _METADATA[self.kinds[column]]
            path = (
                f"EntityDefinitions(LogicalName='{self.logical}')/Attributes(LogicalName='{column}')/"
                f"Microsoft.Dynamics.CRM.{kind}?$select=LogicalName&$expand=OptionSet($select=Options)"
            )
            answer = self._get(path, f"Reading {self.logical}.{column}'s options")
            found = (answer.get("OptionSet") or {}).get("Options") or []
            self._options[column] = {_label(o.get("Label")).casefold(): int(o["Value"]) for o in found}
        return self._options[column]

    def value(self, column: str, value: Any) -> Any:
        """A row's value as the Web API takes it: a choice's label as its number, dates as ISO text."""
        value = plain_value(value)
        kind = self.kinds.get(column.lower())
        if kind not in CHOICES or value is None or isinstance(value, int | float):
            return value
        labels = self.options(column)
        given = (
            value
            if isinstance(value, list)
            else str(value).split(";")
            if kind == "MultiSelectPicklist"
            else [value]
        )
        numbers = []
        for one in given:
            word = str(one).strip()
            if word.lstrip("-").isdigit():
                numbers.append(int(word))
            elif word.casefold() in labels:
                numbers.append(labels[word.casefold()])
            else:
                known = ", ".join(sorted({k for k in labels}))
                raise WriteError(f"{column} has no choice {word!r}: its choices are {known}.")
        return ",".join(map(str, numbers)) if kind == "MultiSelectPicklist" else numbers[0]

    def body(
        self, row: dict[str, Any], without: Iterable[str] = (), skip_empty: bool = False
    ) -> dict[str, Any]:
        """A row as a record's JSON (an empty value: null, which empties the column; or left out)."""
        left = {w.lower() for w in without}
        out = {}
        for column, value in row.items():
            if column.lower() in left or (skip_empty and value is None):
                continue
            out[column if "@" in column else column.lower()] = self.value(column, value)
        return out

    # ===== finding records =====

    def check_key(self, key: str) -> str:
        """The key column, checked: one of the rows' columns, a value in each row, one row each."""
        rows = self.need_rows()
        rows.check_keys([key], unique=True)
        if key.lower() not in self.kinds:
            raise WriteError(
                f"{self.logical} has no column {key}: the key is its id or an alternate key's column."
            )
        self.fact("Key", key)
        return key

    def is_id(self, key: str) -> bool:
        return self.kinds.get(key.lower()) == "Uniqueidentifier"

    def literal(self, key: str, value: Any) -> str:
        """A key's value in an address or a filter: an id bare, a number bare, text quoted."""
        value = plain_value(value)
        if self.is_id(key):
            if not _GUID.fullmatch(str(value)):
                raise WriteError(f"{key} holds ids (00000000-0000-0000-0000-000000000000), not {value!r}.")
            return str(value)
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float):
            return str(value)
        return "'" + str(value).replace("'", "''") + "'"

    def address(self, key: str, row: dict[str, Any]) -> str:
        """A record's address: accounts(<id>), or by an alternate key accounts(accountnumber='AC-1')."""
        literal = self.literal(key, row[key])
        inside = literal if self.is_id(key) else f"{key.lower()}={literal}"
        return f"{self.entity_set}({urllib.parse.quote(inside, safe=chr(39) + '=-')})"

    def existing(self, key: str) -> set[str]:
        """The rows' keys that are records already (as text), asked a few at a time."""
        rows = self.need_rows()
        found: set[str] = set()
        field = key.lower()
        for batch in rows.batches([key], KEYS_IN_A_LOOKUP, distinct=True):
            condition = " or ".join(f"{field} eq {self.literal(key, r[0])}" for r in batch)
            query = urllib.parse.urlencode(
                {"$select": field, "$filter": condition}, quote_via=urllib.parse.quote
            )
            answer = self._get(f"{self.entity_set}?{query}", f"Looking up {self.logical}'s {key}")
            found |= {str(r.get(field)).lower() for r in answer.get("value") or []}
        return found

    def keys_of(self, key: str) -> list[str]:
        """The rows' keys (as text), each once."""
        return [
            str(plain_value(r[0])).lower()
            for b in self.need_rows().batches([key], 1000, distinct=True)
            for r in b
        ]

    # ===== sending =====

    def change_sets(self) -> int:
        rows = self.need_rows().count
        return -(-rows // self.batch_size) if rows else 0

    def send(
        self,
        request: Callable[[dict[str, Any]], tuple[str, str, Any, dict[str, str]] | None],
        rows: Rows | None = None,
    ) -> list[int]:
        """Each row made a request by `request` (method, address, body, headers; None: no request),
        sent a change set at a time. Each answer's status, in order."""
        given = rows or self.need_rows()
        statuses: list[int] = []
        done = 0
        for number, batch in enumerate(given.records(self.batch_size), 1):
            made = [r for r in (request(row) for row in batch) if r is not None]
            if made:
                try:
                    statuses += self._change_set(made)
                except WriteError as error:
                    before = f"the {done:,} rows before it were written" if done else "nothing was written"
                    raise WriteError(
                        f"Batch {number} (rows {done + 1:,} to {done + len(batch):,}) was refused and "
                        "rolled back: "
                        f"{error} Each batch is a transaction of its own (up to 1,000 rows): {before}."
                    ) from None
            done += len(batch)
        return statuses

    def _change_set(self, requests: Sequence[tuple[str, str, Any, dict[str, str]]]) -> list[int]:
        batch, change = f"batch_{uuid.uuid4().hex}", f"changeset_{uuid.uuid4().hex}"
        parts = []
        for n, (method, path, body, headers) in enumerate(requests, 1):
            lines = [
                f"--{change}",
                "Content-Type: application/http",
                "Content-Transfer-Encoding: binary",
                f"Content-ID: {n}",
                "",
                f"{method} {self.conn.api}/{path} HTTP/1.1",
                "Content-Type: application/json; charset=utf-8",
                *(f"{k}: {v}" for k, v in headers.items()),
                "",
                "" if body is None else json.dumps(body),
            ]
            parts.append("\r\n".join(lines))
        text = (
            f"--{batch}\r\nContent-Type: multipart/mixed; boundary={change}\r\n\r\n"
            + "\r\n".join(parts)
            + f"\r\n--{change}--\r\n--{batch}--\r\n"
        )
        answer = self._post_batch(text.encode("utf-8"), batch)
        statuses = [int(s) for s in re.findall(r"HTTP/1\.1 (\d{3})", answer)]
        failed = next((s for s in statuses if s >= 400), None)
        if failed is not None or not statuses:
            raise WriteError(_refusal(answer, failed or 0))
        return statuses

    def _post_batch(self, data: bytes, boundary: str) -> str:
        for attempt in range(WAITS + 1):
            headers = {
                "Authorization": f"Bearer {self.conn.access_token()}",
                "Content-Type": f"multipart/mixed; boundary={boundary}",
                "Accept": "application/json",
                "OData-MaxVersion": "4.0",
                "OData-Version": "4.0",
            }
            request = urllib.request.Request(f"{self.conn.api}/$batch", data, headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=300) as answer:
                    return str(answer.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as refused:
                if refused.code in (429, 503) and attempt < WAITS:
                    wait = refused.headers.get("Retry-After") or ""
                    time.sleep(
                        min(
                            float(wait) if wait.strip().replace(".", "", 1).isdigit() else 2.0**attempt,
                            LONGEST_WAIT,
                        )
                    )
                    continue
                raise WriteError(_refusal(refused.read().decode("utf-8", "replace"), refused.code)) from None
            except urllib.error.URLError as error:
                raise WriteError(f"Dataverse could not be reached: {error.reason}") from None
        raise WriteError("Dataverse kept asking to wait (429).")

    def _get(self, path: str, what: str) -> dict[str, Any]:
        try:
            found = self.conn.get(path, what)
        except RuntimeError as error:
            raise WriteError(words(error)) from None
        return found if isinstance(found, dict) else {}


def _label(label: Any) -> str:
    if not isinstance(label, dict):
        return ""
    own = label.get("UserLocalizedLabel") or {}
    if own.get("Label"):
        return str(own["Label"])
    return next((str(e["Label"]) for e in label.get("LocalizedLabels") or [] if e.get("Label")), "")


_HINTS = {
    400: "Dataverse could not take a record as sent: a column's value may be of the wrong type.",
    401: "The sign-in was not accepted: test the Dataverse connection.",
    403: "This sign-in may not write this table: its security role needs Create, Write or Delete on it.",
    404: "A record is not there: check the key's values (an update or a delete finds each one).",
    412: "A record changed or is not there (If-Match).",
    429: "Dataverse kept asking to wait: try again later, or with a smaller batch_size.",
}


def _refusal(text: str, status: int) -> str:
    """Dataverse's own message from an answer, and what its status usually means."""
    found = re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    message = (
        json.loads(f'"{found.group(1)}"') if found else (text.strip().splitlines() or ["no reason"])[0][:300]
    )
    return f"Dataverse refused ({status}): {message}. {_HINTS.get(status, '')}".strip()


__all__ = ["DataverseWrite", "WriteError"]
