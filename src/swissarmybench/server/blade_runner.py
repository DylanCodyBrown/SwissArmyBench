"""Run a blade for the server: its catalog (Refresh) or a check that it works (Test), always in a child
process of the server's own Python (plan decision 16), never inside the server.

The child (`python -I -m swissarmybench.server.blade_runner`) gets everything on stdin as JSON: the
blade's code and variable, its saved secrets, the vault blades to run first and the values the user
typed for secret blades. It answers on stdout with one JSON object and exits. What the blade prints
goes to stderr, so it cannot break that answer. A time limit stops a blade that hangs.

The answer is names and types (a catalog), a vault's secret names, or a plain error with every secret
value replaced by ****. One answer holds values: `load`, every vault's entries for a Workbench kernel
about to start. The server passes them straight into that kernel's environment; they are never saved,
never sent to the page or the agent, and never logged.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import importlib
import io
import json
import os
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyarrow.ipc as ipc

from swissarmybench.adapters.blades import BladeStore
from swissarmybench.domain import blade_tables, dataverse, lakes, python_connections
from swissarmybench.domain.blades import Blade
from swissarmybench.domain.connections import TEST_ROWS

_MAX_ANSWER_BYTES: int = 512 * 1024 * 1024


class RefreshError(RuntimeError):
    def __init__(self, message: str, missing_module: str | None = None) -> None:
        super().__init__(message)
        self.missing_module = missing_module


def _listed_by_adapter(blade: Blade) -> str:
    from swissarmybench.server.blade_templates import TEMPLATES

    return blade_tables.listed_by_adapter(
        blade.kind, blade.template, blade.dialect, blade.catalog_language, blade.catalog_command, TEMPLATES
    )


def payload(
    store: BladeStore, blade: Blade, mode: str, typed: dict[str, str], extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """What the child needs: the blade, the vault blades that supply its missing secrets, typed values.
    For an analysis (`extra`): the grid's rows as an Arrow table (sent as Arrow IPC) and the columns."""
    vaults, _ = store.providers(blade)
    rows: dict[str, Any] = {}
    if extra and extra.get("table") is not None:
        sink = io.BytesIO()
        with ipc.new_stream(sink, extra["table"].schema) as writer:
            writer.write_table(extra["table"])
        encoded = base64.b64encode(sink.getvalue()).decode("ascii")
        rows = {"rows": encoded, "columns": extra.get("columns", [])}
    # A connection from the user's own Python: its Read a table box, its plain values, the names saved
    # on this computer; each vault it maps runs first, with only this connection's entries.
    python: dict[str, Any] | None = None
    if blade.template == python_connections.TEMPLATE and blade.kind == "other":
        python = {
            "read": blade.read_command,
            "set": python_connections.plain_values(blade.variables),
            "keyring": python_connections.keyring_names(blade.variables),
            # mode "read": which table, and how many rows (None: every row)
            "place": (extra or {}).get("place"),
            "limit": (extra or {}).get("limit"),
        }
    elif lakes.is_kind(blade.dialect) and mode == "read":
        # A lake's or SharePoint's table, by the connection's own read: the columns and filters a DuckDB
        # query sends it, its rows as Arrow.
        python = {
            "adapter": "rows",  # through the adapter's Rows (Plans/adapter.plan.md)
            "read": lakes.READ,
            "set": {},
            "keyring": [],
            "place": (extra or {}).get("place"),
            "limit": (extra or {}).get("limit"),
            "columns": (extra or {}).get("columns"),
            "filters": (extra or {}).get("filters"),
        }
    elif dataverse.is_dataverse(blade.dialect) and mode == "read":
        # A Dataverse environment's table, through its Web API: the adapter's OData read over the connection's
        # own calls (Plans/adapter.plan.md).
        python = {
            "adapter": "odata",
            "read": dataverse.READ,
            "set": {},
            "keyring": [],
            "place": (extra or {}).get("place"),
            "limit": (extra or {}).get("limit"),
        }
    mapped = python_connections.vault_jobs(blade.variables, store.get, store.saved_secrets)
    return {
        **rows,
        "python": python,
        "mode": mode,  # "catalog", "test", "rows", "queries", "datasets", "names", "analysis" or "read"
        "label": blade.name,
        "kind": blade.kind,
        "code": blade.code,
        "variable": blade.variable,
        # A draft's typed passwords (the Add connection form's Test, nothing saved) over the saved ones.
        "secrets": store.saved_secrets(blade) | dict((extra or {}).get("secrets", {})),
        "catalog": {
            "language": blade.catalog_language,
            "command": blade.catalog_command,
            # its tables listed by the adapter unless its List the tables is the user's own (step 3)
            "adapter": _listed_by_adapter(blade),
        },
        "vault_mapping": blade.vault_mapping,
        "vault_all": blade.vault_all,
        "vaults": [
            {
                "label": v.name,
                "code": v.code,
                "variable": v.variable,
                "mapping": v.vault_mapping,
                "every": v.vault_all,
                "secrets": store.saved_secrets(v),
            }
            for v in vaults
        ]
        + mapped,
        "env": typed,
        # mode "rows": a table's rows (a SELECT and its COUNT in the source's own SQL); none: a file
        # connection, whose answer is the file it reaches.
        "sql": (extra or {}).get("sql"),
        "count_sql": (extra or {}).get("count_sql"),
        # mode "rows" on a DuckDB connection: the table and the adapter's plan ({"table", "plan", "count"}).
        "read": (extra or {}).get("read"),
        # mode "queries": groups of statements, tried in order (a Power BI dataset's relationships).
        "attempts": (extra or {}).get("attempts"),
        # modes "rows" and "queries" on a Power BI workspace: the dataset the statements are sent to.
        "dataset": (extra or {}).get("dataset"),
        # mode "write": sab.write's request ({"table", "mode", "key", "dry_run", "records"? or "ipc"?}).
        "write": (extra or {}).get("write"),
        # mode "rows" in a SQL source's own SQL: what it sent to the source (the call statistics' folded).
        "folded": (extra or {}).get("folded"),
    }


