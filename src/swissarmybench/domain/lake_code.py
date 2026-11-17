# ruff: noqa: E501 (the connections' code is text, written as it runs; its lines are its own)
"""The lake connections' shared code, as text: where the files are (a folder on this computer, Azure Data
Lake Storage Gen2 or OneLake through the ADLS Gen2 API, Amazon S3), a Delta table's log, and the one way
every lake kind reads a table into DuckDB (domain/lakes.py assembles each kind's code from these).

One Delta implementation for the three lake kinds (the owner, 2026-11-17: "The OneLake and Data Lake kinds
use this same Delta reading code for their Delta tables, so there's one implementation"):

- a Delta table is read with DuckDB's own `delta_scan` where it works (a folder here; abfss:// with the
  azure extension, the token as a secret made in this Python's DuckDB and never written down; s3:// with
  httpfs), else with the deltalake package when it is installed, else by its log read here: the active
  files (the last checkpoint, then each commit since) read with DuckDB's `read_parquet` over HTTPS, the
  token as a header of a DuckDB secret scoped to the storage's address. Each read says which it used.
- Parquet and CSV files, and hive-partitioned folders, are read with DuckDB's `read_parquet` and
  `read_csv` (the same HTTPS way for Azure and OneLake): the columns asked for and the filters are
  DuckDB's own pushdown (row groups skipped by their statistics, a partition's files by its folder).
- the log gives each Delta table's latest version, size and partition columns (the tree shows them), and
  time travel: `orders@v12` (a version) or `orders@2026-11-01` (the table as it was then).

Listing goes through the ADLS Gen2 API (`?resource=filesystem&recursive=...`), paged; reading a log file
through the same API. An account key is never sent: it signs a short-lived read-only SAS here, and the
SAS is hidden from every message (`sig=****`).

One environment variable moves the storage elsewhere (in the tests, to a stand-in on this computer):
SWISSARMYBENCH_STORAGE_URL (path style: <it>/<account>/<filesystem>/<path>).

This file is text. Pure: no I/O.
"""

from __future__ import annotations

STORAGE_VARIABLE: str = "SWISSARMYBENCH_STORAGE_URL"
MAX_DEPTH: int = 6  # folders below the place looked into for tables
MAX_TABLES: int = 500  # tables one connection lists
MAX_ENTRIES: int = 200_000  # files and folders one listing reads
DESCRIBED: int = (
    MAX_TABLES  # tables whose columns the catalog reads (each one listed: a table needs a column)
)

# How a read was made (in each read's answer, from the Arrow table's metadata `sab_read`).
READ_WITH: dict[str, str] = {
    "delta_scan": "DuckDB's delta_scan",
    "deltalake": "the deltalake package",
    "log": "its Delta log, read here, and DuckDB's read_parquet",
    "parquet": "DuckDB's read_parquet",
    "csv": "DuckDB's read_csv",
    "json": "DuckDB's read_json",
    "sql": "T-SQL on its SQL endpoint",
    "graph": "Microsoft Graph",
    "excel": "the workbook's sheet",
}

