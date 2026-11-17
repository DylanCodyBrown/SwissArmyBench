# ruff: noqa: E501 (the connections' code is text, written as it runs; its lines are its own)
"""SharePoint as two connections, through Microsoft Graph (the owner, 2026-11-17: "SharePoint should be for
the things we can convert to tables for the grid" / "There can be a generic SharePoint connection type for
retrieving documents" / "Those documents could be csvs, or an Excel file which we could turn into a
table").

- SharePoint lists (`sharepoint`): a site's lists, and only lists, each a table: read through Graph with
  paging, its columns typed from the list's column definitions (a choice as its text, a lookup and a
  person as their display text with the id beside it, `<name>_id`), `$select` and `$filter` sent (a
  filter Graph refuses is applied by DuckDB instead: it applies every filter again). Its writes are
  blades: create, update by id or a key column, delete, batched with Graph's $batch and retried on 429.
- SharePoint documents (`sharepoint_docs`): each document library's file index as a table (name, folder,
  extension, size, created and modified and by whom, the content type, the library's own columns, the
  web link), and its tabular documents as tables too: each CSV, Parquet and JSON-lines file, and each
  workbook's sheets and named tables, under their library and folders. Read into memory only (never
  written to disk), kept by the file's eTag so an unchanged file is not downloaded twice. Other documents
  (PDF, Word, pictures) are not tables: blades download, upload and read them (the SharePoint family).

Both sign in through domain/entra.py (a username and password first: ROPC; as you; a managed identity;
an app registration) for Graph's scope. One Graph client for both (`Graph`). SWISSARMYBENCH_GRAPH_URL
moves Graph elsewhere (in the tests, to a stand-in on this computer).

This file is text and a few rules. Pure: no I/O.
"""

from __future__ import annotations

from swissarmybench.domain import entra
from swissarmybench.domain import lake_code as code

GRAPH_VARIABLE: str = "SWISSARMYBENCH_GRAPH_URL"
BATCH: int = 20  # requests in one Graph $batch (Graph's own most)
MAX_WORKBOOK_BYTES: int = 25 * 1024 * 1024  # a workbook read for its sheets' names
MAX_WORKBOOKS: int = 100  # workbooks a catalog looks into

_PLACE = """
# The site: its address (https://<tenant>.sharepoint.com/sites/<name>).
site_url = "https://my-company.sharepoint.com/sites/my-site"
"""
_DOCS_PLACE = """
# The site: its address (https://<tenant>.sharepoint.com/sites/<name>). A library's documents: header_row
# is the row of a sheet or CSV that holds the column names (1: the first).
site_url = "https://my-company.sharepoint.com/sites/my-site"
header_row = 1
"""