def load_payload(store: BladeStore) -> dict[str, Any] | None:
    """Every vault blade, to read all their entries at once (a Workbench kernel's environment); None when
    there are none (no child is started)."""
    vaults = [b for b in store.all() if b.kind == "vault" and (b.vault_mapping or b.vault_all)]
    if not vaults:
        return None
    return {
        "mode": "load",
        "label": "the vaults",
        "kind": "load",
        "vaults": [
            {
                "label": v.name,
                "code": v.code,
                "variable": v.variable,
                "mapping": v.vault_mapping,
                "every": v.vault_all,
                "secrets": store.saved_secrets(v),
            }
            for v in vaults
        ],
    }


# The beta log's hook: (event, exit code, seconds, reason) for each run's start and how it ended.
Report = Callable[[str, int | None, float | None, str], None]


def _no_report(event: str, code: int | None, seconds: float | None, reason: str = "") -> None:
    return None


async def run(job: dict[str, Any], timeout: float, report: Report = _no_report) -> dict[str, Any]:
    """Run the job in a child process; its answer, or RefreshError. `report` hears how it went (the
    beta log): never the blade's own words, which can name the user's servers."""
    began = time.monotonic()
    report("start", None, None, "")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-m",
        "swissarmybench.server.blade_runner",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=_MAX_ANSWER_BYTES,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(json.dumps(job).encode()), timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        report("timeout", process.returncode, time.monotonic() - began, "")
        raise RefreshError(
            f"{job['label']} did not finish within {timeout:.0f} seconds and was stopped. "
            "Check the server name and network, or narrow the catalog query."
        ) from None
    except asyncio.CancelledError:
        # Cancelled (the Queries window's Cancel, the page gone): the child goes with it, so its
        # connection's slot is free at once (services/connection_slots.py).
        process.kill()
        with contextlib.suppress(Exception):
            await asyncio.shield(process.wait())
        report("cancelled", process.returncode, time.monotonic() - began, "")
        raise
    try:
        answer: Any = json.loads(out.decode("utf-8") or "null")
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        tail = err.decode("utf-8", "replace").strip().splitlines()[-1:] or ["no answer"]
        report("crash", process.returncode, time.monotonic() - began, "no answer")
        raise RefreshError(f"{job['label']} stopped unexpectedly: {tail[0][:500]}")
    if "error" in answer:
        report("failed", process.returncode, time.monotonic() - began, "the blade's code raised an error")
        raise RefreshError(str(answer["error"]), answer.get("missing_module"))
    report("end", process.returncode, time.monotonic() - began, "")
    if "arrow" in answer:  # a table's rows, typed: Arrow IPC in base64
        answer["table"] = ipc.open_stream(io.BytesIO(base64.b64decode(answer.pop("arrow")))).read_all()
    return answer


async def run_streaming(
    job: dict[str, Any],
    timeout: float,
    on_output: Callable[[str, str], None],
    started: Callable[[Callable[[], None]], None] | None = None,
    report: Report = _no_report,
) -> dict[str, Any]:
    """The blade IDE's Run (job mode "run") in a child process: each print and warning to `on_output` as it
    comes ("stdout" or "stderr", its text), then the answer. `started` is handed the child's stop (Cancel).
    A run that hangs is stopped at `timeout`; a stopped run answers {"ok": False, "cancelled": True}."""
    began = time.monotonic()
    report("start", None, None, "")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-m",
        "swissarmybench.server.blade_runner",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=_MAX_ANSWER_BYTES,
    )
    stopped = False

    def stop() -> None:
        nonlocal stopped
        stopped = True
        with contextlib.suppress(ProcessLookupError):
            process.kill()

    if started is not None:
        started(stop)
    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise RefreshError(f"{job['label']} could not be started.")
    process.stdin.write(json.dumps(job).encode())
    with contextlib.suppress(BrokenPipeError, ConnectionResetError):
        await process.stdin.drain()
    process.stdin.close()
    err_stream = process.stderr
    out_stream = process.stdout

    async def read_err() -> None:
        async for raw in err_stream:
            line = raw.decode("utf-8", "replace")
            try:
                item = json.loads(line)
            except ValueError:
                item = None
            if isinstance(item, dict) and ("o" in item or "e" in item):
                on_output("stdout" if "o" in item else "stderr", str(item.get("o", item.get("e", ""))))
            elif line.strip():
                on_output("stderr", line)  # written past Python (a driver's C library)

    try:
        out, _ = await asyncio.wait_for(asyncio.gather(out_stream.read(), read_err()), timeout)
        await process.wait()
    except TimeoutError:
        stop()
        await process.wait()
        report("timeout", process.returncode, time.monotonic() - began, "")
        return {
            "ok": False,
            "failed": f"{job['label']} did not finish within {timeout:.0f} seconds and was stopped.",
        }
    if stopped:
        report("cancelled", process.returncode, time.monotonic() - began, "")
        return {"ok": False, "cancelled": True, "failed": "Stopped."}
    try:
        answer: Any = json.loads(out.decode("utf-8") or "null")
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        report("crash", process.returncode, time.monotonic() - began, "no answer")
        return {
            "ok": False,
            "failed": f"{job['label']} stopped unexpectedly (exit code {process.returncode}).",
        }
    if "error" in answer:  # a vault or a password before the code ran: the plain words
        answer = {"ok": False, "failed": str(answer["error"]), "missing_module": answer.get("missing_module")}
    report("end" if answer.get("ok") else "failed", process.returncode, time.monotonic() - began, "")
    result = answer.get("result")
    if isinstance(result, dict) and "arrow" in result:
        result["table"] = ipc.open_stream(io.BytesIO(base64.b64decode(result.pop("arrow")))).read_all()
    ran: dict[str, Any] = answer
    return ran