STORES: str = (
    "\n# The most: the depth looked into below the place, the tables listed, the files one listing reads,\n"  # noqa: S608 (words)
    "# the tables whose columns the catalog reads.\n"
    + f"MAX_DEPTH, MAX_TABLES, MAX_ENTRIES, DESCRIBED = {MAX_DEPTH}, {MAX_TABLES}, {MAX_ENTRIES}, {DESCRIBED}\n"
    + r'''

class LakeError(RuntimeError):
    """A lake's table cannot be listed or read as asked; the message says why and what there is."""


_SAS = re.compile(r"(sig|se|sv|sp|skoid|sktid|skt|ske|sks|skv)=[^&\s'\"]+")


def hidden(text):
    """A message with every signature and token taken out (a SAS's sig=, a bearer token)."""
    text = _SAS.sub(lambda m: m.group(1) + "=****", str(text))
    return re.sub(r"(Bearer\s+|ACCESS_TOKEN\s+')[A-Za-z0-9._\-]+", r"\1****", text)


def arrow_of(result):
    """A DuckDB result as an Arrow table (DuckDB 2's to_arrow_table, 1's fetch_arrow_table)."""
    for name in ("to_arrow_table", "fetch_arrow_table", "arrow"):
        method = getattr(result, name, None)
        if callable(method):
            found = method()
            return found.read_all() if hasattr(found, "read_all") else found
    raise LakeError("This DuckDB cannot give its result as Arrow.")


def quoted(text):
    return "'" + str(text).replace("'", "''") + "'"


def ident(name):
    return '"' + str(name).replace('"', '""') + '"'


class LocalStore:
    """A folder on this computer."""

    kind = "local"

    def __init__(self, root):
        self.root = os.path.abspath(os.path.expanduser(str(root)))
        if not os.path.isdir(self.root):
            raise LakeError(f"There is no folder {self.root!r} on this computer.")

    def where(self):
        return self.root

    def walk(self, path="", depth=8):
        """Every file and folder under `path`, as {"path" (below the root, with /), "dir", "size",
        "modified", "etag"}."""
        start = os.path.join(self.root, *[p for p in path.split("/") if p])
        found, todo = [], [(start, 0)]
        while todo:
            folder, level = todo.pop()
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for e in entries:
                rel = os.path.relpath(e.path, self.root).replace(os.sep, "/")
                info = e.stat()
                found.append({"path": rel, "dir": e.is_dir(), "size": 0 if e.is_dir() else info.st_size,
                              "modified": info.st_mtime, "etag": str(info.st_mtime_ns)})
                if e.is_dir() and level < depth:
                    todo.append((e.path, level + 1))
                if len(found) > MAX_ENTRIES:
                    raise LakeError(f"{self.root} holds more than {MAX_ENTRIES:,} files: name a folder within it.")
        return found

    def get(self, path):
        with open(os.path.join(self.root, *path.split("/")), "rb") as file:
            return file.read()

    def url(self, path):
        return os.path.join(self.root, *[p for p in path.split("/") if p])

    def prepare(self, duck, delta=False):
        return None


class AzureStore:
    """A container (filesystem) of Azure Data Lake Storage Gen2, or a OneLake workspace, through the ADLS
    Gen2 API. Signed in with a token (`token()`), a SAS, or an account key (which signs a read-only SAS
    here, valid for an hour)."""

    kind = "azure"
    VERSION = "2023-11-03"

    def __init__(self, account, filesystem, base="", token=None, sas="", key="", domain="dfs.core.windows.net"):
        self.account, self.filesystem = str(account).strip(), str(filesystem).strip()
        self.base = "/".join(p for p in str(base).replace("\\", "/").split("/") if p)
        self.token, self.key, self.host = token, key, domain
        self.sas = str(sas or "").lstrip("?")
        if not self.account or not self.filesystem:
            raise LakeError("Name the storage account and the container (a OneLake workspace).")
        moved = os.environ.get("SWISSARMYBENCH_STORAGE_URL")
        self.endpoint = f"{moved.rstrip('/')}/{self.account}" if moved else f"https://{self.account}.{host}"
        self.moved = bool(moved)
        if self.key and not self.sas:
            self.sas = account_sas(self.account, self.key)

    def where(self):
        return f"abfss://{self.filesystem}@{self.account}.{self.host}/{self.base}".rstrip("/")

    def _full(self, path):
        return "/".join(p for p in (self.base, path) if p)

    def _address(self, path, query=""):
        address = f"{self.endpoint}/{urllib.parse.quote(self.filesystem)}"
        if path:
            address += "/" + urllib.parse.quote(path)
        extra = "&".join(q for q in (query, self.sas) if q)
        return address + (f"?{extra}" if extra else "")

    def headers(self):
        found = {"x-ms-version": self.VERSION}
        if self.token is not None and not self.sas:
            found["Authorization"] = f"Bearer {self.token()}"
        return found

    def _ask(self, address, what):
        try:
            return ask(address, None, self.headers(), what, raw=True)
        except AzureError as error:
            raise LakeError(hidden(error)) from None

    def walk(self, path="", depth=8):
        """Every file and folder under `path` (the ADLS Gen2 API's recursive listing, paged)."""
        directory = self._full(path)
        found, token = [], ""
        while True:
            query = "resource=filesystem&recursive=true&maxResults=5000"
            if directory:
                query += "&directory=" + urllib.parse.quote(directory, safe="")
            if token:
                query += "&continuation=" + urllib.parse.quote(token, safe="")
            body, headers = self._ask(self._address("", query), f"Listing {self.where()}")
            for p in json.loads(body or b"{}").get("paths") or []:
                name = str(p.get("name") or "")
                rel = name[len(self.base) + 1 :] if self.base and name.startswith(self.base + "/") else name
                if not rel or rel.count("/") > depth + path.count("/") + 1:
                    continue
                found.append({
                    "path": rel,
                    "dir": str(p.get("isDirectory", "false")).lower() == "true",
                    "size": int(p.get("contentLength") or 0),
                    "modified": modified_of(p.get("lastModified")),
                    "etag": str(p.get("etag") or ""),
                })
            token = {k.lower(): v for k, v in headers.items()}.get("x-ms-continuation", "")
            if not token:
                return found
            if len(found) > MAX_ENTRIES:
                raise LakeError(f"{self.where()} holds more than {MAX_ENTRIES:,} files: name a folder within it.")

    def get(self, path):
        body, _ = self._ask(self._address(self._full(path)), f"Reading {path}")
        return body

    def url(self, path):
        """The file's address for DuckDB: abfss:// for the azure extension, else HTTPS with the token as
        a header (or the SAS in its query)."""
        if self.https():
            return self._address(self._full(path))
        return f"abfss://{self.filesystem}@{self.account}.{self.host}/{self._full(path)}"

    def https(self):
        """Read over HTTPS with DuckDB's httpfs (the token as a header): a moved endpoint, a SAS, or
        when the azure extension is not here."""
        return self.moved or bool(self.sas) or not getattr(self, "azure_extension", True)

    def prepare(self, duck, delta=False):
        """A DuckDB secret for these files, made in this DuckDB only (never written down): the azure
        extension's, with the token; or httpfs's, with the token as a header scoped to this address."""
        if not self.https():
            try:
                duck.execute("LOAD azure")
                token = self.token() if self.token is not None else ""
                duck.execute(
                    f"CREATE OR REPLACE SECRET sab_lake (TYPE azure, PROVIDER access_token, "
                    f"ACCESS_TOKEN {quoted(token)}, ACCOUNT_NAME {quoted(self.account)})"
                )
                return None
            except Exception:  # the extension cannot load here: read over HTTPS instead
                self.azure_extension = False
        duck.execute("LOAD httpfs")
        if self.token is not None and not self.sas:
            headers = ", ".join(f"{quoted(k)}: {quoted(v)}" for k, v in self.headers().items())
            duck.execute(
                f"CREATE OR REPLACE SECRET sab_lake_http (TYPE http, EXTRA_HTTP_HEADERS MAP {{{headers}}}, "
                f"SCOPE {quoted(self.endpoint)})"
            )
        return None


def modified_of(text):
    """An HTTP date (Mon, 16 Nov 2026 10:00:00 GMT) as seconds."""
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(str(text)).timestamp()
    except (TypeError, ValueError, IndexError):
        return 0.0


def account_sas(account, key, hours=1):
    """A read-and-list account SAS for the blob and dfs services, signed with the account key here: the
    key itself never leaves this Python."""
    expiry = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=hours))
    fields = {"sv": "2021-06-08", "ss": "b", "srt": "sco", "sp": "rl",
              "se": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"), "spr": "https,http"}
    signed = "\n".join([account, fields["sp"], fields["ss"], fields["srt"], "", fields["se"], "",
                        fields["spr"], fields["sv"], "", ""])
    digest = hmac.new(base64.b64decode(key), signed.encode("utf-8"), hashlib.sha256).digest()
    fields["sig"] = base64.b64encode(digest).decode()
    return urllib.parse.urlencode(fields)


class S3Store:
    """A bucket and prefix of Amazon S3, through DuckDB's httpfs (its glob lists, read_blob reads)."""

    kind = "s3"

    def __init__(self, root, key_id="", secret_key="", region="", profile=""):
        parts = urllib.parse.urlsplit(str(root))
        self.bucket, self.base = parts.netloc, parts.path.strip("/")
        self.key_id, self.secret_key, self.region, self.profile = key_id, secret_key, region, profile
        if not self.bucket:
            raise LakeError(f"An S3 root is s3://<bucket>/<path>, not {root!r}.")
        self._duck = None

    def where(self):
        return f"s3://{self.bucket}/{self.base}".rstrip("/")

    def duck(self):
        if self._duck is None:
            self._duck = duckdb.connect()
            self.prepare(self._duck)
        return self._duck

    def walk(self, path="", depth=8):
        base = "/".join(p for p in (self.base, path) if p)
        rows = self.duck().execute(
            "SELECT file FROM glob(?)", [f"s3://{self.bucket}/{base}/**".replace("//**", "/**")]
        ).fetchall()
        found, folders = [], set()
        for (file,) in rows:
            rel = str(file).split(f"s3://{self.bucket}/", 1)[-1]
            rel = rel[len(self.base) + 1 :] if self.base else rel
            parts = rel.split("/")
            for i in range(1, len(parts)):
                folders.add("/".join(parts[:i]))
            found.append({"path": rel, "dir": False, "size": 0, "modified": 0.0, "etag": ""})
        found += [{"path": f, "dir": True, "size": 0, "modified": 0.0, "etag": ""} for f in sorted(folders)]
        return found

    def get(self, path):
        rows = self.duck().execute("SELECT content FROM read_blob(?)", [self.url(path)]).fetchall()
        return bytes(rows[0][0]) if rows else b""

    def url(self, path):
        return "/".join(p for p in (f"s3://{self.bucket}", self.base, path) if p)

    def prepare(self, duck, delta=False):
        duck.execute("LOAD httpfs")
        if self.key_id:
            region = f", REGION {quoted(self.region)}" if self.region else ""
            duck.execute(
                f"CREATE OR REPLACE SECRET sab_s3 (TYPE s3, KEY_ID {quoted(self.key_id)}, "
                f"SECRET {quoted(self.secret_key)}{region})"
            )
        elif self.profile:
            duck.execute("LOAD aws")
            duck.execute(
                f"CREATE OR REPLACE SECRET sab_s3 (TYPE s3, PROVIDER credential_chain, "
                f"PROFILE {quoted(self.profile)})"
            )
        return None


def store_of(root, token=None, key_id="", secret_key="", region="", profile="", sas="", key=""):
    """Where a root is: a folder here, abfss://container@account.dfs.core.windows.net/path (Data Lake or
    OneLake), or s3://bucket/path."""
    text = str(root).strip()
    if text.lower().startswith(("abfss://", "abfs://")):
        parts = urllib.parse.urlsplit(text)
        filesystem, _, host = parts.netloc.partition("@")
        account, _, rest = host.partition(".")
        return AzureStore(account, filesystem, parts.path, token, sas, key, rest or "dfs.core.windows.net")
    if text.lower().startswith("s3://"):
        return S3Store(text, key_id, secret_key, region, profile)
    return LocalStore(text)
'''
)

