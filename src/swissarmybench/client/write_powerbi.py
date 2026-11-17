"""The Power BI Write starters' helper (docs/ideas.md, "Writing data"): rows pushed into a push dataset.

A Power BI model (a semantic model, what the Power BI connection reads with DAX) is not written row by
row: its source is written, then the model refreshed (the Power BI refresh starters). A push dataset is
made for rows sent from outside:

    w = PushWrite("Finance", "Sales push", "Sales", orders, "append", dry_run=dry_run)
    there = w.check_push()             # a push dataset with that table, or none yet
    w.would("POST .../rows", inserted=w.rows.count)
    if not dry_run:
        if not there:
            w.create()                 # made from the rows' columns, their types from DuckDB's
        w.done(inserted=w.push())      # 10,000 rows a request (Power BI's most), 429 waited out

Power BI's requests (its REST API, under the workspace):
    GET    datasets                                  is it there, and is it a push dataset
    POST   datasets?defaultRetentionPolicy=None      a push dataset: {name, defaultMode: Push, tables}
    POST   datasets/{id}/tables/{table}/rows         {"rows": [...]}
    DELETE datasets/{id}/tables/{table}/rows         every row of the table

A push dataset has no transactions: a failed request says how many rows went in before it. Standard
library only; the sign-in is the workspace connection's own (sab.connection), never a copy of it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from swissarmybench.client.writes import Write, WriteError, each_batch, live, plain_value

ROWS_A_REQUEST = 10_000  # Power BI's most in one POST .../rows
WAITS = 5
_TYPES = {
    "BOOLEAN": "Boolean",
    "TINYINT": "Int64",
    "SMALLINT": "Int64",
    "INTEGER": "Int64",
    "BIGINT": "Int64",
    "UTINYINT": "Int64",
    "USMALLINT": "Int64",
    "UINTEGER": "Int64",
    "FLOAT": "Double",
    "DOUBLE": "Double",
    "DATE": "DateTime",
    "TIMESTAMP": "DateTime",
    "TIMESTAMP WITH TIME ZONE": "DateTime",
}
_HINTS = {
    401: "The sign-in was not accepted: test the workspace connection.",
    403: "This sign-in may not do that: it must be a member (or admin) of the workspace.",
    404: "The workspace has no such dataset or table: check its name.",
    429: "Too many requests to Power BI: wait a minute (a push dataset takes 120 requests a minute).",
}


def push_type(duck: str) -> str:
    """A DuckDB type as a push dataset's column type."""
    if duck.startswith("DECIMAL"):
        return "Double"
    return _TYPES.get(duck, "String")