# ===== installing packages =====

_INSTALL_TIMEOUT_SECONDS: float = 600.0


async def install_packages(packages: list[str]) -> tuple[int | None, str]:
    """Install packages into Swiss Army Bench's own Python, where Refresh runs: with uv when it is here,
    else pip. Returns the exit code (None when it ran over ten minutes and was stopped) and the output."""
    uv = shutil.which("uv") or next(
        (
            str(p)
            for p in (Path.home() / ".local" / "bin" / "uv", Path.home() / ".cargo" / "bin" / "uv")
            if p.is_file()
        ),
        None,
    )
    command = (
        [uv, "pip", "install", "--python", sys.executable, *packages]
        if uv
        else [sys.executable, "-m", "pip", "install", *packages]
    )
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        out, _ = await asyncio.wait_for(process.communicate(), _INSTALL_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        return None, ""
    importlib.invalidate_caches()  # what was just installed is found by the next check at once
    return process.returncode, out.decode("utf-8", "replace")


async def install_missing(codes: list[str]) -> list[str]:
    """What these codes import that this Python lacks (each known to pip by its import's name; one only
    guessed is left to Install now), installed before they run (the owner, 2026-11-24: missing packages
    found and installed by themselves). The packages installed; none when nothing was missing or it failed.
    SWISSARMYBENCH_AUTO_INSTALL=off: never (the tests: Install now stays the way)."""
    from swissarmybench.adapters.blade_run import needed

    if os.environ.get("SWISSARMYBENCH_AUTO_INSTALL", "").lower() in ("off", "0", "false", "no"):
        return []
    pips = list(
        dict.fromkeys(p.pip for code in codes for p in needed(code) if not p.installed and not p.guessed)
    )
    if not pips:
        return []
    code, _ = await install_packages(pips)
    return pips if code == 0 else []


# ===== the child process =====


def _child(job: dict[str, Any]) -> dict[str, Any]:
    from swissarmybench.adapters.blade_run import (
        BladeRunError,
        adapter_catalog,
        close_quietly,
        list_tables,
        run_catalog,
        run_code,
        run_vault,
        set_variables,
    )

    if job["mode"] == "load":
        return _load(job)
    os.environ.update({k: str(v) for k, v in job.get("env", {}).items()})
    secrets: dict[str, str] = dict(job.get("secrets", {}))
    hidden = {**secrets, **{f"env:{k}": str(v) for k, v in job.get("env", {}).items()}}
    try:
        for vault in job.get("vaults", []):
            values = run_vault(
                vault["code"],
                vault["variable"],
                vault["mapping"],
                vault["secrets"],
                vault["label"],
                bool(vault.get("every")),
            )
            hidden.update({f"vault:{k}": v for k, v in values.items()})
        python = job.get("python")
        if python:
            catalog_code = (job.get("catalog") or {}).get("command")
            reads = python_connections.env_reads(job["code"], catalog_code, python.get("read"))
            set_variables(reads, python["set"], python["keyring"], secrets, job["label"])
        if job["mode"] == "run":
            return _ide_run(job, secrets, hidden)
        if job["mode"] == "read":
            return _read(job, hidden)
        if job["mode"] == "names":
            return _names(job, secrets)
        if job["mode"] == "rows":
            return _rows(job, secrets)
        if job["mode"] == "queries":
            return _queries(job, secrets)
        if job["mode"] == "datasets":
            return _datasets(job, secrets)
        if job["mode"] == "write":
            return _write(job, hidden)
        if job["kind"] == "vault":
            every = bool(job.get("vault_all"))
            values = run_vault(
                job["code"], job["variable"], job["vault_mapping"], secrets, job["label"], every
            )
            return {"ok": True, "variables": sorted(values)}  # names only: the values stay in this process
        value, names = run_code(job["code"], job["variable"], secrets, job["label"])
        if job["mode"] == "analysis":
            return _analysis(value, job)
        try:
            if job["mode"] == "test":
                return _python_tested(value, names, job, hidden) if python else _tested(value)
            catalog = job["catalog"]
            if python:
                columns, rows = list_tables(names, catalog["command"], hidden, job["label"])
            elif catalog.get("adapter"):
                columns, rows = adapter_catalog(value, catalog["adapter"], hidden, job["label"])
            else:
                columns, rows = run_catalog(
                    value, names, catalog["language"], catalog["command"], hidden, job["label"]
                )
            return {"columns": columns, "rows": rows}
        finally:
            close_quietly(value)
    except BladeRunError as error:
        message = str(error)
        for secret in hidden.values():
            if secret and len(secret) >= 3:
                message = message.replace(secret, "****")
        return {"error": message, "missing_module": error.missing_module}


def _rows(job: dict[str, Any], secrets: dict[str, str]) -> dict[str, Any]:
    """A table's rows for Open as grid: the SELECT (limited, or every row) and the COUNT, run on the
    connection; the rows as typed Arrow. A file connection (no SQL): the file it reaches."""
    import pyarrow as pa

    from swissarmybench.adapters.blade_run import _sql_rows, close_quietly, run_code

    began = time.perf_counter()
    value, _ = run_code(job["code"], job["variable"], secrets, job["label"])
    _CONNECTED["ms"] = round((time.perf_counter() - began) * 1000, 1)
    try:
        if not job.get("sql"):
            return {"path": str(value)}
        source = _within(value, job)
        adapted = _adapter_rows(source, job["read"], job.get("count_sql")) if job.get("read") else None
        if adapted is not None:
            return adapted
        typed = getattr(source, "read_arrow", None)  # a connection that reads typed Arrow itself (SQL Server)
        began = time.perf_counter()
        table = typed(job["sql"]) if callable(typed) else None
        columns, rows = ([], []) if table is not None else _sql_rows(source, job["sql"])
        if job.get("folded") is not None:  # a table's read in its own SQL: one fact for the statistics
            _FACTS.append(_sql_fact(job, began, table, columns, rows))
        total = None
        if job.get("count_sql"):
            _, counted = _sql_rows(source, job["count_sql"])
            total = int(counted[0][0]) if counted and counted[0] and counted[0][0] is not None else None
    finally:
        close_quietly(value)
    if table is not None:
        return {"arrow": _arrow_text(table), "total": total}
    arrays = []
    for i in range(len(columns)):
        values = [row[i] for row in rows]
        try:
            arrays.append(pa.array(values))
        except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError):
            arrays.append(pa.array([None if v is None else str(v) for v in values], pa.string()))
    return {"arrow": _arrow_text(pa.Table.from_arrays(arrays, names=columns)), "total": total}