DELTA: str = r'''

class DeltaLog:
    """A Delta table's log (_delta_log): its versions, its active files at a version, its schema and
    partition columns. Read here, with the standard library (and pyarrow for a checkpoint)."""

    UNREAD_FEATURES = {"deletionVectors", "columnMapping", "v2Checkpoint", "typeWidening", "variantType"}

    def __init__(self, store, path, entries=None):
        self.store, self.path = store, path.strip("/")
        log = f"{self.path}/_delta_log" if self.path else "_delta_log"
        listed = entries if entries is not None else store.walk(log, depth=0)
        self.commits, self.checkpoints = {}, {}
        for e in listed:
            name = e["path"].rsplit("/", 1)[-1]
            found = re.fullmatch(r"(\d{20})\.json", name)
            if found:
                self.commits[int(found.group(1))] = e
            found = re.fullmatch(r"(\d{20})\.checkpoint\.parquet", name)
            if found:
                self.checkpoints[int(found.group(1))] = e
        self.log = log
        if not self.commits and not self.checkpoints:
            raise LakeError(f"{path} has no Delta log.")
        self.latest = max([*self.commits, *self.checkpoints])
        self._read = {}

    def _lines(self, version):
        if version not in self._read:
            text = self.store.get(f"{self.log}/{version:020d}.json").decode("utf-8")
            self._read[version] = [json.loads(line) for line in text.splitlines() if line.strip()]
        return self._read[version]

    def version_at(self, when):
        """The last version committed at or before `when` (a date or a time, as text)."""
        try:
            moment = datetime.datetime.fromisoformat(str(when).replace("Z", "+00:00"))
        except ValueError:
            raise LakeError(f"{when!r} is not a date or time (2026-11-01, 2026-11-01T09:30).") from None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=datetime.timezone.utc)
        if len(str(when)) == 10:  # a day: the table as it was at that day's end
            moment += datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)
        limit = moment.timestamp() * 1000
        found = None
        for version in sorted(self.commits):
            stamp = next((a["commitInfo"].get("timestamp") for a in self._lines(version) if "commitInfo" in a),
                         None) or self.commits[version]["modified"] * 1000
            if stamp <= limit:
                found = version
        if found is None:
            raise LakeError(f"The table had no version yet on {when} (its first: {min(self.commits)}).")
        return found

    def snapshot(self, version=None):
        """The table at a version (None: the latest): {"version", "files": [{"path", "values", "size"}],
        "columns": [(name, type)], "partitions", "size", "features", "configuration"}."""
        target = self.latest if version is None else int(version)
        if target > self.latest or target < 0:
            raise LakeError(f"The table has versions 0 to {self.latest}, not {target}.")
        start = max((v for v in self.checkpoints if v <= target), default=-1)
        files, meta, protocol = {}, None, {}
        if start >= 0:
            for action in self._checkpoint(start):
                if action.get("add"):
                    files[action["add"]["path"]] = action["add"]
                if action.get("metaData"):
                    meta = action["metaData"]
                if action.get("protocol"):
                    protocol = action["protocol"]
        for v in range(start + 1, target + 1):
            if v not in self.commits:
                raise LakeError(f"The table's log is missing version {v}: it cannot be read here.")
            for action in self._lines(v):
                if "add" in action:
                    files[action["add"]["path"]] = action["add"]
                elif "remove" in action:
                    files.pop(action["remove"]["path"], None)
                elif "metaData" in action:
                    meta = action["metaData"]
                elif "protocol" in action:
                    protocol = action["protocol"]
        if meta is None:
            raise LakeError("The table's log has no schema (metaData).")
        schema = json.loads(meta.get("schemaString") or "{}")
        columns = [(f["name"], type_of(f["type"])) for f in schema.get("fields", [])]
        features = set(protocol.get("readerFeatures") or [])
        mode = (meta.get("configuration") or {}).get("delta.columnMapping.mode", "none")
        if mode != "none":
            features.add("columnMapping")
        found = [
            {"path": urllib.parse.unquote(p), "values": a.get("partitionValues") or {}, "size": int(a.get("size") or 0),
             "deletion": bool(a.get("deletionVector"))}
            for p, a in files.items()
        ]
        if any(f["deletion"] for f in found):
            features.add("deletionVectors")
        return {
            "version": target,
            "files": found,
            "columns": columns,
            "partitions": list(meta.get("partitionColumns") or []),
            "size": sum(f["size"] for f in found),
            "features": sorted(features),
        }

    def _checkpoint(self, version):
        try:
            import pyarrow.parquet as pq
        except ImportError:
            raise LakeError("Reading a Delta checkpoint needs pyarrow (pip install pyarrow).") from None
        table = pq.read_table(io.BytesIO(self.store.get(f"{self.log}/{version:020d}.checkpoint.parquet")))
        return table.to_pylist()

    def history(self, limit=50):
        """The versions, newest first: {"version", "timestamp", "operation"}."""
        out = []
        for v in sorted(self.commits, reverse=True)[:limit]:
            info = next((a["commitInfo"] for a in self._lines(v) if "commitInfo" in a), {})
            stamp = info.get("timestamp") or self.commits[v]["modified"] * 1000
            when = datetime.datetime.fromtimestamp(stamp / 1000, datetime.timezone.utc)
            out.append({"version": v, "timestamp": when.isoformat(timespec="seconds"),
                        "operation": info.get("operation", "")})
        return out


DELTA_TYPES = {"string": "VARCHAR", "long": "BIGINT", "integer": "INTEGER", "short": "SMALLINT",
               "byte": "TINYINT", "float": "FLOAT", "double": "DOUBLE", "boolean": "BOOLEAN",
               "binary": "BLOB", "date": "DATE", "timestamp": "TIMESTAMP WITH TIME ZONE",
               "timestamp_ntz": "TIMESTAMP"}


def type_of(kind):
    """A Delta schema type in DuckDB's words (a struct, list or map as its own name)."""
    if isinstance(kind, dict):
        return str(kind.get("type", "struct")).upper()
    text = str(kind)
    if text.startswith("decimal"):
        return text.upper()
    return DELTA_TYPES.get(text, text.upper())
'''

