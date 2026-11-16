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
from swissarmybench.domain import dataverse, python_connections
from swissarmybench.domain.blades import Blade
from swissarmybench.domain.connections import TEST_ROWS

_MAX_ANSWER_BYTES: int = 512 * 1024 * 1024


class RefreshError(RuntimeError):
    def __init__(self, message: str, missing_module: str | None = None) -> None:
        super().__init__(message)
        self.missing_module = missing_module


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
    elif dataverse.is_dataverse(blade.dialect) and mode == "read":
        # A Dataverse environment's table, through its Web API: the connection's own read.
        python = {
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
        "catalog": {"language": blade.catalog_language, "command": blade.catalog_command},
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
        # mode "queries": groups of statements, tried in order (a Power BI dataset's relationships).
        "attempts": (extra or {}).get("attempts"),
        # modes "rows" and "queries" on a Power BI workspace: the dataset the statements are sent to.
        "dataset": (extra or {}).get("dataset"),
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


# ===== the child process =====


def _child(job: dict[str, Any]) -> dict[str, Any]:
    from swissarmybench.adapters.blade_run import (
        BladeRunError,
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

    value, _ = run_code(job["code"], job["variable"], secrets, job["label"])
    try:
        if not job.get("sql"):
            return {"path": str(value)}
        source = _within(value, job)
        columns, rows = _sql_rows(source, job["sql"])
        total = None
        if job.get("count_sql"):
            _, counted = _sql_rows(source, job["count_sql"])
            total = int(counted[0][0]) if counted and counted[0] else None
    finally:
        close_quietly(value)
    arrays = []
    for i in range(len(columns)):
        values = [row[i] for row in rows]
        try:
            arrays.append(pa.array(values))
        except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError):
            arrays.append(pa.array([None if v is None else str(v) for v in values], pa.string()))
    table = pa.Table.from_arrays(arrays, names=columns)
    sink = io.BytesIO()
    with ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return {"arrow": base64.b64encode(sink.getvalue()).decode("ascii"), "total": total}


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
    value, names = run_code(job["code"], job["variable"], secrets, job["label"])
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
        )
        table, total = read_result(result, total, limit)
    finally:
        close_quietly(value)
    return {"arrow": _arrow_answer(table), "total": total}


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
    """Every vault's entries: {"values": {variable: value}, "problems": [a vault that failed, why]}. One
    vault failing leaves the others' values (a kernel still starts)."""
    from swissarmybench.adapters.blade_run import BladeRunError, run_vault

    values: dict[str, str] = {}
    problems: list[str] = []
    for vault in job.get("vaults", []):
        try:
            values.update(
                run_vault(
                    vault["code"],
                    vault["variable"],
                    vault["mapping"],
                    vault["secrets"],
                    vault["label"],
                    bool(vault.get("every")),
                )
            )
        except BladeRunError as error:
            message = str(error)
            for secret in [*vault["secrets"].values(), *values.values()]:
                if secret and len(secret) >= 3:
                    message = message.replace(secret, "****")
            problems.append(message)
    return {"values": values, "problems": problems}


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
            message = f"{job['label']} returned something Visualizations can't show: {error}"
            raise BladeRunError(message) from None
    if not cards:
        raise BladeRunError(f"{job['label']} returned nothing to show: return markdown, a table or a figure.")
    return {"title": title, "cards": cards}


def main() -> None:
    job = json.loads(sys.stdin.buffer.read())
    real_stdout = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):  # a blade's prints must not break the answer
        answer = _child(job)
    json.dump(answer, real_stdout, default=str)
    real_stdout.flush()


if __name__ == "__main__":
    main()
