"""sab_perf.py: beside a launched app's pages, what the Performance Analyzer reads (the owner, 2026-11-19;
carried over to the widget Canvas, 2026-11-21: each block is a widget instance, timed by sab_canvas.render).

A copy of this file goes into the folder a launch runs in (never into a build: the build is the plain export,
whose sab_canvas finds no sab_perf and times nothing).
It records only while the analyzer is open (the file `sab_perf.on` beside it): each rerun's trigger (the
widget
whose value changed, a button, a page switch, the first load), each block's time, the calls (a SQL or DAX
an outside HTTP request, a file read), and each st.cache_data and st.cache_resource function's
calls and misses. One JSON line a rerun, into `sab_perf.jsonl` beside it. Names, times, sizes and counts only:
no value, no row, no query's text (a digest tells two queries apart). Standard library only.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ON = _HERE / "sab_perf.on"
_LOG = _HERE / "sab_perf.jsonl"
_LOCK = threading.Lock()
# Kept in sys, not in this module: Streamlit loads the app's own modules again when one changes (Play's live
# data stamp, sab_live.py), and a fresh copy of this state would patch the readers a second time.
_STATE: dict[str, Any] = sys.__dict__.setdefault(
    "_sab_perf_state", {"run": None, "values": {}, "page": None, "patched": False, "caches": {}}
)


def _on() -> bool:
    try:
        return _ON.exists()
    except OSError:
        return False


def _digest(value: Any) -> str:
    try:
        text = repr(value)
    except Exception:
        text = type(value).__name__
    return hashlib.sha256(text[:100_000].encode("utf-8", "replace")).hexdigest()[:12]


def _widget_values() -> dict[str, str]:
    try:
        import streamlit as st  # type: ignore[import-not-found, unused-ignore]

        return {str(k): _digest(v) for k, v in st.session_state.items() if not str(k).startswith("_")}
    except Exception:
        return {}


def _write(record: dict[str, Any]) -> None:
    line = json.dumps(record, default=str) + "\n"
    with _LOCK:
        try:
            with _LOG.open("a", encoding="utf-8") as out:
                out.write(line)
        except OSError:
            pass


def _call(kind: str, **said: Any) -> None:
    run = _STATE["run"]
    if run is not None:
        run["calls"].append({"kind": kind, "block": run.get("block"), **said})


# ===== what is timed: queries, outside requests, file reads, caches =====


def _patch() -> None:
    if _STATE["patched"]:
        return
    _STATE["patched"] = True
    try:
        import urllib.request

        original = urllib.request.urlopen

        @functools.wraps(original)
        def urlopen(url: Any, *args: Any, **kwargs: Any) -> Any:
            if not _on():
                return original(url, *args, **kwargs)
            start = time.perf_counter()
            target = getattr(url, "full_url", url)
            host = str(target).split("/")[2] if "://" in str(target) else "?"
            try:
                answer = original(url, *args, **kwargs)
                _call(
                    "http",
                    host=host,
                    status=getattr(answer, "status", None),
                    ms=(time.perf_counter() - start) * 1000,
                )
                return answer
            except Exception:
                _call("http", host=host, status="failed", ms=(time.perf_counter() - start) * 1000)
                raise

        urllib.request.urlopen = urlopen
    except Exception:  # noqa: S110 (the analyzer's trouble never stops the page)
        pass
    try:
        import pandas as pd

        for name in ("read_parquet", "read_csv", "read_excel", "read_json"):
            original_read = getattr(pd, name, None)
            if original_read is None:
                continue

            def reader(*args: Any, _read: Any = original_read, _name: str = name, **kwargs: Any) -> Any:
                if not _on():
                    return _read(*args, **kwargs)
                start = time.perf_counter()
                result = _read(*args, **kwargs)
                file = Path(str(args[0])).name if args else "?"
                rows = len(result) if hasattr(result, "__len__") else None
                _call("file", reader=_name, file=file, rows=rows, ms=(time.perf_counter() - start) * 1000)
                return result

            setattr(pd, name, functools.wraps(original_read)(reader))
    except Exception:  # noqa: S110 (the analyzer's trouble never stops the page)
        pass
    try:
        import streamlit as st  # type: ignore[import-not-found, unused-ignore]

        for kind in ("cache_data", "cache_resource"):
            setattr(st, kind, _Cached(getattr(st, kind), kind))
        frame = st.dataframe

        @functools.wraps(frame)
        def dataframe(data: Any = None, *args: Any, **kwargs: Any) -> Any:
            run = _STATE["run"]
            if run is not None and data is not None and hasattr(data, "shape"):
                rows, columns = [*list(data.shape), 0, 0][:2]
                run["tables"].append({"block": run.get("block"), "rows": rows, "columns": columns})
            return frame(data, *args, **kwargs)

        st.dataframe = dataframe
    except Exception:  # noqa: S110 (the analyzer's trouble never stops the page)
        pass


class _Cached:
    """st.cache_data (or cache_resource) as it is, counting each function's calls and misses (the function
    runs only on a miss) and the digests of a miss's arguments (which one changes)."""

    def __init__(self, original: Any, kind: str) -> None:
        self._original = original
        self._kind = kind

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)

    def __call__(self, func: Any = None, **settings: Any) -> Any:
        if func is None:
            return lambda f: self(f, **settings)
        name = getattr(func, "__qualname__", "function")
        kind = self._kind

        @functools.wraps(func)
        def miss(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                held = _cache(name, kind)
                held["misses"] += 1
                held["miss_ms"] += (time.perf_counter() - start) * 1000
                try:
                    import inspect

                    bound = inspect.signature(func).bind_partial(*args, **kwargs)
                    named = [(k, _digest(v)) for k, v in bound.arguments.items()]
                except Exception:
                    named = [(str(i), _digest(v)) for i, v in enumerate(args)]
                held["arguments"].append(named)

        cached = self._original(miss, **settings)

        @functools.wraps(func)
        def called(*args: Any, **kwargs: Any) -> Any:
            _cache(name, kind)["calls"] += 1
            return cached(*args, **kwargs)

        for attribute in ("clear",):
            if hasattr(cached, attribute):
                setattr(called, attribute, getattr(cached, attribute))
        return called


def _cache(name: str, kind: str) -> dict[str, Any]:
    run = _STATE["run"]
    store = run["caches"] if run is not None else {}
    held: dict[str, Any] = store.setdefault(
        name,
        {"name": name, "cache": kind.split("_")[1], "calls": 0, "misses": 0, "miss_ms": 0.0, "arguments": []},
    )
    return held


# ===== a rerun =====


def start(file: str, page: str) -> None:
    """A page's run begins: its trigger (the widget whose value changed since the last run, a page switch,
    the first load), and the clock."""
    if not _on():
        _STATE["run"] = None
        return
    _patch()
    now = _widget_values()
    before = _STATE["values"]
    changed = [k for k, v in now.items() if before.get(k) != v]
    if _STATE["page"] is None:
        trigger = "first load"
    elif _STATE["page"] != page:
        trigger = "page switch"
    elif changed:
        trigger = changed[0]
    else:
        trigger = "rerun"
    _STATE["values"], _STATE["page"] = now, page
    _STATE["run"] = {
        "kind": "run",
        "page": page,
        "trigger": trigger,
        "started": time.time(),
        "clock": time.perf_counter(),
        "last": time.perf_counter(),
        "blocks": [],
        "calls": [],
        "tables": [],
        "caches": {},
        "block": None,
    }


def before(block: str) -> None:
    """A block is about to run (its calls are its)."""
    run = _STATE["run"]
    if run is not None:
        run["block"] = block
        run["last"] = time.perf_counter()


def mark(block: str) -> None:
    """A block ran: its time since it began."""
    run = _STATE["run"]
    if run is None:
        return
    now = time.perf_counter()
    run["blocks"].append([block, (now - run["last"]) * 1000])
    run["last"] = now
    run["block"] = None


def end() -> None:
    """The page's run ended: its record written (one line)."""
    run = _STATE["run"]
    _STATE["run"] = None
    if run is None or not _on():
        return
    record = {k: v for k, v in run.items() if k not in ("clock", "last", "block")}
    record["ms"] = (time.perf_counter() - run["clock"]) * 1000
    record["caches"] = list(run["caches"].values())
    record["pid"] = os.getpid()
    _write(record)
