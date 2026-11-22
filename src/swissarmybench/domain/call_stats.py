"""The statistics of every call (the owner, 2026-11-22; Plans/stats.plan.md): "enough data to pass back to the
agent so we can actually troubleshoot, and we can make performance upgrades to widgets, tables and logic".

It reads top to bottom in the order a call is kept:

  1. A call's record   one shape for a connection's call and an API's: the object (a table, a connection,
                       an endpoint), who and where, the time in parts (waiting in the connection's line,
                       connecting, the first row or byte, the total), the size (rows, bytes, pages, columns
                       returned against columns asked), what the source folded against what DuckDB did after,
                       the outcome, the result's fingerprint. Made from the adapter's facts (from_adapter), a
                       finished slot ticket and its child's facts (from_ticket), or api_adapter's (from_api)
  2. Running figures   per object (count, errors, the last times, rows, bytes and pages): fold() adds a call,
                       figure() says p50, p95, the error rate, the typical size, the last call
  3. The kept file     .sab/stats.json (Git-ignored): the figures, sorted, byte-stable (text, read)
  4. Hints             plain words for what to change (hints): filter at the source, ask for larger pages,
                       keep it as a table, a connection's line, a failing object
  5. The agent's views summary, slowest, errors, one table, connection or endpoint, hints (view)

Never a value: names, times, sizes, kinds and fingerprints only (a failure's words stay where they were said).
Pure rules: no I/O, no clock (the service stamps `at`).
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

FORMAT = 1
KEPT_SAMPLES = 200  # each object's last times (and sizes) kept for its percentiles
MILLIONS = 1_000_000  # a read this big that names no columns, or filters after, earns a hint
MANY_PAGES = 20  # an endpoint paged this many times in one call earns a hint
SAME_READS = 5  # the same table read this often with the same shape earns a hint
SLOW_LINE_MS = 2000.0  # waiting this long for a connection's slot (95th percentile) earns a hint
FAILING_RATE = 0.2
VIEWS = ("summary", "slowest", "errors", "table", "connection", "endpoint", "hints")
OBJECTS = ("table", "connection", "endpoint")
_WHERE = ("notebook", "script", "cell", "widget", "page", "endpoint", "grid")  # names only

Call = dict[str, Any]
Figures = dict[str, dict[str, Any]]


class StatsError(ValueError):
    """A view that is not one, said in one sentence."""


# ===== 1. A call's record =====


def _num(value: Any) -> float | None:
    return round(float(value), 1) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _int(value: Any) -> int:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0


def _name(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text[:120]


def _file(path: Any) -> str:
    return _name(str(path or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1])


def where_of(source: Mapping[str, Any] | None) -> dict[str, Any]:
    """Where a call came from as names: a notebook or a script (its file's name) and its cell, a widget and
    its page, an endpoint, a grid. Anything else is left out."""
    given = dict(source or {})
    out: dict[str, Any] = {}
    document = given.pop("document", None)
    if document:
        out["notebook" if str(document).lower().endswith(".ipynb") else "script"] = _file(document)
    for key in _WHERE:
        value = given.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            out[key] = value
        elif value:
            out[key] = _name(value)
    return out


def _object(connection: str, table: str) -> dict[str, str]:
    if table:
        return {"kind": "table", "name": f"{connection}.{table}" if connection else table}
    return {"kind": "connection", "name": connection}


def _blank(at: str) -> Call:
    return {
        "at": at,
        "object": {},
        "connection": "",
        "call": "",
        "who": "user",
        "where": {},
        "ms": {"wait": None, "connect": None, "first": None, "total": None},
        "size": {"rows": 0, "bytes": 0, "pages": 0, "columns": 0, "asked": 0},
        "folded": [],
        "by_duckdb": [],
        "outcome": {"ok": True, "status": 0, "retries": 0, "error": ""},
        "fingerprint": "",
    }


def from_adapter(facts: Mapping[str, Any], where: Mapping[str, Any], who: str, at: str) -> Call:
    """One adapter call in this process (the sandbox, a file connection, an open table's read)."""
    made = _blank(at)
    ms, size, outcome = facts.get("ms") or {}, facts.get("size") or {}, facts.get("outcome") or {}
    connection = _name(facts.get("source"))
    made |= {
        "object": _object(connection, _name(facts.get("table"))),
        "connection": connection,
        "call": _name(facts.get("call")),
        "who": _name(who) or "user",
        "where": where_of(where),
        "folded": [str(p) for p in facts.get("folded") or []],
        "by_duckdb": [str(p) for p in facts.get("by_duckdb") or []],
        "fingerprint": _name(facts.get("fingerprint"))[:24],
    }
    made["ms"] |= {
        "connect": _num(ms.get("connect")),
        "first": _num(ms.get("first_row")),
        "total": _num(ms.get("total")),
    }
    made["size"] |= {k: _int(size.get(k)) for k in ("rows", "bytes", "columns", "asked")}
    made["outcome"] |= {"ok": bool(outcome.get("ok", True)), "error": _name(outcome.get("error"))[:60]}
    return made


def _main_facts(facts: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """A child process's call: its biggest read or query (a count before it is not the call)."""
    reads = [f for f in facts if isinstance(f, Mapping) and f.get("call") in ("read", "query", "write")]
    return max(reads, key=lambda f: _int((f.get("size") or {}).get("rows")), default=None)


def from_ticket(done: Mapping[str, Any], facts: Sequence[Mapping[str, Any]], at: str) -> Call:
    """A connection's call through its slots (the Queries window's finished entry), with the adapter's facts
    its child process sent back: the wait in line and the total from the ticket, the rest from the facts."""
    connection = _name(done.get("connection"))
    targets = [str(t) for t in done.get("targets") or [] if t]
    main = _main_facts(facts)
    made = (
        from_adapter(main, {}, "user", at)
        if main is not None
        else _blank(at) | {"call": _name(done.get("kind"))}
    )
    ok = done.get("outcome") == "ok"
    made |= {
        "object": _object(connection, targets[0] if targets else ""),
        "connection": connection,
        "who": _name(done.get("caller")) or "user",
        "where": where_of(done.get("source")),
    }
    made["call"] = made["call"] or _name(done.get("kind"))
    made["ms"]["wait"] = _num(float(done.get("waited") or 0) * 1000)
    made["ms"]["total"] = _num(float(done.get("seconds") or 0) * 1000)
    if main is None and done.get("rows") is not None:
        made["size"]["rows"] = _int(done.get("rows"))
    made["outcome"] |= {"ok": ok, "error": "" if ok else _name(done.get("outcome"))[:40]}
    return made


def from_api(facts: Mapping[str, Any], fingerprint: str, where: Mapping[str, Any], at: str) -> Call:
    """One API action's call (api_adapter's facts; its shape's fingerprint from the envelope)."""
    made = _blank(at)
    ms, size, outcome = facts.get("ms") or {}, facts.get("size") or {}, facts.get("outcome") or {}
    api = _name(facts.get("api"))
    made |= {
        "object": {"kind": "endpoint", "name": f"{api} {_name(facts.get('action'))}".strip()},
        "connection": api,
        "call": "api",
        "who": _name(facts.get("who")) or "user",
        "where": where_of(where),
        "fingerprint": _name(fingerprint)[:24],
    }
    made["ms"] |= {
        "wait": _num(ms.get("wait")),
        "first": _num(ms.get("first_byte")),
        "total": _num(ms.get("total")),
    }
    made["size"] |= {
        "rows": _int(size.get("records")),
        "bytes": _int(size.get("bytes")),
        "pages": _int(size.get("pages")),
        "columns": _int(size.get("columns")),
    }
    made["outcome"] |= {
        "ok": bool(outcome.get("ok", True)),
        "status": _int(outcome.get("status")),
        "retries": _int(outcome.get("retries")),
        "error": _name(outcome.get("error"))[:40],
    }
    return made


# ===== 2. Running figures =====


def key_of(obj: Mapping[str, Any]) -> str:
    return f"{obj.get('kind')}:{obj.get('name')}"


def _keys(call: Call) -> list[str]:
    """Each figure a call counts in: its object's, and its connection's when the object is a table."""
    keys = [key_of(call["object"])]
    if call["object"].get("kind") == "table" and call["connection"]:
        keys.append(key_of({"kind": "connection", "name": call["connection"]}))
    return keys


def _kept(values: list[Any], value: Any) -> list[Any]:
    return [*values, value][-KEPT_SAMPLES:]


def fold(figures: Figures, call: Call) -> None:
    """A call added to its object's running figures (and its connection's)."""
    for key in _keys(call):
        one = figures.setdefault(
            key, {"count": 0, "errors": 0, "ms": [], "wait": [], "rows": [], "bytes": [], "pages": []}
        )
        one["count"] += 1
        one["errors"] += 0 if call["outcome"]["ok"] else 1
        one["ms"] = _kept(one["ms"], call["ms"]["total"] or 0.0)
        one["wait"] = _kept(one["wait"], call["ms"]["wait"] or 0.0)
        for size in ("rows", "bytes", "pages"):
            one[size] = _kept(one[size], call["size"][size])
        one["last"] = call["at"]


def _centile(values: Sequence[float], share: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(share * len(ordered)))], 1)


def figure(one: Mapping[str, Any]) -> dict[str, Any]:
    """An object's figures as said: count, p50 and p95 (ms), the error rate, the typical rows, bytes and pages
    (medians of the last calls), the 95th percentile of the wait in line, the last call's time."""
    count = int(one.get("count") or 0)
    times = [float(t) for t in one.get("ms") or []]
    return {
        "count": count,
        "errors": int(one.get("errors") or 0),
        "error_rate": round(int(one.get("errors") or 0) / count, 4) if count else 0.0,
        "p50": _centile(times, 0.5),
        "p95": _centile(times, 0.95),
        "wait_p95": _centile([float(t) for t in one.get("wait") or []], 0.95),
        "rows": int(statistics.median(one["rows"])) if one.get("rows") else 0,
        "bytes": int(statistics.median(one["bytes"])) if one.get("bytes") else 0,
        "pages": int(statistics.median(one["pages"])) if one.get("pages") else 0,
        "last": one.get("last") or "",
    }


# ===== 3. The kept file =====


def text(figures: Figures) -> str:
    """.sab/stats.json's text: sorted, one figure a block, the same bytes for the same figures."""
    return json.dumps({"format": FORMAT, "figures": figures}, sort_keys=True, indent=1) + "\n"


def read(said: str) -> Figures:
    """The kept figures (nothing for a file that is not one, or of another format)."""
    try:
        loaded = json.loads(said)
    except ValueError:
        return {}
    if (
        not isinstance(loaded, dict)
        or loaded.get("format") != FORMAT
        or not isinstance(loaded.get("figures"), dict)
    ):
        return {}
    return {str(k): dict(v) for k, v in loaded["figures"].items() if isinstance(v, dict)}


# ===== 4. Hints =====


def _by(call: Call) -> str:
    """Who and where in words: a widget on its page, a notebook's cell, an endpoint, else who."""
    where = call.get("where") or {}
    if where.get("widget"):
        return f"The widget {where['widget']}" + (f" on {where['page']}" if where.get("page") else "")
    if where.get("notebook") or where.get("script"):
        cell = f" (cell {where['cell']})" if where.get("cell") is not None else ""
        return f"{where.get('notebook') or where.get('script')}{cell}"
    if where.get("endpoint"):
        return f"The endpoint {where['endpoint']}"
    return {"agent": "The agent", "background": "A background load"}.get(call.get("who") or "", "A read")


def _filter_hint(call: Call) -> dict[str, Any] | None:
    size, after = call["size"], set(call["by_duckdb"])
    if call["call"] != "read" or size["rows"] < MILLIONS:
        return None
    whole = size["asked"] == 0 and size["columns"] > 3
    if not whole and "filters" not in after:
        return None
    columns = f" and all {size['columns']} columns" if whole else ""
    later = ", its filters done in DuckDB after the read" if "filters" in after else ""
    words = (
        f"{_by(call)} read {size['rows']:,} rows{columns} of {call['object']['name']}{later}: name the "
        "columns it uses and filter at the source."
    )
    return {"kind": "filter_at_source", "object": call["object"], "words": words}


def _pages_hint(call: Call) -> dict[str, Any] | None:
    if call["call"] != "api" or call["size"]["pages"] < MANY_PAGES:
        return None
    words = (
        f"{call['object']['name']} was paged {call['size']['pages']} pages in one call: ask for larger pages "
        "(its page size input)."
    )
    return {"kind": "larger_pages", "object": call["object"], "words": words}


def _same_reads(calls: Sequence[Call]) -> list[dict[str, Any]]:
    seen = Counter(
        (key_of(c["object"]), c["fingerprint"], c["size"]["rows"])
        for c in calls
        if c["call"] == "read" and c["fingerprint"] and c["outcome"]["ok"]
    )
    out = []
    for (key, _, _), count in seen.items():
        if count >= SAME_READS:
            kind, _, name = key.partition(":")
            words = (
                f"{name} was read {count} times with the same shape and rows: keep it as a table (one read, "
                "then DuckDB SQL over it)."
            )
            out.append({"kind": "keep_as_table", "object": {"kind": kind, "name": name}, "words": words})
    return out


def _figure_hints(figures: Figures) -> list[dict[str, Any]]:
    out = []
    for key, one in sorted(figures.items()):
        kind, _, name = key.partition(":")
        said = figure(one)
        if kind == "connection" and said["count"] >= 3 and said["wait_p95"] >= SLOW_LINE_MS:
            words = (
                f"Calls on {name} waited up to {said['wait_p95'] / 1000:.1f} s for a slot: raise its queries "
                "at once, or run the background loads later."
            )
            out.append({"kind": "slow_line", "object": {"kind": kind, "name": name}, "words": words})
        if said["count"] >= 5 and said["error_rate"] >= FAILING_RATE:
            words = f"{name} failed {said['errors']} of its {said['count']} calls: see stats errors."
            out.append({"kind": "failing", "object": {"kind": kind, "name": name}, "words": words})
    return out


def hints(calls: Sequence[Call], figures: Figures | None = None) -> list[dict[str, Any]]:
    """What to change, in plain words, each once: from this session's calls and the running figures."""
    found: list[dict[str, Any]] = []
    for call in calls:
        found += [h for h in (_filter_hint(call), _pages_hint(call)) if h is not None]
    found += _same_reads(calls) + _figure_hints(figures or {})
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for hint in found:
        unique.setdefault((hint["kind"], key_of(hint["object"])), hint)
    return list(unique.values())


# ===== 5. The agent's views =====


def _of(calls: Iterable[Call], kind: str, name: str) -> list[Call]:
    wanted = name.casefold()
    if kind == "connection":
        return [c for c in calls if c["connection"].casefold() == wanted]
    return [
        c
        for c in calls
        if c["object"].get("kind") == kind and str(c["object"].get("name")).casefold() == wanted
    ]


def _figure_of(figures: Figures, kind: str, name: str) -> dict[str, Any] | None:
    wanted = f"{kind}:{name}".casefold()
    found = next((v for k, v in figures.items() if k.casefold() == wanted), None)
    return figure(found) if found is not None else None


def view(calls: Sequence[Call], figures: Figures, action: str, name: str = "", n: int = 20) -> dict[str, Any]:
    """The agent's stats(action): summary, slowest, errors, a table, connection or endpoint (name), hints."""
    if action not in VIEWS:
        raise StatsError(f"stats' action is one of {', '.join(VIEWS)}.")
    most = max(1, min(int(n or 20), 500))
    newest = list(reversed(calls))
    if action == "slowest":
        return {"calls": sorted(calls, key=lambda c: -(c["ms"]["total"] or 0.0))[:most]}
    if action == "errors":
        return {"calls": [c for c in newest if not c["outcome"]["ok"]][:most]}
    if action == "hints":
        return {"hints": hints(calls, figures)}
    if action in OBJECTS:
        if not name:
            raise StatsError(f"Name the {action}: stats {action} <name>.")
        return {
            "object": {"kind": action, "name": name},
            "figures": _figure_of(figures, action, name),
            "calls": _of(newest, action, name)[:most],
        }
    busiest = sorted(figures.items(), key=lambda kv: -int(kv[1].get("count") or 0))[:10]
    return {
        "calls": len(calls),
        "errors": sum(1 for c in calls if not c["outcome"]["ok"]),
        "since": calls[0]["at"] if calls else "",
        "busiest": [{"object": k, **figure(v)} for k, v in busiest],
        "hints": len(hints(calls, figures)),
    }