GRAPH: str = (
    f"""
# Requests in one Graph $batch (Graph's own most); a workbook read for its sheets' names, at most; the
# most workbooks a catalog looks into.
BATCH, MAX_WORKBOOK_BYTES, MAX_WORKBOOKS = {BATCH}, {MAX_WORKBOOK_BYTES}, {MAX_WORKBOOKS}
"""  # noqa: S608 (code as text: its words, not a query)
    + r'''

class SharePointError(LakeError):
    """Graph refused, or a list or document cannot be read as asked: the message says why."""


class Graph:
    """Microsoft Graph for one site, signed in once (the token in memory only)."""

    def __init__(self, site_url, token):
        self.base = os.environ.get("SWISSARMYBENCH_GRAPH_URL", "https://graph.microsoft.com/v1.0").rstrip("/")
        parts = urllib.parse.urlsplit(str(site_url).strip())
        if not parts.hostname or parts.scheme not in ("https", "http"):
            raise SharePointError(
                f"The site's address is https://<tenant>.sharepoint.com/sites/<name>, not {site_url!r}.")
        self.host, self.path, self.token = parts.hostname, parts.path.rstrip("/"), token
        self._site = None

    def _headers(self, more=None):
        return {"Authorization": f"Bearer {self.token()}", "Accept": "application/json"} | (more or {})

    def get(self, path, what, prefer=None, raw=False):
        """One GET (a path under Graph's root, or a next page's whole address)."""
        if "://" in path and not path.startswith(self.base + "/"):
            raise SharePointError(f"{what}: Graph sent an address outside {self.base}; it is not followed.")
        address = path if "://" in path else f"{self.base}/{path.lstrip('/')}"
        headers = self._headers({"Prefer": prefer} if prefer else None)
        for attempt in range(4):
            try:
                return ask(address, None, headers, what, raw=raw)
            except AzureError as error:
                if "(429)" in str(error) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise SharePointError(str(error)) from None
        raise SharePointError(f"{what}: Graph kept saying to wait.")

    def send(self, method, path, body, what):
        """One change (POST, PATCH, DELETE), as JSON."""
        data = json.dumps(body).encode() if body is not None else b""
        headers = self._headers({"Content-Type": "application/json"})
        try:
            return ask(f"{self.base}/{path.lstrip('/')}", data, headers, what, method=method)
        except AzureError as error:
            raise SharePointError(str(error)) from None

    def upload(self, path, data, what):
        """A file's bytes PUT to a path (a library's, up to 250 MB in one request)."""
        headers = self._headers({"Content-Type": "application/octet-stream"})
        try:
            return ask(f"{self.base}/{path.lstrip('/')}", data, headers, what, method="PUT")
        except AzureError as error:
            raise SharePointError(str(error)) from None

    def batch(self, requests, what):
        """Requests sent BATCH at a time with Graph's $batch, each retried on 429 (after its Retry-After):
        each one's answer {"id", "status", "body"}, in order."""
        answers = {}
        todo = [dict(r, id=str(i)) for i, r in enumerate(requests)]
        attempt = 0
        while todo:
            chunk, todo = todo[:BATCH], todo[BATCH:]
            sent = self.send("POST", "$batch", {"requests": chunk}, what)
            again, wait = [], 0
            for r in sent.get("responses") or []:
                if int(r.get("status", 0)) == 429 and attempt < 5:
                    again.append(next(c for c in chunk if c["id"] == str(r["id"])))
                    wait = max(wait, int((r.get("headers") or {}).get("Retry-After", 1)))
                else:
                    answers[str(r["id"])] = r
            if again:
                attempt += 1
                time.sleep(min(wait, 30))
                todo = again + todo
        return [answers[str(i)] for i in range(len(requests))]

    def pages(self, path, what, limit=None, prefer=None):
        """Every item of a paged answer (@odata.nextLink) until `limit` (None: every one)."""
        found, at = [], path
        while at:
            answer = self.get(at, what, prefer)
            found += answer.get("value") or []
            if limit is not None and len(found) >= limit:
                return found[:limit]
            at = answer.get("@odata.nextLink")
        return found

    def site(self):
        """The site's id, found once by its address."""
        if self._site is None:
            found = self.get(f"sites/{self.host}:{self.path or '/'}", "Finding the site")
            self._site = str(found.get("id") or "")
            if not self._site:
                raise SharePointError(f"Graph found no site at https://{self.host}{self.path}.")
        return self._site


SYSTEM = {"ContentType", "Attachments", "Edit", "LinkTitleNoMenu", "LinkTitle", "DocIcon", "ItemChildCount",
          "FolderChildCount", "_ComplianceFlags", "_ComplianceTag", "_ComplianceTagWrittenTime",
          "_ComplianceTagUserId", "_IsRecord", "AppAuthor", "AppEditor", "_UIVersionString", "ComplianceAssetId",
          "_ColorTag", "FileLeafRef", "FileRef", "FileSizeDisplay", "_CheckinComment", "LinkFilenameNoMenu",
          "LinkFilename", "ParentVersionString", "ParentLeafName", "CheckoutUser", "_ExtendedDescription",
          "MediaServiceImageTags", "TriggerFlowInfo", "_DisplayName", "SelectTitle", "SelectFilename"}


def column_kind(c):
    """A list column's kind and its DuckDB type: text, number, boolean, dateTime, choice, lookup, person."""
    for facet, kind in (("lookup", ("lookup", "VARCHAR")), ("personOrGroup", ("person", "VARCHAR")),
                        ("number", ("number", "DOUBLE")), ("currency", ("number", "DOUBLE")),
                        ("boolean", ("boolean", "BOOLEAN")), ("dateTime", ("dateTime", "TIMESTAMP")),
                        ("choice", ("choice", "VARCHAR")), ("hyperlinkOrPicture", ("link", "VARCHAR")),
                        ("calculated", ("text", "VARCHAR")), ("text", ("text", "VARCHAR"))):
        if facet in c:
            return kind
    return ("text", "VARCHAR")


def value_of(value, kind):
    """A field's value as a cell: a date as a date, a several-choice as its texts joined by "; ", a link
    as its address."""
    if value is None:
        return None
    if isinstance(value, list):
        return "; ".join(str(v.get("LookupValue", v) if isinstance(v, dict) else v) for v in value)
    if kind == "link" and isinstance(value, dict):
        return value.get("Url")
    if kind == "dateTime" and isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if kind == "number" and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def odata_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return f"'{text}T00:00:00Z'"
    return "'" + text.replace("'", "''") + "'"


ODATA_OPS = {"=": "eq", "<>": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}


def odata_filter(filters, fields):
    """The filters sent with a read as Graph's $filter on list fields (`fields` maps a column's name to
    its internal name): =, <>, <, <=, >, >=, IN and BETWEEN; the rest are left to DuckDB."""
    parts = []
    for column, op, value in filters or []:
        name = fields.get(str(column).casefold())
        if name is None:
            continue
        field = f"fields/{name}"
        if op in ODATA_OPS:
            parts.append(f"{field} {ODATA_OPS[op]} {odata_value(value)}")
        elif op == "in" and value:
            parts.append("(" + " or ".join(f"{field} eq {odata_value(v)}" for v in value) + ")")
        elif op == "between":
            parts.append(f"{field} ge {odata_value(value[0])} and {field} le {odata_value(value[1])}")
    return " and ".join(parts)


class Site:
    """What both SharePoint connections share: Graph, the site, a list's columns and its items as rows."""

    def __init__(self, site_url, token):
        self.graph = Graph(site_url, token)
        self.found, self._columns, self._lookups, self._duck, self.how = None, {}, {}, None, "graph"

    def all_lists(self):
        if not hasattr(self, "_lists"):
            path = f"sites/{self.graph.site()}/lists?$select=id,name,displayName,list,webUrl&$top=999"
            self._lists = self.graph.pages(path, "Listing the site's lists")
        return self._lists

    def columns(self, list_id):
        """A list's columns as rows give them: {"name" (its display name), "field" (Graph's), "kind",
        "type", "indexed", "target" (a lookup's list and column)}."""
        if list_id not in self._columns:
            path = f"sites/{self.graph.site()}/lists/{list_id}/columns?$top=999"
            found = []
            for c in self.graph.pages(path, "Reading the list's columns"):
                if c.get("hidden") or c.get("name") in SYSTEM:
                    continue
                kind, duck = column_kind(c)
                found.append({"name": str(c.get("displayName") or c["name"]), "field": str(c["name"]),
                              "kind": kind, "type": duck, "indexed": bool(c.get("indexed")),
                              "target": c.get("lookup") or {}})
            self._columns[list_id] = found
        return self._columns[list_id]

    def lookup_texts(self, target, ids):
        """A lookup's or a person's display texts by item id (read once per list): {id: text}."""
        list_id = target.get("listId") or "User Information List"
        column = target.get("columnName") or "Title"
        key = (list_id, column)
        if key not in self._lookups:
            if list_id == "User Information List":
                users = [l for l in self.all_lists() if l.get("name") in ("users", "User Information List")
                         or l.get("displayName") == "User Information List"]
                list_id = users[0]["id"] if users else "User Information List"
            path = (f"sites/{self.graph.site()}/lists/{urllib.parse.quote(list_id)}/items"
                    f"?$expand=fields($select={column})&$top=999")
            try:
                rows = self.graph.pages(path, "Reading a lookup's texts")
            except SharePointError:
                rows = []
            self._lookups[key] = {str(r.get("id")): (r.get("fields") or {}).get(column) for r in rows}
        found = self._lookups[key]
        return {i: found.get(str(i)) for i in ids}

    def items(self, list_id, columns, limit=None, filters=None):
        """A list's items as rows (each column by its display name; a lookup or person as its text with
        `<name>_id`), with $select, the filters as $filter (applied again by DuckDB) and $top."""
        fields = {c["name"].casefold(): c["field"] for c in columns if c["kind"] in ("text", "number", "dateTime", "choice", "boolean")}
        selected = []
        for c in columns:
            selected.append(c["field"] + ("LookupId" if c["kind"] in ("lookup", "person") else ""))
        top = 999 if limit is None else max(1, min(999, int(limit)))
        base = (f"sites/{self.graph.site()}/lists/{list_id}/items?$expand=fields($select="
                f"{','.join(selected)})&$top={top}")
        where = odata_filter(filters, fields)
        records = None
        if where:
            try:
                records = self.graph.pages(base + "&$filter=" + urllib.parse.quote(where), "Reading the list",
                                           limit, "HonorNonIndexedQueriesWarningMayFailRandomly")
                self.how = "graph ($filter sent)"
            except SharePointError:
                records = None  # Graph refused the filter (a column not indexed): DuckDB applies it
        if records is None:
            records = self.graph.pages(base, "Reading the list", limit)
            self.how = "graph"
        rows = []
        for r in records:
            got = r.get("fields") or {}
            row = {"id": int(r["id"]) if str(r.get("id", "")).isdigit() else r.get("id")}
            for c in columns:
                if c["kind"] in ("lookup", "person"):
                    found = got.get(c["field"] + "LookupId")
                    row[c["name"] + "_id"] = int(found) if str(found).isdigit() else found
                else:
                    row[c["name"]] = value_of(got.get(c["field"]), c["kind"])
            rows.append(row)
        for c in columns:
            if c["kind"] in ("lookup", "person"):
                ids = {row[c["name"] + "_id"] for row in rows if row[c["name"] + "_id"] is not None}
                texts = self.lookup_texts(c["target"] if c["kind"] == "lookup" else {}, ids) if ids else {}
                for row in rows:
                    row[c["name"]] = texts.get(row[c["name"] + "_id"])
        return rows

    def duck(self):
        if self._duck is None:
            self._duck = duckdb.connect()
        return self._duck

    def finish(self, rows, names, types, limit, columns, filters, frame, how):
        """Rows (dicts) as Arrow through DuckDB: the columns asked for, every filter applied again, the
        count, the first `limit`; how it was read in the metadata."""
        import pyarrow as pa

        if rows:
            table = pa.Table.from_pylist([{n: r.get(n) for n in names} for r in rows])
        else:
            table = pa.table({n: pa.array([], pa.string()) for n in names})
        return self.finish_arrow(table, limit, columns, filters, frame, how)

    def finish_arrow(self, table, limit, columns, filters, frame, how):
        duck = self.duck()
        duck.register("sab_rows", table)
        try:
            known = list(table.column_names)
            where, params = where_of(filters, known)
            by_name = {k.casefold(): k for k in known}
            picked = [by_name[str(c).casefold()] for c in columns or [] if str(c).casefold() in by_name]
            listed = ", ".join(ident(c) for c in picked) if picked else "*"
            clause = f" WHERE {where}" if where else ""
            total = duck.execute(f"SELECT count(*) FROM sab_rows{clause}", params).fetchall()[0][0]
            tail = f" LIMIT {int(limit)}" if limit is not None else ""
            result = arrow_of(duck.execute(f"SELECT {listed} FROM sab_rows{clause}{tail}", params))
        finally:
            duck.unregister("sab_rows")
        result = result.replace_schema_metadata({b"sab_read": how.encode()})
        if frame:
            try:
                return result.to_pandas(), int(total)
            except ImportError:
                return result, int(total)
        return result, int(total)

    def read(self, table, schema="", columns=None, filters=None, limit=None):
        """A table's rows as a DataFrame (Arrow without pandas)."""
        return self.rows(table, schema, limit, columns, filters, frame=True)[0]

    def tested(self, rows=20):
        """Test: it signed in and found the site; how many tables it has, and the first one's first rows."""
        listed = self.tables()
        found = {"found": f"signed in and found {len(listed)} table{'' if len(listed) == 1 else 's'}"}
        if listed:
            got, total = self.rows(listed[0]["table"], listed[0]["schema"], rows)
            found["preview"] = {"table": listed[0]["table"], "rows": got.to_pylist(), "total": total}
        return found

    def cursor(self):
        raise SharePointError("SharePoint has no SQL of its own: name its tables in DuckDB SQL "
                              "([Connection].Tasks) or read one with sab.read.")

    def close(self):
        if self._duck is not None:
            self._duck.close()
            self._duck = None


class SharePointLists(Site):
    """A SharePoint site's lists, each a table.

        conn.tables()                        each list: its name and id
        conn.read("Tasks")                   its items (a DataFrame), typed by its columns
        conn.read("Tasks", columns=["Title", "Status"], filters=[["Status", "=", "Open"]], limit=50)
        conn.create("Tasks", rows)           new items (rows: a list of dicts by column name)
        conn.update("Tasks", rows, key="id") items changed, found by id or a key column
        conn.delete("Tasks", ids)            items deleted by id
    """

    def tables(self):
        if self.found is None:
            self.found = []
            for l in self.all_lists():
                info = l.get("list") or {}
                if info.get("hidden") or info.get("template") in ("documentLibrary", "webPageLibrary"):
                    continue
                self.found.append({"schema": "", "table": str(l.get("displayName") or l.get("name")),
                                   "id": str(l["id"]), "web": l.get("webUrl", "")})
            if not self.found:
                raise SharePointError("The site has no lists this sign-in may read.")
        return [dict(t) for t in self.found]

    def table(self, name, schema=""):
        wanted = str(name).strip().casefold()
        for t in self.tables():
            if wanted in (t["table"].casefold(), t["id"].casefold()):
                return t
        some = ", ".join(t["table"] for t in self.tables()[:12])
        raise SharePointError(f"The site has no list {name!r}. It has: {some}.")

    def catalog(self):
        rows = []
        for t in self.tables():
            place = {"table_schema": "", "table_name": t["table"], "table_type": "TABLE"}
            columns = self.columns(t["id"])
            rows.append(place | {"column_name": "", "data_type": "", "description": "SharePoint list"})
            rows.append(place | {"column_name": "id", "data_type": "BIGINT", "description": "the item's id"})
            for c in columns:
                indexed = ", indexed" if c["indexed"] else ""
                rows.append(place | {"column_name": c["name"], "data_type": c["type"],
                                     "description": f"{c['kind']}{indexed} ({c['field']})"})
                if c["kind"] in ("lookup", "person"):
                    rows.append(place | {"column_name": c["name"] + "_id", "data_type": "BIGINT",
                                         "description": f"the {c['kind']}'s id"})
        return rows

    def rows(self, table, schema="", limit=None, columns=None, filters=None, frame=False):
        t = self.table(table, schema)
        known = self.columns(t["id"])
        wanted = {str(c).casefold() for c in columns or []}
        picked = [c for c in known if not wanted or c["name"].casefold() in wanted
                  or (c["name"] + "_id").casefold() in wanted or any(str(f[0]).casefold() in
                      (c["name"].casefold(), (c["name"] + "_id").casefold()) for f in filters or [])]
        # Every row the filters could match: a limit is sent only when DuckDB has nothing to filter.
        asked = limit if not filters else None
        rows = self.items(t["id"], picked, asked, filters)
        names = ["id"]
        for c in picked:
            names += [c["name"], c["name"] + "_id"] if c["kind"] in ("lookup", "person") else [c["name"]]
        return self.finish(rows, names, None, limit, columns, filters, frame, self.how)

    # ===== writes (the Write blades): Graph's $batch, retried on 429 =====

    def _fields(self, t, row):
        by_name = {c["name"].casefold(): c for c in self.columns(t["id"])}
        out = {}
        for name, value in row.items():
            if str(name).casefold() in ("id",):
                continue
            c = by_name.get(str(name).casefold())
            if c is None:
                if str(name).casefold().endswith("_id") and by_name.get(str(name)[:-3].casefold()):
                    out[by_name[str(name)[:-3].casefold()]["field"] + "LookupId"] = value
                    continue
                raise SharePointError(f"{t['table']} has no column {name!r}.")
            if c["kind"] in ("lookup", "person"):
                continue  # its _id is written, not its text
            if isinstance(value, (datetime.date, datetime.datetime)):
                value = value.isoformat()
            out[c["field"]] = value
        return out

    def create(self, table, rows):
        t = self.table(table)
        base = f"/sites/{self.graph.site()}/lists/{t['id']}/items"
        sent = [{"method": "POST", "url": base, "headers": {"Content-Type": "application/json"},
                 "body": {"fields": self._fields(t, r)}} for r in rows]
        return self._done(self.graph.batch(sent, f"Adding items to {t['table']}"))

    def update(self, table, rows, key="id"):
        t = self.table(table)
        ids = self.ids(table, [r[key] for r in rows], key)
        base = f"/sites/{self.graph.site()}/lists/{t['id']}/items"
        sent = [{"method": "PATCH", "url": f"{base}/{ids[r[key]]}/fields",
                 "headers": {"Content-Type": "application/json"}, "body": self._fields(t, r)} for r in rows]
        return self._done(self.graph.batch(sent, f"Changing items of {t['table']}"))

    def delete(self, table, ids):
        t = self.table(table)
        base = f"/sites/{self.graph.site()}/lists/{t['id']}/items"
        sent = [{"method": "DELETE", "url": f"{base}/{i}"} for i in ids]
        return self._done(self.graph.batch(sent, f"Deleting items of {t['table']}"))

    def ids(self, table, values, key="id"):
        """Each key value's item id (key "id": the ids themselves). A value no item has, or two have, is
        said."""
        if key == "id":
            return {v: v for v in values}
        found = self.rows(table, columns=["id", key])[0].to_pylist()
        by_value = {}
        for r in found:
            by_value.setdefault(r[key], []).append(r["id"])
        missing = [v for v in values if v not in by_value]
        twice = [v for v in values if len(by_value.get(v, [])) > 1]
        if missing or twice:
            raise SharePointError(
                (f"No item has {key} {missing[0]!r}. " if missing else "")
                + (f"Several items have {key} {twice[0]!r}: use id." if twice else ""))
        return {v: by_value[v][0] for v in values}

    def _done(self, answers):
        failed = [a for a in answers if int(a.get("status", 0)) >= 400]
        if failed:
            body = failed[0].get("body") or {}
            message = (body.get("error") or {}).get("message", "") if isinstance(body, dict) else ""
            raise SharePointError(f"{len(failed)} of {len(answers)} changes were refused: "
                                  f"{failed[0].get('status')} {message}".strip())
        return {"done": len(answers)}


DOC_FIELDS = (("name", "VARCHAR"), ("folder", "VARCHAR"), ("extension", "VARCHAR"), ("size", "BIGINT"),
              ("created", "TIMESTAMP"), ("created_by", "VARCHAR"), ("modified", "TIMESTAMP"),
              ("modified_by", "VARCHAR"), ("content_type", "VARCHAR"), ("web_url", "VARCHAR"),
              ("id", "VARCHAR"), ("etag", "VARCHAR"))
TABULAR = {"csv": "csv", "tsv": "csv", "parquet": "parquet", "jsonl": "json", "ndjson": "json",
           "xlsx": "excel", "xlsm": "excel"}


def workbook_parts(data):
    """A workbook's sheets and named tables (their names and ranges), read from its XML: stdlib only."""
    sheets, tables = [], []
    with zipfile.ZipFile(io.BytesIO(data)) as book:
        names = book.namelist()
        text = book.read("xl/workbook.xml").decode("utf-8", "replace")
        sheets = [html_text(s) for s in re.findall(r"<sheet\b[^>]*\bname=\"([^\"]+)\"", text)]
        for n in sorted(n for n in names if re.fullmatch(r"xl/tables/table\d+\.xml", n)):
            found = book.read(n).decode("utf-8", "replace")
            name = re.search(r"<table\b[^>]*\bdisplayName=\"([^\"]+)\"", found)
            ref = re.search(r"<table\b[^>]*\bref=\"([^\"]+)\"", found)
            if name and ref:
                tables.append((html_text(name.group(1)), ref.group(1)))
    return sheets, tables


def html_text(text):
    return (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            .replace("&apos;", "'"))


class SharePointDocuments(Site):
    """A SharePoint site's document libraries: each one's file index a table, and its tabular documents
    (CSV, Parquet, JSON lines; a workbook's sheets and named tables) tables too.

        conn.tables()                          the index tables and the tabular documents
        conn.read("Documents")                 a library's file index (a DataFrame)
        conn.read("Documents/Finance/Budget 2026.xlsx/Summary")   a sheet (or a named table)
        conn.files("Documents", "Finance")     a folder's files: names, sizes, dates (a small table)
        conn.download("Documents/Finance/Budget 2026.xlsx")       its bytes (kept by its eTag)
        conn.frame("Documents/Finance/Budget 2026.xlsx", sheet="Summary")   a document as a DataFrame
        conn.text("Documents/Policies/Travel.docx")               a Word or PDF document's text
        conn.upload("Documents/Finance/out.csv", data)            bytes (or a DataFrame) uploaded
    """

    def __init__(self, site_url, token, header_row=1):
        super().__init__(site_url, token)
        self.header_row, self._files, self._index = max(1, int(header_row)), {}, {}

    def libraries(self):
        if not hasattr(self, "_drives"):
            path = f"sites/{self.graph.site()}/drives?$select=id,name,driveType,webUrl"
            self._drives = [d for d in self.graph.pages(path, "Listing the site's libraries")
                            if d.get("driveType", "documentLibrary") == "documentLibrary"]
            if not self._drives:
                raise SharePointError("The site has no document libraries this sign-in may read.")
        return self._drives

    def library(self, name):
        for d in self.libraries():
            if str(d["name"]).casefold() == str(name).strip().casefold() or d["id"] == name:
                return d
        some = ", ".join(d["name"] for d in self.libraries())
        raise SharePointError(f"The site has no library {name!r}. It has: {some}.")

    def library_columns(self, drive):
        """A library's own columns (the ones its people fill in), as a list's columns."""
        path = f"drives/{drive['id']}/list?$select=id"
        try:
            list_id = self.graph.get(path, "Finding the library's list").get("id")
        except SharePointError:
            return []
        return [c for c in self.columns(list_id) if c["field"] not in ("Title",) and c["kind"] != "lookup"
                and c["field"] not in ("Created", "Modified", "Author", "Editor")]

    def index(self, drive, limit=None):
        """A library's file index: one row per file (folders are its rows' folder), with its own columns."""
        key = drive["id"]
        if key in self._index and limit is None:
            return self._index[key]
        own = self.library_columns(drive)
        select = ",".join(["FileLeafRef", "FileRef", "ContentType"] + [c["field"] for c in own])
        path = (f"drives/{drive['id']}/list/items?$expand=driveItem,fields($select={select})&$top=999")
        rows = []
        for r in self.graph.pages(path, f"Reading {drive['name']}'s files"):
            item = r.get("driveItem") or {}
            if "folder" in item:
                continue
            fields = r.get("fields") or {}
            parent = str((item.get("parentReference") or {}).get("path") or "")
            folder = parent.split("root:", 1)[1].strip("/") if "root:" in parent else ""
            name = str(item.get("name") or fields.get("FileLeafRef") or "")
            row = {
                "name": name,
                "folder": folder,
                "extension": name.rsplit(".", 1)[1].lower() if "." in name else "",
                "size": int(item.get("size") or 0),
                "created": value_of(item.get("createdDateTime"), "dateTime"),
                "created_by": ((item.get("createdBy") or {}).get("user") or {}).get("displayName"),
                "modified": value_of(item.get("lastModifiedDateTime"), "dateTime"),
                "modified_by": ((item.get("lastModifiedBy") or {}).get("user") or {}).get("displayName"),
                "content_type": (fields.get("ContentType") if isinstance(fields.get("ContentType"), str)
                                 else (item.get("file") or {}).get("mimeType")),
                "web_url": item.get("webUrl"),
                "id": item.get("id"),
                "etag": item.get("eTag"),
            }
            for c in own:
                row[c["name"]] = value_of(fields.get(c["field"]), c["kind"])
            rows.append(row)
        self._index[key] = (rows, own)
        return rows, own

    def download(self, path):
        """A document's bytes, by its path (library/folders/name) or a file index row, kept by its eTag:
        an unchanged file is downloaded once."""
        drive, item = self.find(path)
        tag = item.get("etag") or item.get("eTag")
        kept = self._files.get(item["id"])
        if kept is not None and kept[0] == tag:
            return kept[1]
        data, _ = self.graph.get(f"drives/{drive['id']}/items/{item['id']}/content", f"Reading {item['name']}",
                                 raw=True)
        self._files[item["id"]] = (tag, data)
        return data

    def find(self, path):
        """A document by its path (library/folders/name) or a file index row (a dict with id, folder)."""
        if isinstance(path, dict):
            library = path.get("library") or self.libraries()[0]["name"]
            path = "/".join(p for p in (library, path.get("folder"), path.get("name")) if p)
        parts = [p for p in str(path).replace("\\", "/").split("/") if p]
        if len(parts) < 2:
            raise SharePointError(f"Name the document as library/folders/name, not {path!r}.")
        drive = self.library(parts[0])
        rows, _ = self.index(drive)
        folder, name = "/".join(parts[1:-1]), parts[-1]
        for r in rows:
            if r["name"].casefold() == name.casefold() and r["folder"].casefold() == folder.casefold():
                return drive, r
        raise SharePointError(f"{drive['name']} has no document {'/'.join(parts[1:])!r}.")

    def files(self, library=None, folder=None):
        """A library's files (in a folder and below, or all): name, folder, size, modified, by whom."""
        drive = self.library(library) if library else self.libraries()[0]
        rows, _ = self.index(drive)
        wanted = (folder or "").strip("/").casefold()
        picked = [r for r in rows if not wanted or r["folder"].casefold() == wanted
                  or r["folder"].casefold().startswith(wanted + "/")]
        keys = ("name", "folder", "extension", "size", "modified", "modified_by", "web_url")
        return frame_of([{k: r[k] for k in keys} for r in picked], keys)

    def tables(self):
        """Each library's file index, then each tabular document (a workbook: a table per sheet and per
        named table), under its library and folders."""
        if self.found is None:
            found, books = [], 0
            for d in self.libraries():
                found.append({"schema": "", "table": d["name"], "kind": "index", "drive": d})
                rows, _ = self.index(d)
                for r in rows:
                    kind = TABULAR.get(r["extension"])
                    if kind is None:
                        continue
                    schema = "/".join(p for p in (d["name"], r["folder"]) if p)
                    if kind != "excel":
                        found.append({"schema": schema, "table": r["name"], "kind": kind, "drive": d, "file": r})
                        continue
                    if books >= MAX_WORKBOOKS or r["size"] > MAX_WORKBOOK_BYTES:
                        continue
                    books += 1
                    try:
                        sheets, named = workbook_parts(self.download({"library": d["name"], **r}))
                    except (SharePointError, zipfile.BadZipFile, KeyError):
                        continue
                    for s in sheets:
                        found.append({"schema": schema, "table": f"{r['name']}/{s}", "kind": "sheet",
                                      "drive": d, "file": r, "sheet": s})
                    for n, ref in named:
                        if n.casefold() not in {s.casefold() for s in sheets}:
                            found.append({"schema": schema, "table": f"{r['name']}/{n}", "kind": "named",
                                          "drive": d, "file": r, "sheet": n, "ref": ref})
            self.found = found
        return [dict(t) for t in self.found]

    def table(self, name, schema=""):
        wanted = [p.casefold() for p in f"{schema}/{name}".replace("\\", "/").split("/") if p]
        found = self.tables()
        hits = []
        for t in found:
            path = [p.casefold() for p in f"{t['schema']}/{t['table']}".split("/") if p]
            stem = path[:-1] + [path[-1].rsplit(".", 1)[0]]
            if path[-len(wanted):] == wanted or stem[-len(wanted):] == wanted:
                hits.append((len(path) == len(wanted), t))
        exact = [t for full, t in hits if full]
        picked = exact if len(exact) == 1 else [t for _, t in hits]
        if len(picked) == 1:
            return picked[0]
        if picked:
            some = ", ".join(f"{t['schema']}/{t['table']}".strip("/") for t in picked[:8])
            raise SharePointError(f"{name!r} could be {some}: name its folders too.")
        some = ", ".join(f"{t['schema']}/{t['table']}".strip("/") for t in found[:12])
        raise SharePointError(f"The site has no library or document {name!r}. It has: {some}.")

    def catalog(self):
        rows = []
        for t in self.tables():
            place = {"table_schema": t["schema"], "table_name": t["table"], "table_type": "TABLE"}
            if t["kind"] == "index":
                rows.append(place | {"column_name": "", "data_type": "", "description": "the library's file index"})
                _, own = self.index(t["drive"])
                rows += [place | {"column_name": n, "data_type": k, "description": ""} for n, k in DOC_FIELDS]
                rows += [place | {"column_name": c["name"], "data_type": c["type"],
                                  "description": f"the library's own column ({c['field']})"} for c in own]
                continue
            words = {"sheet": "a workbook's sheet", "named": f"a workbook's named table ({t.get('ref')})"}.get(
                t["kind"], f"a {t['kind'].upper()} document")
            try:  # its columns: the document read (once: kept by its eTag)
                found = self.rows(t["table"], t["schema"], limit=0)[0]
            except (SharePointError, LakeError, ImportError, ValueError, KeyError) as error:
                folder = {"table_schema": t["schema"], "table_name": "", "table_type": "TABLE", "column_name": ""}
                rows.append(folder | {"data_type": "", "description": f"{t['table']}: not read: {str(error)[:160]}"})
                continue
            rows.append(place | {"column_name": "", "data_type": "", "description": words})
            rows += [place | {"column_name": f.name, "data_type": str(f.type).upper(), "description": ""}
                     for f in found.schema]
        return rows

    def frame(self, path, sheet=None, header_row=None):
        """A document as a table (Arrow): a CSV, Parquet or JSON-lines file, or a workbook's sheet or named
        table (its first sheet when none is named)."""
        drive, item = self.find(path)
        data = self.download({"library": drive["name"], **item})
        kind = TABULAR.get(item["extension"])
        header = self.header_row if header_row is None else max(1, int(header_row))
        return arrow_from(data, kind, sheet, header, item["name"])

    def text(self, path):
        """A document's text: a Word document's paragraphs, a PDF's pages (pypdf), a text file as it is."""
        drive, item = self.find(path)
        data = self.download({"library": drive["name"], **item})
        if item["extension"] == "docx":
            with zipfile.ZipFile(io.BytesIO(data)) as book:
                xml = book.read("word/document.xml").decode("utf-8", "replace")
            paragraphs = re.findall(r"<w:p\b.*?</w:p>", xml, re.S)
            return "\n".join(html_text("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))) for p in paragraphs)
        if item["extension"] == "pdf":
            pypdf = importlib.import_module("pypdf")
            return "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages)
        return data.decode("utf-8", "replace")

    def upload(self, path, data):
        """Bytes, a DataFrame (as CSV, or Excel for a .xlsx path) or a file on this computer uploaded to
        library/folders/name (replacing a document of that name)."""
        parts = [p for p in str(path).replace("\\", "/").split("/") if p]
        if len(parts) < 2:
            raise SharePointError(f"Name where it goes as library/folders/name, not {path!r}.")
        drive = self.library(parts[0])
        if hasattr(data, "to_csv") or hasattr(data, "to_pandas"):
            frame = data.to_pandas() if hasattr(data, "to_pandas") else data
            sink = io.BytesIO()
            if parts[-1].lower().endswith((".xlsx", ".xlsm")):
                frame.to_excel(sink, index=False)
            else:
                frame.to_csv(sink, index=False)
            data = sink.getvalue()
        elif isinstance(data, str) and os.path.isfile(data):
            with open(data, "rb") as file:
                data = file.read()
        within = urllib.parse.quote("/".join(parts[1:]))
        answer = self.graph.upload(f"drives/{drive['id']}/root:/{within}:/content", data, f"Uploading {parts[-1]}")
        self._index.pop(drive["id"], None)
        self.found = None
        return {"name": answer.get("name"), "size": answer.get("size"), "web_url": answer.get("webUrl")}

    def rows(self, table, schema="", limit=None, columns=None, filters=None, frame=False):
        t = self.table(table, schema)
        if t["kind"] == "index":
            rows, own = self.index(t["drive"])
            names = [n for n, _ in DOC_FIELDS] + [c["name"] for c in own]
            return self.finish(rows, names, None, limit, columns, filters, frame, "graph")
        data = self.download({"library": t["drive"]["name"], **t["file"]})
        kind = "excel" if t["kind"] in ("sheet", "named") else t["kind"]
        found = arrow_from(data, kind, t.get("sheet"), self.header_row, t["file"]["name"], t.get("ref"))
        return self.finish_arrow(found, limit, columns, filters, frame, "excel" if kind == "excel" else kind)


def arrow_from(data, kind, sheet=None, header=1, name="the document", ref=None):
    """A tabular document's bytes as an Arrow table: CSV, Parquet, JSON lines, a workbook's sheet (or a
    named table's range)."""
    import pyarrow as pa

    if kind == "parquet":
        import pyarrow.parquet as pq

        return pq.read_table(io.BytesIO(data))
    if kind == "csv":
        import pyarrow.csv as pacsv

        return pacsv.read_csv(io.BytesIO(data), pacsv.ReadOptions(skip_rows=header - 1))
    if kind == "json":
        import pyarrow.json as pajson

        return pajson.read_json(io.BytesIO(data))
    if kind == "excel":
        openpyxl = importlib.import_module("openpyxl")
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=not ref, data_only=True)
        if ref:
            ws = next(ws for ws in book.worksheets if sheet in getattr(ws, "tables", {}))
            cells = [[c.value for c in row] for row in ws[ws.tables[sheet].ref]]
            header = 1
        else:
            ws = book[sheet] if sheet else book.worksheets[0]
            cells = [list(r) for r in ws.iter_rows(values_only=True)]
        cells = cells[header - 1:]
        if not cells:
            raise SharePointError(f"{name}'s {sheet or 'first sheet'} is empty.")
        heads = [str(h) if h is not None else f"column_{i + 1}" for i, h in enumerate(cells[0])]
        body = [r for r in cells[1:] if any(v is not None for v in r)]
        columns = {}
        for i, h in enumerate(heads):
            values = [r[i] if i < len(r) else None for r in body]
            try:
                columns[h] = pa.array(values)
            except (pa.ArrowInvalid, pa.ArrowTypeError):
                columns[h] = pa.array([None if v is None else str(v) for v in values], pa.string())
        return pa.table(columns)
    raise SharePointError(f"{name} is not a table (only CSV, Parquet, JSON lines and workbooks are).")


def frame_of(rows, names):
    try:
        import pandas as pd
    except ImportError:
        return rows
    return pd.DataFrame.from_records(rows, columns=list(names))
'''
)