def _adapter_rows(
    connection: Any, read: dict[str, Any], count_sql: str | None = None
) -> dict[str, Any] | None:
    """A connection's table through the adapter (Plans/adapter.plan.md): DuckDB's own, or a SQL database's
    DB-API connection in its dialect; its plan folded into the read, the batches made the table and nothing
    else kept; its row count when asked (SQL Server's from its system views, as before). None: a connection
    the adapter does not read (its SQL is sent instead)."""
    from swissarmybench.adapters import adapter as sab
    from swissarmybench.adapters.blade_run import _sql_rows

    sab.observe(_FACTS.append)
    dialect = str(read.get("dialect") or "duckdb")
    source: Any
    if type(connection).__module__.split(".")[0] in ("duckdb", "_duckdb"):
        source = sab.DuckDB.over(connection)
    elif dialect in sab.DIALECTS and callable(getattr(connection, "cursor", None)):
        source = sab.Sql(connection, dialect)
    else:
        return None
    table = sab.make_table(sab.TableSource(source, str(read["table"]), sab.plan_from(read.get("plan"))))
    total = None
    if read.get("count") and count_sql and dialect == "sqlserver":
        _, counted = _sql_rows(connection, count_sql)
        total = int(counted[0][0]) if counted and counted[0] and counted[0][0] is not None else None
    elif read.get("count"):
        reader, _ = sab.read(source, str(read["table"]), sab.Plan(totals=(sab.Total("count"),)))
        total = int(reader.read_all().column(0)[0].as_py())
    return {"arrow": _arrow_text(table), "total": total}


def _write(job: dict[str, Any], secrets: dict[str, str]) -> dict[str, Any]:
    """sab.write on the connection (the agent's connections_write): its client in the adapter's backend, the
    dry run counted by reads, else the rows written; the answer is the counts and the report's words."""
    from swissarmybench.adapters.blade_run import BladeRunError, close_quietly, run_code
    from swissarmybench.client import writes

    asked = job["write"]
    rows: Any = asked.get("records")
    if asked.get("ipc"):
        rows = ipc.open_stream(io.BytesIO(base64.b64decode(asked["ipc"]))).read_all()
    value, _ = run_code(job["code"], job["variable"], secrets, job["label"])
    try:
        made = writes.write_with(
            job["label"], value, asked["table"], rows, asked["mode"], asked.get("key"), bool(asked["dry_run"])
        )
        return writes.answer(made)
    except writes.WriteError as error:
        raise BladeRunError(str(error)) from None
    finally:
        close_quietly(value)


def _arrow_text(table: Any) -> str:
    sink = io.BytesIO()
    with ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return base64.b64encode(sink.getvalue()).decode("ascii")


def _within(value: Any, job: dict[str, Any]) -> Any:
    """What the statements run on: the connection, or, for a Power BI workspace, the dataset the job
    names (the connection's own `dataset(name)`)."""
    pick = getattr(value, "dataset", None)
    return pick(job["dataset"]) if job.get("dataset") and callable(pick) else value


def _datasets(job: dict[str, Any], secrets: dict[str, str]) -> dict[str, Any]:
    """A Power BI workspace's datasets, from the connection's own `datasets()`: each one's name and
    id. None for a connection that has no such list (it is one dataset by itself)."""
    from swissarmybench.adapters.blade_run import close_quietly, run_code

    value, _ = run_code(job["code"], job["variable"], secrets, job["label"])
    try:
        lister = getattr(value, "datasets", None)
        if not callable(lister):
            return {"datasets": None}
        return {"datasets": [{"name": str(d["name"]), "id": str(d["id"])} for d in lister()]}
    finally:
        close_quietly(value)


# ===== a connection from the user's own Python: Read a table, and its Test =====