class PushWrite(Write):
    """A write to a table of a Power BI push dataset in the workspace of a Power BI connection."""

    def __init__(
        self, connection: Any, dataset: str, table: str, what: str, rows: Any = None, dry_run: bool = True
    ) -> None:
        name, conn = live(connection)
        if not (hasattr(conn, "url") and hasattr(conn, "dataset") and hasattr(conn, "access_token")):
            raise WriteError(
                f"{name} is not a Power BI workspace connection: these starters push to Power BI."
            )
        super().__init__(name, f"{dataset}/{table}", what, rows, dry_run)
        self.conn, self.dataset, self.table = conn, str(dataset), str(table)
        self.found: dict[str, Any] | None = None

    # ===== the dataset =====

    def lookup(self) -> dict[str, Any] | None:
        """The workspace's dataset of that name (any case): its id, and whether it takes rows."""
        listed = self._call("GET", "/datasets") or {}
        wanted = self.dataset.casefold()
        self.found = next(
            (d for d in listed.get("value") or [] if str(d.get("name", "")).casefold() == wanted), None
        )
        return self.found

    def check_new(self) -> None:
        if self.lookup() is not None:
            raise WriteError(
                f"The workspace has a dataset {self.dataset} already: the Power BI push rows starter adds "
                "to it."
            )
        self.fact("Dataset", f"{self.dataset} (new)")

    def check_push(self) -> bool:
        """True: a push dataset with that table; False: no such dataset (it is made). A model, or a push
        dataset without that table, stops the write in plain words."""
        found = self.lookup()
        if found is None:
            self.fact("Dataset", f"{self.dataset} (not there: made as a push dataset)")
            return False
        if not found.get("addRowsAPIEnabled"):
            raise WriteError(
                f"{self.dataset} is a model, not a push dataset: Power BI's models are not written row "
                "by row. "
                "Write its source, then refresh it (the Power BI refresh dataset starter)."
            )
        tables = [
            str(t.get("name"))
            for t in (self._call("GET", f"/datasets/{found['id']}/tables") or {}).get("value") or []
        ]
        if self.table not in tables:
            raise WriteError(
                f"The push dataset {self.dataset} has no table {self.table}: it has "
                f"{', '.join(tables) or 'none'}."
            )
        self.fact("Dataset", f"{self.dataset} (a push dataset)")
        return True

    def column_types(self) -> str:
        return ", ".join(f"{n} ({push_type(t)})" for n, t in self.need_rows().columns)

    def requests(self) -> int:
        count = self.need_rows().count
        return -(-count // ROWS_A_REQUEST) if count else 0

    # ===== the writes =====

    def create(self) -> str:
        """The push dataset, made with one table of the rows' columns. Its id."""
        columns = [{"name": n, "dataType": push_type(t)} for n, t in self.need_rows().columns]
        body = {
            "name": self.dataset,
            "defaultMode": "Push",
            "tables": [{"name": self.table, "columns": columns}],
        }
        made = self._call("POST", "/datasets?defaultRetentionPolicy=None", body) or {}
        self.found = {"id": made.get("id"), "name": self.dataset, "addRowsAPIEnabled": True}
        return str(made.get("id"))

    def clear(self) -> None:
        """Every row of the table removed."""
        self._call("DELETE", f"{self._rows_path()}")

    def push(self) -> int:
        """The rows pushed, 10,000 a request. The rows pushed."""
        rows = self.need_rows()
        path = self._rows_path()
        try:
            return each_batch(
                rows.records(ROWS_A_REQUEST, plain_value),
                lambda batch: self._call("POST", path, {"rows": batch}),
            )
        except Exception as failed:
            before = getattr(failed, "before", 0)
            where = failed.where() if hasattr(failed, "where") else "the push"
            went = f"the {before:,} rows before it went in" if before else "no row went in"
            raise WriteError(
                f"{where[:1].upper()}{where[1:]} failed: {failed} A push dataset has no transactions: {went}."
            ) from None

    def _rows_path(self) -> str:
        if not self.found or not self.found.get("id"):
            self.check_push()
        if self.found is None:
            raise WriteError(f"There is no dataset {self.dataset} in the workspace.")
        return f"/datasets/{self.found['id']}/tables/{urllib.parse.quote(self.table, safe='')}/rows"

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        """One request to Power BI's REST API under the workspace, waited out on 429."""
        data = None if body is None else json.dumps(body).encode()
        for attempt in range(WAITS + 1):
            token = self.conn.access_token()
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            request = urllib.request.Request(self.conn.url + path, data, headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=120) as answer:
                    raw = answer.read()
                    return json.loads(raw) if raw.strip() else None
            except urllib.error.HTTPError as refused:
                wait = refused.headers.get("Retry-After") or ""
                if refused.code == 429 and attempt < WAITS:
                    time.sleep(min(float(wait) if wait.strip().isdigit() else 2.0**attempt, 120.0))
                    continue
                raise WriteError(_plain(refused.code, refused.read())) from None
            except urllib.error.URLError as error:
                raise WriteError(f"Power BI could not be reached: {error.reason}") from None
        raise WriteError("Power BI kept asking to wait (429).")


def _plain(status: int, body: bytes) -> str:
    try:
        said = json.loads(body)
        error = said.get("error", said) if isinstance(said, dict) else said
        message = (error.get("message") or error.get("code")) if isinstance(error, dict) else error
    except ValueError:
        message = body.decode("utf-8", "replace")[:300]
    first = str(message or "no reason given").strip().splitlines()[0]
    return f"Power BI refused ({status}): {first}. {_HINTS.get(status, '')}".strip()


__all__ = ["PushWrite", "WriteError", "push_type"]