_HEAD = entra.IMPORTS + "\nimport duckdb\n"
# What the Graph client borrows from the lake code: the error, Arrow, quoting, filters in DuckDB.
_SHARED = entra.COMMON + code.STORES + code.DELTA + code.WRITER + code.READER


def _code(place: str, sign_in: str, made: str) -> str:
    return _HEAD + place + sign_in + _SHARED + GRAPH + "\n\n" + made


_WAYS: tuple[tuple[str, str, str], ...] = (
    *entra.ROPC_SIGN_INS,
    *entra.SIGN_INS,
)
_LISTS_MADE = 'conn = SharePointLists(site_url, Token(sign_in, "https://graph.microsoft.com/.default"))\n'
_DOCS_MADE = 'conn = SharePointDocuments(site_url, Token(sign_in, "https://graph.microsoft.com/.default"), header_row)\n'

LISTS_SIGN_INS: tuple[tuple[str, str, str], ...] = tuple(
    (label, mark, _code(_PLACE, way, _LISTS_MADE)) for label, mark, way in _WAYS
)
DOCS_SIGN_INS: tuple[tuple[str, str, str], ...] = tuple(
    (label, mark, _code(_DOCS_PLACE, way, _DOCS_MADE)) for label, mark, way in _WAYS
)
LISTS: str = LISTS_SIGN_INS[0][2]
DOCS: str = DOCS_SIGN_INS[0][2]