def read_result(result: Any, total: int | None, limit: int | None) -> tuple[Any, int | None]:
    """What Read a table returned as a typed Arrow table of at most `limit` rows, and how many rows
    the source holds when that is known: it said so (`(rows, total)`), or it ignored the limit and
    returned them all. A DataFrame, an Arrow table, a list of dicts: whatever push accepts."""
    from swissarmybench.adapters.blade_run import BladeRunError
    from swissarmybench.client.push_client import _to_arrow

    if isinstance(result, list) and not result:
        raise BladeRunError("Read a table returned no rows, so there is nothing to show.")
    if isinstance(result, list) and not all(isinstance(row, dict) for row in result):
        raise BladeRunError(
            f"Read a table returned a list that is not all dicts. Return {python_connections.READ_SHAPE}."
        )
    try:
        table = _to_arrow(result)
    except (TypeError, ValueError) as error:
        raise BladeRunError(
            f"Read a table returned a {type(result).__name__}. Return {python_connections.READ_SHAPE}. "
            f"({error})"
        ) from None
    kept, total = python_connections.read_total(table.num_rows, limit, total)
    return (table.slice(0, kept) if kept < table.num_rows else table), total


def _arrow_answer(table: Any) -> str:
    sink = io.BytesIO()
    with ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return base64.b64encode(sink.getvalue()).decode("ascii")


def _read(job: dict[str, Any], secrets: dict[str, str]) -> dict[str, Any]:
    """A table's rows for Open as grid and the preview: Connect, then Read a table."""
    from swissarmybench.adapters.blade_run import BladeRunError, close_quietly, read_table, run_code

    python = job.get("python") or {}
    if not python.get("read"):
        raise BladeRunError(f"{job['label']} has no Read a table: open the connection and fill it in.")
    place = python.get("place") or {}
    began = time.perf_counter()
    value, names = run_code(job["code"], job["variable"], secrets, job["label"])
    _CONNECTED["ms"] = round((time.perf_counter() - began) * 1000, 1)
    adapter = python.get("adapter")
    if (adapter == "odata" and callable(getattr(value, "described", None))) or (
        adapter == "rows" and callable(getattr(value, "rows", None))
    ):
        try:
            return _adapter_read(value, adapter, place, python)
        except Exception as error:
            raise BladeRunError(f"{job['label']}: {error}") from None
        finally:
            close_quietly(value)
    try:
        limit = python.get("limit")
        result, total = read_table(
            names,
            python["read"],
            str(place.get("schema") or ""),
            str(place.get("table") or ""),
            limit,
            secrets,
            job["label"],
            python.get("columns") or None,
            python.get("filters") or None,
            frame=False,
        )
        # How the connection read it (the lake kinds say: delta_scan, deltalake, its log, read_parquet).
        meta = getattr(getattr(result, "schema", None), "metadata", None) or {}
        how = meta.get(b"sab_read", b"").decode("utf-8", "replace")
        table, total = read_result(result, total, limit)
    finally:
        close_quietly(value)
    return {"arrow": _arrow_answer(table), "total": total} | ({"read_with": how} if how else {})


def _adapter_read(
    connection: Any, adapter: str, place: dict[str, Any], python: dict[str, Any]
) -> dict[str, Any]:
    """A Dataverse table (OData) or a lake's or SharePoint's (Rows) through the adapter: the limit, and the
    columns and filters a DuckDB query sends, folded into the connection's own read; the count it gave and,
    for the lakes, how it read the files (the table's sab_read)."""
    from swissarmybench.adapters import adapter as sab

    sab.observe(_FACTS.append)
    source: Any = sab.OData(connection) if adapter == "odata" else sab.Rows(connection)
    table = str(place.get("table") or "")
    if adapter == "rows" and place.get("schema"):
        table = f"{place['schema']}/{table}"
    filters = tuple(
        sab.Filter(str(c), "!=" if op == "<>" else str(op).lower(), v)
        for c, op, v in python.get("filters") or []
    )
    plan = sab.Plan(columns=tuple(python.get("columns") or ()), filters=filters, limit=python.get("limit"))
    made = sab.make_table(sab.TableSource(source, table, plan))
    meta = made.schema.metadata or {}
    how = meta.get(b"sab_read", b"").decode("utf-8", "replace")
    return {"arrow": _arrow_answer(made), "total": source.total} | ({"read_with": how} if how else {})


def _plain(value: Any) -> Any:
    """A cell as JSON holds it: text for what JSON has no word for, nothing for a missing number."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else None
    return str(value)


def _python_tested(value: Any, names: dict[str, Any], job: dict[str, Any], secrets: dict[str, str]) -> Any:
    """Test, for the user's own Python: Connect ran; then List the tables; then the first table's first
    rows by Read a table. Each box that is filled in is run, and the first to fail says so."""
    from swissarmybench.adapters.blade_run import list_tables, read_table

    made = _tested(value)
    command = (job.get("catalog") or {}).get("command")
    if "error" in made or not command:
        return made
    columns, rows = list_tables(names, command, secrets, job["label"])
    made |= {"tables": python_connections.table_count(columns, rows), "columns": len(rows)}
    read = (job.get("python") or {}).get("read")
    if not read:
        return made
    schema, table = python_connections.first_table(columns, rows)
    result, total = read_table(names, read, schema, table, TEST_ROWS, secrets, job["label"])
    arrow, total = read_result(result, total, TEST_ROWS)
    made["preview"] = {
        "table": table,
        "schema": schema,
        "columns": [str(c) for c in arrow.column_names],
        "rows": [[_plain(v) for v in row.values()] for row in arrow.to_pylist()],
        "total": total,
    }
    return made


def _queries(job: dict[str, Any], secrets: dict[str, str]) -> dict[str, Any]:
    """Several statements on the connection, signed in once. `attempts` is groups of statements, tried
    in order: the first group whose every statement the source answers is the answer ({"attempt": which
    group, "results": [{"columns", "rows"}, ...]}); when none does, the first group's refusal."""
    from swissarmybench.adapters.blade_run import BladeRunError, _sql_rows, close_quietly, run_code

    value, _ = run_code(job["code"], job["variable"], secrets, job["label"])
    refused: BaseException | None = None
    try:
        source = _within(value, job)
        for at, statements in enumerate(job.get("attempts") or []):
            try:
                results = []
                for statement in statements:
                    columns, rows = _sql_rows(source, str(statement))
                    results.append({"columns": columns, "rows": rows})
                return {"attempt": at, "results": results}
            except BaseException as error:
                if isinstance(error, KeyboardInterrupt | SystemExit):
                    raise
                refused = refused or error
    finally:
        close_quietly(value)
    raise BladeRunError(f"{job['label']} did not answer: {type(refused).__name__}: {refused}")