WRITER: str = r'''

def arrow_table(rows):
    """Rows to write as an Arrow table: a DataFrame (pandas, polars), an Arrow table, a DuckDB relation,
    a list of dicts."""
    import pyarrow as pa

    if isinstance(rows, pa.Table):
        return rows
    for name in ("to_arrow_table", "fetch_arrow_table", "to_arrow", "arrow"):
        method = getattr(rows, name, None)
        if callable(method) and not hasattr(rows, "to_pandas"):
            found = method()
            return found.read_all() if hasattr(found, "read_all") else found
    if hasattr(rows, "to_arrow"):  # polars
        return rows.to_arrow()
    if hasattr(rows, "columns") and hasattr(rows, "dtypes"):  # pandas
        return pa.Table.from_pandas(rows, preserve_index=False)
    if isinstance(rows, list):
        return pa.Table.from_pylist(rows)
    raise LakeError(f"Write a DataFrame, an Arrow table or a DuckDB relation, not a {type(rows).__name__}.")


_SHORTEST_VACUUM_HOURS = 168  # seven days: what Delta keeps for readers and time travel


class LakeWrites:
    """What a lake writes (the Write starters call these, after their dry run): a DataFrame as a Delta
    table (append, overwrite, merge by keys) with the deltalake package, a delete by a condition, a
    compaction and a vacuum (each with a dry run of its own), and a Parquet or CSV file put in its place.
    The counts a dry run says are read here, without writing (DuckDB on the table as it is)."""

    def delta_url(self, path):
        """A Delta table's address for the deltalake package (abfss://, s3://, a folder)."""
        store = self.store
        if isinstance(store, AzureStore):
            full = "/".join(p for p in (store.base, path) if p)
            return f"abfss://{store.filesystem}@{store.account}.{store.host}/{full}"
        return store.url(path)

    def deltalake(self):
        return importlib.import_module("deltalake")  # missing: the missing-package prompt names it

    def delta_table(self, path):
        return self.deltalake().DeltaTable(self.delta_url(path), storage_options=self.options() or None)

    def _changed(self, path):
        self.found, self._views = None, False
        self._logs.pop(path, None)

    def target_path(self, table, schema=""):
        """A write's place: an existing table's path, or a new one's (folders/name below the place)."""
        try:
            return self.table(table, schema)["path"]
        except LakeError:
            return "/".join(p for p in f"{schema}/{table}".replace("\\", "/").split("/") if p)

    def write_delta(self, path, rows, mode="append", keys=(), partition_by=None):
        """Rows written to the Delta table at `path`: appended, overwriting it, or merged by `keys` (a row
        whose keys match is updated, any other inserted). One commit. Its counts."""
        data = arrow_table(rows)
        dl = self.deltalake()
        options = self.options() or None
        if mode in ("append", "overwrite"):
            dl.write_deltalake(self.delta_url(path), data, mode=mode, partition_by=partition_by or None,
                               storage_options=options)
            self._changed(path)
            return {"written": data.num_rows}
        if mode != "merge" or not keys:
            raise LakeError("A Delta write appends, overwrites, or merges by its key columns (keys=[...]).")
        predicate = " AND ".join(f"t.{ident(k)} = s.{ident(k)}" for k in keys)
        merged = (self.delta_table(path).merge(data, predicate, source_alias="s", target_alias="t")
                  .when_matched_update_all().when_not_matched_insert_all().execute())
        self._changed(path)
        return {"inserted": int(merged.get("num_target_rows_inserted", 0)),
                "updated": int(merged.get("num_target_rows_updated", 0))}

    def delete_delta(self, path, condition):
        """The rows matching `condition` (a SQL condition: region = 'West') deleted, in one commit."""
        if not str(condition).strip():
            raise LakeError("A delete names its rows: a condition such as region = 'West'.")
        found = self.delta_table(path).delete(str(condition))
        self._changed(path)
        return {"deleted": int(found.get("num_deleted_rows", 0))}

    def count_where(self, table, condition, schema=""):
        """How many rows a condition matches now (a delete's dry run), by DuckDB on the table as it is."""
        t = self.table(table, schema)
        found, _ = self.source(t)
        clause = f" WHERE {condition}" if str(condition).strip() else ""
        return int(self.duck().execute(f"SELECT count(*) FROM {found}{clause}").fetchall()[0][0])

    def count_matches(self, table, rows, keys, schema=""):
        """How many of the rows' keys the table already has (a merge's updates), and the table's rows."""
        t = self.table(table, schema)
        found, _ = self.source(t)
        duck = self.duck()
        duck.register("sab_incoming", arrow_table(rows))
        try:
            on = " AND ".join(f"t.{ident(k)} IS NOT DISTINCT FROM s.{ident(k)}" for k in keys)
            matched = duck.execute(
                f"SELECT count(*) FROM sab_incoming s WHERE EXISTS (SELECT 1 FROM {found} t WHERE {on})"
            ).fetchall()[0][0]
            total = duck.execute(f"SELECT count(*) FROM {found}").fetchall()[0][0]
        finally:
            duck.unregister("sab_incoming")
        return int(matched), int(total)

    def optimize_delta(self, path, dry_run=True, target_size=128 * 1024 * 1024):
        """Small files compacted into larger ones (one commit). The dry run: how many files there are and
        how many are smaller than the target size."""
        snapshot = DeltaLog(self.store, path).snapshot()
        small = [f for f in snapshot["files"] if f["size"] < target_size]
        if dry_run:
            return {"files": len(snapshot["files"]), "small": len(small), "version": snapshot["version"]}
        done = self.delta_table(path).optimize.compact(target_size=target_size)
        self._changed(path)
        return {"added": int(done.get("numFilesAdded", 0)), "removed": int(done.get("numFilesRemoved", 0))}

    def vacuum_delta(self, path, retention_hours=_SHORTEST_VACUUM_HOURS, dry_run=True, allow_shorter=False):
        """Files no version within the retention period reads, deleted (a dry run lists them). Less than
        seven days is refused unless `allow_shorter` (it breaks time travel and readers still reading)."""
        hours = int(retention_hours)
        if hours < _SHORTEST_VACUUM_HOURS and not allow_shorter:
            raise LakeError(
                f"A vacuum keeps at least {_SHORTEST_VACUUM_HOURS} hours (7 days) of files: {hours} hours would "
                "break time travel and readers still reading. Set allow_shorter=True in the cell to do it anyway.")
        files = self.delta_table(path).vacuum(retention_hours=hours, dry_run=bool(dry_run),
                                              enforce_retention_duration=not allow_shorter)
        if not dry_run:
            self._changed(path)
        return {"files": len(files), "retention_hours": hours, "dry_run": bool(dry_run), "listed": list(files)[:20]}

    def put_file(self, path, data):
        """Bytes put at `path` below the place, in one step: a folder here writes a new file and then puts
        it in its place; Azure creates, appends and flushes (the ADLS Gen2 API)."""
        store = self.store
        if isinstance(store, LocalStore):
            target = store.url(path)
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            partial = target + ".sab-writing"
            with open(partial, "wb") as file:
                file.write(data)
            os.replace(partial, target)
        elif isinstance(store, AzureStore):
            full = store._full(path)
            headers = store.headers()
            try:
                ask(store._address(full, "resource=file"), b"", headers, f"Creating {path}", method="PUT")
                if data:
                    ask(store._address(full, "action=append&position=0"), data,
                        headers | {"Content-Type": "application/octet-stream"}, f"Writing {path}", method="PATCH")
                ask(store._address(full, f"action=flush&position={len(data)}"), b"", headers,
                    f"Finishing {path}", method="PATCH")
            except AzureError as error:
                raise LakeError(hidden(error)) from None
        else:
            raise LakeError("Files are written to a folder here, Azure Data Lake Storage or OneLake; for S3, "
                            "write a Delta table.")
        self.found, self._views = None, False
        return {"written": len(data), "path": path}

    def write_file(self, path, rows, file_format="parquet"):
        """Rows written as one Parquet or CSV file at `path` (replacing a file of that name)."""
        data = arrow_table(rows)
        sink = io.BytesIO()
        if file_format == "parquet":
            import pyarrow.parquet as pq

            pq.write_table(data, sink, compression="zstd")
        elif file_format == "csv":
            import pyarrow.csv as pacsv

            pacsv.write_csv(data, sink)
        else:
            raise LakeError(f"A file is written as parquet or csv, not {file_format!r}.")
        done = self.put_file(path, sink.getvalue())
        return done | {"rows": data.num_rows}
'''