def _names(job: dict[str, Any], secrets: dict[str, str]) -> dict[str, Any]:
    """A vault's secret names, from its `names()`: names only, no value is read. None when the vault's
    code has no names() (the user types the names instead)."""
    from swissarmybench.adapters.blade_run import BladeRunError, run_code

    _, made = run_code(job["code"], job["variable"], secrets, job["label"])
    lister = made.get("names")
    if not callable(lister):
        return {"names": None}
    try:
        found = lister()
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt | SystemExit):
            raise
        raise BladeRunError(
            f"{job['label']} could not list its secrets: {type(error).__name__}: {error}"
        ) from None
    return {"names": [str(n) for n in list(found)[:20_000]]}


def _load(job: dict[str, Any]) -> dict[str, Any]:
    """Every vault's entries: {"values": {variable: value}, "problems": [a vault that failed, why], "names":
    {a vault that loads every secret: the secret names it listed}}. One vault failing leaves the others'
    values (a kernel still starts). Every vault is listed first, then the names are given out as the server
    gives them (domain/vault_names.py assign: `reserved`, each vault's `kept`): no variable twice, a taken
    one prefixed with its vault's name. The names are names only (the server keeps them: vault_names.py)."""
    from swissarmybench.adapters.blade_run import BladeRunError, open_vault, read_vault
    from swissarmybench.domain import vault_names as naming

    values: dict[str, str] = {}
    problems: list[str] = []
    names: dict[str, list[str]] = {}
    opened: list[tuple[dict[str, Any], Any]] = []

    def failed(vault: dict[str, Any], error: BladeRunError) -> None:
        message = str(error)
        for secret in [*vault["secrets"].values(), *values.values()]:
            if secret and len(secret) >= 3:
                message = message.replace(secret, "****")
        problems.append(message)

    for vault in job.get("vaults", []):
        try:
            getter, found = open_vault(
                vault["code"], vault["variable"], vault["secrets"], vault["label"], bool(vault.get("every"))
            )
        except BladeRunError as error:
            failed(vault, error)
            continue
        if found is not None:
            names[str(vault["label"])] = found
        opened.append((vault, getter))
    inputs = [
        naming.VaultIn(
            str(v["label"]),
            dict(v["mapping"]),
            bool(v.get("every")),
            names.get(str(v["label"]), []),
            dict(v.get("kept") or {}),
        )
        for v, _ in opened
    ]
    reserved = naming.reserved([str(n) for n in job.get("yours") or []], inputs)  # your variables first
    given = naming.assign(inputs, reserved)
    for vault, getter in opened:
        mapping = given[str(vault["label"])].mapping
        try:
            values.update(read_vault(getter, mapping, vault["secrets"], vault["label"]))
        except BladeRunError as error:
            failed(vault, error)
    return {"values": values, "problems": problems, "names": names}


def _tested(value: Any) -> dict[str, Any]:
    """A test's answer: what the code made. A path must be there (making a Path always works)."""
    import os
    from pathlib import Path

    # A class the connection's own code defines (a Power BI dataset's) is named by itself.
    module = type(value).__module__
    made = {
        "ok": True,
        "type": type(value).__qualname__ if module == "__blade__" else f"{module}.{type(value).__qualname__}",
    }
    if isinstance(value, os.PathLike):
        path = Path(value).expanduser()
        made["path"] = str(path)  # where it is, for a file connection's preview (services/connections.py)
        if path.is_dir():
            files = [p for p in path.iterdir() if p.is_file()]
            return made | {"found": f"a folder of {len(files)} file{'' if len(files) == 1 else 's'}"}
        if path.is_file():
            return made | {"found": f"a file of {path.stat().st_size:,} bytes"}
        return {"error": f"{path} is not there: check the path (and that this computer can reach it)."}
    if module.startswith("trino."):  # Trino connects on its first query: one, so Test signs in
        from swissarmybench.adapters.blade_run import BladeRunError

        try:
            cursor = value.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchall()
        except Exception as error:  # the driver's own: refused, unreachable, a certificate it would not take
            raise BladeRunError(f"Trino did not let it in: {type(error).__name__}: {error}") from None
        return made | {"found": "signed in"}
    tester = getattr(value, "tested", None)
    if module == "__blade__" and callable(tester):  # its own Test (a Dataverse environment's): rows too
        said = tester(TEST_ROWS)
        made["found"] = str(said.get("found") or "")
        if isinstance(said.get("about"), dict):  # what the server is (SQL Server's: the card says it)
            made["about"] = {str(k): v for k, v in said["about"].items() if isinstance(v, str | bool)}
        if said.get("notes"):
            made["notes"] = [str(n) for n in said["notes"]][:20]
        shown = said.get("preview")
        if isinstance(shown, dict) and shown.get("rows"):
            arrow, total = read_result(shown["rows"], shown.get("total"), TEST_ROWS)
            made["preview"] = {
                "table": str(shown.get("table") or ""),
                "schema": "",
                "columns": [str(c) for c in arrow.column_names],
                "rows": [[_plain(v) for v in row.values()] for row in arrow.to_pylist()],
                "total": total,
            }
        return made
    lister = getattr(value, "datasets", None)
    if module == "__blade__" and callable(lister):  # a Power BI workspace: it signed in and listed them
        count = len(lister())
        return made | {"found": f"signed in and found {count} dataset{'' if count == 1 else 's'}"}
    return made