READER: str = r'''

FILE_KINDS = {".parquet": "parquet", ".csv": "csv", ".tsv": "csv", ".txt": "csv", ".jsonl": "json",
              ".ndjson": "json", ".json": "json"}


def file_kind(name):
    lowered = name.lower()
    for suffix, kind in FILE_KINDS.items():
        if lowered.endswith(suffix) or lowered.endswith(suffix + ".gz"):
            return kind
    return None


def split_table(table):
    """A table's name and when (`orders@v12`: version 12; `orders@2026-11-01`: as it was then)."""
    name, at, when = str(table).rpartition("@") if "@" in str(table) else (str(table), "", "")
    if not at:
        return str(table), None, None
    if re.fullmatch(r"[vV]\d+", when):
        return name, int(when[1:]), None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?(Z|[+-]\d{2}:\d{2})?", when):
        return name, None, when
    raise LakeError(f"{table!r}: after @ comes a version (v12) or a date (2026-11-01).")


OPS = {"=", "<>", "<", "<=", ">", ">=", "in", "between", "is null", "is not null"}


def where_of(filters, known):
    """The filters sent with a read (each [column, op, value]) as a DuckDB WHERE and its parameters;
    a column the table does not have is left for DuckDB to say."""
    parts, params = [], []
    by_name = {k.casefold(): k for k in known}
    for column, op, value in filters or []:
        name = by_name.get(str(column).casefold())
        if name is None or op not in OPS:
            continue
        if op == "in":
            parts.append(f"{ident(name)} IN ({', '.join('?' for _ in value)})")
            params += list(value)
        elif op == "between":
            parts.append(f"{ident(name)} BETWEEN ? AND ?")
            params += list(value)
        elif op in ("is null", "is not null"):
            parts.append(f"{ident(name)} {op.upper()}")
        else:
            parts.append(f"{ident(name)} {op} ?")
            params.append(value)
    return " AND ".join(parts), params


class Lake(LakeWrites):
    """Tables in files, read into DuckDB. Each table: {"schema" (its folders, with /), "table" (its
    name), "kind" (delta, parquet, csv, json, hive), "path" (below the place), "files"}.

        conn.tables()                 every table
        conn.read("sales/orders")     a table's rows (a DataFrame; Arrow without pandas)
        conn.read("orders", columns=["id", "amount"], filters=[["region", "=", "North"]], limit=50)
        conn.read("orders@v12")       a Delta table at version 12 (orders@2026-11-01: as it was then)
        conn.history("orders")        a Delta table's versions
        conn.sql("SELECT ...")        DuckDB SQL with every table as a view (sales.orders)
        conn.cursor()                 that DuckDB, for %%sql
    """

    def __init__(self, store, kind_words="lake"):
        self.store, self.words = store, kind_words
        self.found, self._duck, self._logs, self.how = None, None, {}, ""

    # ===== the tables =====

    def entries(self, path="", depth=MAX_DEPTH):
        return self.store.walk(path, depth)

    def tables(self):
        """Every table under the place (found once)."""
        if self.found is None:
            self.found = discover(self.entries(), self.mode)[:MAX_TABLES]
            if not self.found:
                raise LakeError(f"{self.store.where()} holds no tables ({self.none_words()}).")
        return [dict(t) for t in self.found]

    mode = "files"

    def none_words(self):
        return "no Parquet, CSV or JSON files, Delta tables or partitioned folders"

    def table(self, name, schema=""):
        """One table, by its name (orders, orders.parquet), with its folders (sales/orders) or `schema`."""
        base, version, when = split_table(name)
        wanted = [p for p in f"{schema}/{base}".replace("\\", "/").split("/") if p]
        found = self.tables()
        matches = []
        for t in found:
            path = [p for p in t["schema"].split("/") if p] + [t["table"]]
            stem = path[:-1] + [t["table"].rsplit(".", 1)[0] if "." in t["table"] else t["table"]]
            for candidate in (path, stem):
                if [p.casefold() for p in candidate[-len(wanted):]] == [w.casefold() for w in wanted]:
                    matches.append((len(candidate) == len(wanted), t))
                    break
        exact = [t for full, t in matches if full]
        picked = exact if len(exact) == 1 else [t for _, t in matches]
        if len(picked) == 1:
            return picked[0] | {"version": version, "when": when}
        if picked:
            some = ", ".join(f"{t['schema']}/{t['table']}".strip("/") for t in picked[:8])
            raise LakeError(f"{name!r} could be {some}: name its folder too.")
        some = ", ".join(f"{t['schema']}/{t['table']}".strip("/") for t in found[:12])
        raise LakeError(f"{self.store.where()} has no table {name!r}. It has: {some or 'none'}.")

    def delta(self, t):
        key = t["path"]
        if key not in self._logs:
            self._logs[key] = DeltaLog(self.store, t["path"])
        return self._logs[key]

    def duck(self):
        """This connection's own DuckDB (in memory), with the storage's secret."""
        if self._duck is None:
            self._duck = duckdb.connect()
            self.store.prepare(self._duck)
        return self._duck

    # ===== reading =====

    def source(self, t, filters=()):
        """The FROM for a table, as DuckDB reads it, and how (delta_scan, deltalake, log, parquet...)."""
        duck = self.duck()
        if t["kind"] == "delta":
            return self._delta_source(t, filters)
        if t.get("version") is not None or t.get("when"):
            raise LakeError(f"{t['table']} is not a Delta table: it has no versions.")
        reader = {"parquet": "read_parquet", "json": "read_json_auto"}.get(t["format"], "read_csv")
        if t["kind"] == "hive":
            # Each file with its folders' key=value as columns (pruned by an =, IN or IS NULL filter on
            # them first): the same over HTTPS as on this computer.
            files = []
            for f in t["files"]:
                values = dict(p.split("=", 1) for p in f[len(t["path"]) + 1 :].split("/")[:-1] if "=" in p)
                files.append({"path": f, "values": {k: urllib.parse.unquote(v) for k, v in values.items()}})
            kept = prune(files, t["partitions"], filters) or files[:1]
            parts = []
            for f in kept:
                values = ", ".join(f"{quoted(f['values'].get(k)) if f['values'].get(k) is not None else 'NULL'} AS {ident(k)}"
                                   for k in t["partitions"])
                parts.append(f"SELECT *, {values} FROM {reader}({quoted(self.store.url(f['path']))})")
            if not prune(files, t["partitions"], filters):
                parts = [f"SELECT * FROM ({parts[0]}) WHERE false"]
            return "(" + "\nUNION ALL BY NAME\n".join(parts) + ")", t["format"]
        urls = [self.store.url(f) for f in t["files"]]
        listed = "[" + ", ".join(quoted(u) for u in urls) + "]"
        if t["format"] == "json":
            return f"{reader}({listed})", "json"
        return f"{reader}({listed}, union_by_name = true)", t["format"]

    def _delta_source(self, t, filters):
        log = self.delta(t)
        version = t.get("version")
        if t.get("when"):
            version = log.version_at(t["when"])
        snapshot = log.snapshot(version)
        at = f", version = {snapshot['version']}" if version is not None else ""
        url = self.store.url(t["path"])
        refused = []
        # 1. DuckDB's own delta_scan (here, abfss:// with the azure extension, s3://).
        if not (getattr(self.store, "https", lambda: False)()):
            try:
                self.duck().execute("LOAD delta")
                found = f"delta_scan({quoted(url)}{at})"
                self.duck().execute(f"DESCRIBE SELECT * FROM {found}").fetchall()
                return found, "delta_scan"
            except Exception as error:  # the extension, or its reach: the next way
                refused.append(hidden(error).splitlines()[0][:200])
            # 2. the deltalake package.
            try:
                deltalake = importlib.import_module("deltalake")
                table = deltalake.DeltaTable(url, version=snapshot["version"], storage_options=self.options())
                self.dataset = table.to_pyarrow_dataset()
                self.duck().register("sab_deltalake", self.dataset)
                return "sab_deltalake", "deltalake"
            except ImportError:
                pass
            except Exception as error:
                refused.append(hidden(error).splitlines()[0][:200])
        # 3. its log, read here: the active files with read_parquet, a partition's values as columns.
        unread = set(snapshot["features"]) & DeltaLog.UNREAD_FEATURES
        if unread:
            raise ModuleNotFoundError(
                f"{t['table']} uses {', '.join(sorted(unread))}: reading it needs the deltalake package "
                f"(pip install deltalake). {' '.join(refused)}".strip(), name="deltalake")
        files = prune(snapshot["files"], snapshot["partitions"], filters)
        names = [c for c, _ in snapshot["columns"]]
        if not files:
            empty = ", ".join(f"NULL::{kind} AS {ident(c)}" for c, kind in snapshot["columns"])
            return f"(SELECT {empty} WHERE false)", "log"
        kinds = dict(snapshot["columns"])
        parts = []
        for f in files:
            url = self.store.url(f"{t['path']}/{f['path']}")
            values = ", ".join(
                f"{'NULL' if f['values'].get(p) is None else quoted(f['values'][p])}::{kinds.get(p, 'VARCHAR')} AS {ident(p)}"
                for p in snapshot["partitions"]
            )
            stored = [c for c in names if c not in snapshot["partitions"]]
            picked = ", ".join(ident(c) for c in stored)
            parts.append(f"SELECT {picked}{', ' if values and picked else ''}{values} "
                         f"FROM read_parquet({quoted(url)})")
        return "(" + "\nUNION ALL BY NAME\n".join(parts) + ")", "log"

    def options(self):
        """The deltalake package's storage options for this store (its token, a SAS)."""
        if isinstance(self.store, AzureStore):
            found = {"account_name": self.store.account}
            if self.store.sas:
                found["sas_token"] = self.store.sas
            elif self.store.token is not None:
                found["bearer_token"] = self.store.token()
            if self.store.host.endswith("fabric.microsoft.com"):
                found["use_fabric_endpoint"] = "true"
            return found
        if isinstance(self.store, S3Store):
            found = {"aws_region": self.store.region} if self.store.region else {}
            if self.store.key_id:
                found |= {"aws_access_key_id": self.store.key_id, "aws_secret_access_key": self.store.secret_key}
            if self.store.profile:
                found["aws_profile"] = self.store.profile
            return found
        return {}

    def rows(self, table, schema="", limit=None, columns=None, filters=None, frame=False):
        """A table's rows and how many it holds: `columns` (none: every one), `filters` ([column, op,
        value]: =, <>, <, <=, >, >=, in, between, is null, is not null), the first `limit` (None: every
        row). Arrow (with how it was read in its metadata), or with `frame` a DataFrame."""
        t = self.table(table, schema)
        found, how = self.source(t, filters)
        duck = self.duck()
        try:
            known = [r[0] for r in duck.execute(f"DESCRIBE SELECT * FROM {found}").fetchall()]
            where, params = where_of(filters, known)
            by_name = {k.casefold(): k for k in known}
            picked = [by_name[str(c).casefold()] for c in columns or [] if str(c).casefold() in by_name]
            listed = ", ".join(ident(c) for c in picked) if picked else "*"
            clause = f" WHERE {where}" if where else ""
            total = duck.execute(f"SELECT count(*) FROM {found}{clause}", params).fetchall()[0][0]
            tail = f" LIMIT {int(limit)}" if limit is not None else ""
            result = arrow_of(duck.execute(f"SELECT {listed} FROM {found}{clause}{tail}", params))
        except duckdb.Error as error:
            raise LakeError(f"Reading {t['table']} failed: {hidden(error).splitlines()[0][:400]}") from None
        self.how = how
        result = result.replace_schema_metadata({**(result.schema.metadata or {}), b"sab_read": how.encode()})
        if frame:
            try:
                return result.to_pandas(), int(total)
            except ImportError:
                return result, int(total)
        return result, int(total)

    def read(self, table, schema="", columns=None, filters=None, limit=None):
        """A table's rows as a DataFrame (Arrow without pandas)."""
        return self.rows(table, schema, limit, columns, filters, frame=True)[0]

    def history(self, table, schema=""):
        t = self.table(table, schema)
        if t["kind"] != "delta":
            raise LakeError(f"{t['table']} is not a Delta table: it has no versions.")
        return self.delta(t).history()

    def describe(self, t):
        """A table's columns [(name, type)] and its words for the tree (a Delta table's version, size,
        partition columns; a file's size)."""
        if t["kind"] == "delta":
            snap = self.delta(t).snapshot()
            parted = f" · partitioned by {', '.join(snap['partitions'])}" if snap["partitions"] else ""
            return snap["columns"], f"Delta v{snap['version']} · {size_words(snap['size'])}{parted}"
        found, _ = self.source(t)
        columns = [(r[0], r[1]) for r in self.duck().execute(f"DESCRIBE SELECT * FROM {found}").fetchall()]
        size = size_words(t.get("size", 0))
        parted = f" · partitioned by {', '.join(t['partitions'])}" if t.get("partitions") else ""
        count = len(t["files"])
        return columns, f"{t['format'].upper()} · {count} file{'' if count == 1 else 's'} · {size}{parted}"

    def catalog(self):
        """Every table's columns as a catalog (its folders the schema), each table with a row of its
        words (version, size, partitions)."""
        rows = []
        for n, t in enumerate(self.tables()):
            place = {"table_schema": t["schema"], "table_name": t["table"], "table_type": "TABLE"}
            if n >= DESCRIBED:
                rows.append(place | {"column_name": "", "data_type": "", "description": t["kind"]})
                continue
            try:
                columns, words = self.describe(t)
            except (LakeError, duckdb.Error, ModuleNotFoundError) as error:
                # Said beside its folder (a table with no column is not listed).
                note = f"{t['table']}: not read: {hidden(error).splitlines()[0][:160]}"
                rows.append(place | {"table_name": "", "column_name": "", "data_type": "", "description": note})
                continue
            rows.append(place | {"column_name": "", "data_type": "", "description": words})
            rows += [place | {"column_name": c, "data_type": str(k), "description": ""} for c, k in columns]
        return rows

    def cursor(self):
        """This connection's DuckDB, every table a view (sales.orders), for %%sql: DuckDB SQL."""
        duck = self.duck()
        if not getattr(self, "_views", False):
            for t in self.tables():
                schema = t["schema"] or "main"
                duck.execute(f"CREATE SCHEMA IF NOT EXISTS {ident(schema)}")
                name = t["table"].rsplit(".", 1)[0] if t["kind"] in ("parquet", "csv", "json") else t["table"]
                try:
                    found, _ = self.source(t)
                    duck.execute(f"CREATE OR REPLACE VIEW {ident(schema)}.{ident(name)} AS SELECT * FROM {found}")
                except (LakeError, duckdb.Error, ModuleNotFoundError):
                    continue
            self._views = True
        return duck.cursor()

    def sql(self, query, frame=True):
        result = arrow_of(self.cursor().execute(query))
        return result.to_pandas() if frame else result

    def tested(self, rows=20):
        listed = self.tables()
        found = {"found": f"found {len(listed)} table{'' if len(listed) == 1 else 's'} in {self.store.where()}"}
        if listed:
            first = listed[0]
            got, total = self.rows(first["table"], first["schema"], rows)
            found["preview"] = {"table": first["table"], "rows": got.to_pylist(), "total": total}
        return found

    def close(self):
        if self._duck is not None:
            self._duck.close()
            self._duck = None


def size_words(size):
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:,.0f} {unit}" if unit == "bytes" else f"{size:,.1f} {unit}"
        size /= 1024
    return ""


def prune(files, partitions, filters):
    """The files a read needs: those whose partition values can match an =, IN or IS NULL filter."""
    kept = files
    for column, op, value in filters or []:
        part = next((p for p in partitions if p.casefold() == str(column).casefold()), None)
        if part is None or op not in ("=", "in", "is null"):
            continue
        wanted = None if op == "is null" else {str(v) for v in (value if op == "in" else [value])}
        kept = [f for f in kept if (f["values"].get(part) is None if wanted is None
                                    else str(f["values"].get(part)) in wanted)]
    return kept


def discover(entries, mode):
    """The tables among a listing: each folder holding a _delta_log is a Delta table (its folders
    below are its own); in "files" mode also each Parquet, CSV or JSON file, each hive-partitioned folder
    (region=North/...) and each folder of a job's part files (part-0000.parquet, _SUCCESS) as one table."""
    dirs = {e["path"] for e in entries if e["dir"]}
    by_folder = {}
    for e in entries:
        folder = e["path"].rsplit("/", 1)[0] if "/" in e["path"] else ""
        by_folder.setdefault(folder, []).append(e)
    deltas = sorted({d for d in dirs if f"{d}/_delta_log" in dirs}
                    | ({""} if "_delta_log" in dirs else set()))
    tables, taken = [], set()

    def inside(path, roots):
        return any(path == r or path.startswith(r + "/") or r == "" for r in roots)

    for d in deltas:
        schema, _, name = d.rpartition("/")
        tables.append({"schema": schema, "table": name or "table", "kind": "delta", "format": "delta",
                       "path": d, "files": [], "size": 0, "partitions": []})
        taken.add(d)
    if mode == "delta":
        return sorted(tables, key=lambda t: (t["schema"].casefold(), t["table"].casefold()))
    # A hive-partitioned folder: its children are key=value folders, holding data files.
    hives = set()
    for d in sorted(dirs, key=len):
        if inside(d, taken | hives):
            continue
        children = [e for e in by_folder.get(d, []) if e["dir"]]
        if children and all(re.fullmatch(r"[^=/]+=[^/]*", c["path"].rsplit("/", 1)[-1]) for c in children):
            files = [e for e in entries if not e["dir"] and e["path"].startswith(d + "/") and file_kind(e["path"])]
            if files:
                hives.add(d)
                schema, _, name = d.rpartition("/")
                keys = []
                for f in files:
                    for part in f["path"][len(d) + 1 :].split("/")[:-1]:
                        key = part.split("=", 1)[0]
                        if key not in keys:
                            keys.append(key)
                tables.append({"schema": schema, "table": name, "kind": "hive", "format": file_kind(files[0]["path"]),
                               "path": d, "files": [f["path"] for f in files],
                               "size": sum(f["size"] for f in files), "partitions": keys})
    # A folder of a job's part files: one table.
    parts = set()
    for folder, found in by_folder.items():
        if not folder or inside(folder, taken | hives):
            continue
        data = [e for e in found if not e["dir"] and file_kind(e["path"])]
        names = [e["path"].rsplit("/", 1)[-1] for e in found if not e["dir"]]
        if data and ("_SUCCESS" in names or all(n.startswith("part-") for n in (e["path"].rsplit("/", 1)[-1] for e in data))) and len(data) > 1:
            parts.add(folder)
            schema, _, name = folder.rpartition("/")
            tables.append({"schema": schema, "table": name, "kind": "parts", "format": file_kind(data[0]["path"]),
                           "path": folder, "files": [e["path"] for e in data],
                           "size": sum(e["size"] for e in data), "partitions": []})
    for e in entries:
        if e["dir"] or not file_kind(e["path"]) or inside(e["path"], taken | hives | parts):
            continue
        schema, _, name = e["path"].rpartition("/")
        if name.startswith(("_", ".")):
            continue
        tables.append({"schema": schema, "table": name, "kind": file_kind(name), "format": file_kind(name),
                       "path": e["path"], "files": [e["path"]], "size": e["size"], "partitions": []})
    return sorted(tables, key=lambda t: (t["schema"].casefold(), t["table"].casefold()))
'''