def _analysis(function: Any, job: dict[str, Any]) -> dict[str, Any]:
    """Call the user's analysis on the grid's rows and turn what it returns into Visualizations cards."""
    import inspect

    import pyarrow as pa

    from swissarmybench.adapters.blade_run import BladeRunError
    from swissarmybench.client.visualizations_client import card_for

    if not callable(function):
        raise BladeRunError(f"{job['label']}'s {job['variable']!r} is not a function.")
    table = ipc.open_stream(io.BytesIO(base64.b64decode(job["rows"]))).read_all()
    frame = table.to_pandas() if isinstance(table, pa.Table) else table
    takes = len(inspect.signature(function).parameters)
    try:
        answer = function(frame, list(job.get("columns", []))) if takes >= 2 else function(frame)
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt | SystemExit):
            raise
        raise BladeRunError(f"{job['label']} stopped: {type(error).__name__}: {error}") from None
    title = None
    parts = answer if isinstance(answer, list | tuple) else [answer]
    if isinstance(answer, dict) and not ({"data", "$schema"} & set(answer)):
        title = answer.get("title")
        parts = [answer[k] for k in ("markdown", "table", "figure") if answer.get(k) is not None]
    cards = []
    for part in parts[:12]:
        if part is None:
            continue
        try:
            cards.append(card_for(part))
        except (TypeError, ValueError) as error:
            message = f"{job['label']} returned something the Analyze board can't show: {error}"
            raise BladeRunError(message) from None
    if not cards:
        raise BladeRunError(f"{job['label']} returned nothing to show: return markdown, a table or a figure.")
    return {"title": title, "cards": cards}


# ===== the blade IDE's Run (the owner, 2026-11-21: "a play button to execute") =====

# Values never sent back: each secret the run holds, put in by _child (an answer, a printed line or a value's
# preview with one in it says **** instead).
_HIDDEN: list[str] = []
_RESULT_ROWS = 200
_TEXT_CHARS = 20_000


def _scrub(text: str) -> str:
    for secret in _HIDDEN:
        if secret and len(secret) >= 3:
            text = text.replace(secret, "****")
    return text


class _Stream(io.TextIOBase):
    """A blade's print() and its warnings, each write one JSON line on the real stderr: {"o": text} or
    {"e": text}. The server streams them to the IDE's Output as they come."""

    def __init__(self, key: str, sink: Any) -> None:
        self._key = key
        self._sink = sink

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        if text:
            self._sink.write(json.dumps({self._key: _scrub(text)}) + "\n")
            self._sink.flush()
        return len(text)


def _ide_run(job: dict[str, Any], secrets: dict[str, str], hidden: dict[str, str]) -> dict[str, Any]:
    """Run a blade's code (the editor's, saved or not) as Test does, and answer what it makes: a table's
    columns, types, first rows and count (the whole table as Arrow, for Open as grid), or a value's text. A
    failure answers the error panel's detail (client/kernel_errors.py), the code's own lines marked: the code
    is compiled under `filename`, an absolute name the error panel reads as your file."""
    import ast
    import inspect
    import linecache

    from swissarmybench.adapters.blade_run import _secret_function, close_quietly, run_vault
    from swissarmybench.client import kernel_errors

    __tracebackhide__ = True  # the error panel's frames start at the blade's own code
    _HIDDEN[:] = [v for v in hidden.values() if v]
    code, label, filename = job["code"], job["label"], str(job.get("filename") or "<blade>")
    linecache.cache[filename] = (len(code), None, code.splitlines(keepends=True), filename)

    def failed(error: BaseException) -> dict[str, Any]:
        sys.last_exc = error
        sys.last_value = error
        try:
            detail = json.loads(kernel_errors.detail())
        except Exception:
            detail = {}
        missing = error.name if isinstance(error, ModuleNotFoundError) else None
        return {
            "ok": False,
            "failed": f"{type(error).__name__}: {error}",
            "detail": detail,
            "missing_module": missing,
        }

    if job["kind"] == "vault":
        values = run_vault(
            code, job["variable"], job["vault_mapping"], secrets, label, bool(job.get("vault_all"))
        )
        listed = ", ".join(sorted(values)) or "nothing"
        return {"ok": True, "result": {"kind": "value", "type": "vault", "text": f"It sets {listed}."}}
    names: dict[str, Any] = {"__name__": "__blade__", "secret": _secret_function(secrets, label)}
    value: Any = None
    try:
        tree = ast.parse(code, filename)
        last: ast.expr | None = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = tree.body.pop().value
        exec(compile(tree, filename, "exec"), names)  # noqa: S102 (the user's own code, on their Run)
        if last is not None:
            value = eval(compile(ast.Expression(last), filename, "eval"), names)  # noqa: S307 (as above)
        variable = job.get("variable") or ""
        if variable in names:
            value = names[variable]
        elif last is None:
            made = [n for n in names if not n.startswith("_") and n != "secret"]
            listed = ", ".join(made) or "nothing"
            return {
                "ok": False,
                "failed": f"It ran but made no variable named {variable!r}. It made: {listed}.",
            }
        made_by = None
        if callable(value) and job["kind"] != "analysis" and not isinstance(value, type):
            try:
                needed = any(
                    p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                    for p in inspect.signature(value).parameters.values()
                )
            except (TypeError, ValueError):
                needed = True
            if not needed:  # a table blade's function: what it returns is what it makes
                made_by = getattr(value, "__name__", "it")
                value = value()
        elif callable(value) and job["kind"] == "analysis" and job.get("mode") == "run":
            # The IDE's Run tries an analysis on made-up rows (the Analyze page gives it a table's own).
            import pandas as pd

            made_by = getattr(value, "__name__", "it")
            value = value(pd.DataFrame(_SAMPLE_ROWS))
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            raise
        return failed(error)
    try:
        return {"ok": True, "result": _ide_result(value, made_by)}
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            raise
        return failed(error)
    finally:
        close_quietly(value)


# Made-up rows an analysis blade is tried on by the IDE's Run.
_SAMPLE_ROWS: dict[str, list[Any]] = {
    "region": ["North", "South", "East", "West", "North", "South"],
    "month": ["2026-01", "2026-01", "2026-02", "2026-02", "2026-03", "2026-03"],
    "amount": [120.5, 89.0, 342.25, 57.75, 210.0, 98.5],
}


def _ide_result(value: Any, made_by: str | None) -> dict[str, Any]:
    """What a run made, for the Result tab: a table, or a value as text."""
    from swissarmybench.client.kernel_values import is_table, type_name

    if (
        is_table(value)
        or type(value).__module__.split(".")[0] == "duckdb"
        or (isinstance(value, list) and value and all(isinstance(r, dict) for r in value[:50]))
    ):
        from swissarmybench.client.push_client import _to_arrow

        table = _to_arrow(value)
        head = table.slice(0, _RESULT_ROWS)
        return {
            "kind": "table",
            "type": type_name(value),
            "made_by": made_by,
            "columns": [str(c) for c in table.column_names],
            "types": [str(t) for t in table.schema.types],
            "rows": [[_plain(v) for v in row.values()] for row in head.to_pylist()],
            "total": table.num_rows,
            "arrow": _arrow_text(table),
        }
    if callable(value) and not isinstance(value, type):
        import inspect

        try:
            shown = f"{getattr(value, '__name__', 'function')}{inspect.signature(value)}"
        except (TypeError, ValueError):
            shown = repr(value)
        return {"kind": "value", "type": "function", "made_by": made_by, "text": shown}
    text = value if isinstance(value, str) else repr(value)
    return {"kind": "value", "type": type_name(value), "made_by": made_by, "text": _scrub(text[:_TEXT_CHARS])}


# The adapter's facts of this run (adapter.observe: times, sizes, folded, fingerprint; never a value), sent
# back beside the answer for the server's call statistics (services/call_stats.py), with the connect's time.
_FACTS: list[dict[str, Any]] = []
_CONNECTED: dict[str, float | None] = {"ms": None}


def _sql_fact(
    job: dict[str, Any], began: float, table: Any, columns: list[str], rows: list[Any]
) -> dict[str, Any]:
    """A table read in its source's own SQL as the adapter's facts say a read: its time (all of it at once,
    so the first row is the total), its rows and columns, what its SQL sent to the source. Never a value."""
    ms = round((time.perf_counter() - began) * 1000, 1)
    names = list(table.column_names) if table is not None else list(columns)
    count = int(table.num_rows) if table is not None else len(rows)
    bytes_ = int(table.get_total_buffer_size()) if table is not None else 0
    shape = "|".join(names)
    return {
        "call": "read",
        "source": job["label"],
        "table": "",
        "ms": {"connect": None, "first_row": ms, "total": ms},
        "size": {"rows": count, "bytes": bytes_, "batches": 1, "columns": len(names), "asked": 0},
        "folded": [str(p) for p in job.get("folded") or []],
        "by_duckdb": [],
        "outcome": {"ok": True, "error": ""},
        "fingerprint": hashlib.sha1(shape.encode(), usedforsecurity=False).hexdigest()[:12],
    }


def _facts_sent() -> list[dict[str, Any]]:
    for facts in _FACTS:
        if facts["ms"].get("connect") is None:
            facts["ms"]["connect"] = _CONNECTED["ms"]
    return _FACTS


def main() -> None:
    job = json.loads(sys.stdin.buffer.read())
    real_stdout = sys.stdout
    if job.get("mode") == "run":  # the IDE's Run: its prints and warnings streamed, one JSON line each
        sink = sys.stderr
        with contextlib.redirect_stdout(_Stream("o", sink)), contextlib.redirect_stderr(_Stream("e", sink)):
            answer = _child(job)
        real_stdout.write(_scrub(json.dumps(answer, default=str)))
        real_stdout.flush()
        return
    with contextlib.redirect_stdout(sys.stderr):  # a blade's prints must not break the answer
        answer = _child(job)
    if _FACTS and isinstance(answer, dict):
        answer["facts"] = _facts_sent()
    json.dump(answer, real_stdout, default=str)
    real_stdout.flush()


if __name__ == "__main__":
    main()
