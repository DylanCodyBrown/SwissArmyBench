"""A table's column facts and the one checker (design principle 8.13): what a column is, whether it fits a
slot of an analysis's contract, and why not, in plain words.

The facts are counted in one DuckDB pass over the table's view (types, filled and different values, ranges,
what text reads as numbers or dates), then the few-valued columns' values and every column's first values.
check_column is the rule the form, the chips, the column-first buttons, Check this table, the agent's
analyze_check and sab.analyze all share (domain/analyze.py plans a form with it; domain/analysis_fixes.py
proposes the fixes). Standard library only; no I/O.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain.analysis import is_identifier
from swissarmybench.domain.analysis_contracts import Check, Slot
from swissarmybench.domain.datasets import quote
from swissarmybench.domain.steps import type_family

# ===== a table's column facts =====

VALUES_KEPT = 12  # a column with at most this many different values has them all listed, with counts
SAMPLE_VALUES = 3
FACT_PARTS = 13  # facts_query's numbers per column


@dataclass(frozen=True)
class Facts:
    """One column as the checker sees it (counted once over the table's view)."""

    name: str
    type: str
    filled: int = 0
    distinct: int = 0
    low: float | None = None  # numbers: lowest; dates: the earliest, as days since 1970
    high: float | None = None
    low_positive: float | None = None  # numbers: the lowest above zero (what Benford reads)
    nonpositive: int = 0  # numbers: values at or below zero
    whole: bool = False  # numbers: every value a whole number
    numbers: int = 0  # text: values that read as numbers ("1,240.50", "$12")
    dates: tuple[int, int, int] = (0, 0, 0)  # text: values that read as dates (ISO, month/day, day/month)
    days: int = 0  # dates: different days
    months: int = 0  # dates: different months
    sample: tuple[str, ...] = ()
    values: tuple[tuple[str, int], ...] = ()  # every different value with its rows, when few (VALUES_KEPT)
    identifier: bool = False
    predicted: bool = False  # what a fix would make: its ranges are not known until it is applied

    @property
    def family(self) -> str:
        return type_family(self.type)

    @property
    def word(self) -> str:
        return type_word(self.type)

    @property
    def dated(self) -> bool:
        return self.family in ("date", "timestamp")


def type_word(duckdb_type: str) -> str:
    """A type as a word a person reads: number, date, date and time, text, yes/no, list..."""
    family = type_family(duckdb_type)
    words = {
        "number": "number",
        "date": "date",
        "timestamp": "date and time",
        "boolean": "yes/no",
        "text": "text",
    }
    if family in words:
        return words[family]
    upper = duckdb_type.upper()
    if upper.endswith("[]") or upper.startswith("LIST"):
        return "list"
    if upper.startswith(("STRUCT", "MAP")):
        return "record"
    if upper.startswith("TIME"):
        return "time of day"
    return "other"


def number_sql(column: str) -> str:
    """A text column read as a number: spaces, thousands' commas and a currency sign dropped; anything
    else (and nan, inf) is blank. The facts count with it and the fix's step uses it: one reading."""
    c = f"CAST({quote(column)} AS VARCHAR)"
    cleaned = (
        f"replace(replace(replace(replace(replace(trim({c}), ',', ''), '$', ''), '€', ''), '£', ''), ' ', '')"
    )
    x = f"TRY_CAST({cleaned} AS DOUBLE)"
    return f"CASE WHEN isfinite({x}) THEN {x} END"


DATE_FORMATS: tuple[tuple[str, str, str], ...] = (
    ("iso", "year-month-day", ""),
    ("mdy", "month/day/year", "%m/%d/%Y"),
    ("dmy", "day/month/year", "%d/%m/%Y"),
)


def date_sql(column: str, style: str) -> str:
    """A text column read as a date in one style (never guessed row by row: one style for the column)."""
    c = f"trim(CAST({quote(column)} AS VARCHAR))"
    if style == "iso":
        return f"CAST(TRY_CAST({c} AS TIMESTAMP) AS DATE)"
    pattern = next(p for key, _, p in DATE_FORMATS if key == style)
    return f"CAST(try_strptime({c}, '{pattern}') AS DATE)"


def facts_query(relation: str, columns: list[tuple[str, str]]) -> str:
    """Rows, then FACT_PARTS numbers for each (name, type), in one pass: filled, different, lowest,
    highest, lowest above zero, at or below zero, every value whole, text that reads as a number, as a date
    (three styles), different days and months. A date's range is in days since 1970."""
    parts = ["count(*)"]
    nothing = ["NULL"] * (FACT_PARTS - 2)
    for name, kind in columns:
        c = quote(name)
        family = type_family(kind)
        parts += [f"count({c})", f"count(DISTINCT {c})"]
        if family == "number":
            x = f"CAST({c} AS DOUBLE)"
            ok = f"isfinite({x})"
            parts += [
                f"min({x}) FILTER (WHERE {ok})",
                f"max({x}) FILTER (WHERE {ok})",
                f"min({x}) FILTER (WHERE {ok} AND {x} > 0)",
                f"count(*) FILTER (WHERE {ok} AND {x} <= 0)",
                f"coalesce(bool_and({x} = floor({x})) FILTER (WHERE {ok}), FALSE)",
                *["NULL"] * 6,
            ]
        elif family in ("date", "timestamp"):
            d = f"CAST({c} AS DATE)"
            parts += [
                f"min({d}) - DATE '1970-01-01'",
                f"max({d}) - DATE '1970-01-01'",
                *["NULL"] * 7,
                f"count(DISTINCT {d})",
                f"count(DISTINCT date_trunc('month', {d}))",
            ]
        elif family == "text":
            parts += [
                *["NULL"] * 5,
                f"count({number_sql(name)})",
                *[f"count({date_sql(name, style)})" for style, _, _ in DATE_FORMATS],
                "NULL",
                "NULL",
            ]
        else:
            parts += nothing
    return f"SELECT {', '.join(parts)} FROM {relation}"


def values_query(relation: str, columns: list[str]) -> str:
    """Each named column's different values with their rows, most common first (for the few-valued
    columns: a yes/no's two values, a status's handful): rows of (column's place, value, rows)."""
    selects = [
        f"SELECT {i} AS i, CAST({quote(name)} AS VARCHAR) AS v, count(*) AS n FROM {relation} "
        f"WHERE {quote(name)} IS NOT NULL GROUP BY 2"
        for i, name in enumerate(columns)
    ]
    return f"SELECT i, v, n FROM ({' UNION ALL '.join(selects)}) ORDER BY i, n DESC, v"


def sample_query(relation: str, columns: list[str]) -> str:
    """A few different values of each column, in the order the view's first rows show them: the tiny
    preview beside a column's name. Rows of (column's place, value)."""
    first = f"(SELECT *, row_number() OVER () AS __r FROM (SELECT * FROM {relation} LIMIT 500))"
    selects = [
        f"(SELECT {i} AS i, CAST({quote(name)} AS VARCHAR) AS v, min(__r) AS r FROM {first} "
        f"WHERE {quote(name)} IS NOT NULL GROUP BY 2 ORDER BY r LIMIT {SAMPLE_VALUES})"
        for i, name in enumerate(columns)
    ]
    return f"SELECT i, v FROM ({' UNION ALL '.join(selects)}) ORDER BY i, r"


def read_facts(
    columns: list[tuple[str, str]],
    row: tuple[Any, ...] | None,
    samples: dict[str, list[str]] | None = None,
    values: dict[str, list[tuple[str, int]]] | None = None,
) -> tuple[int, list[Facts]]:
    """facts_query's one row (with each column's sample and few values) as (rows, Facts per column)."""
    rows = int(row[0] or 0) if row else 0
    samples = samples or {}
    values = values or {}
    out: list[Facts] = []

    def number(v: Any) -> float | None:
        return None if v is None else float(v)

    for i, (name, kind) in enumerate(columns):
        got = tuple(row[1 + FACT_PARTS * i : 1 + FACT_PARTS * (i + 1)]) if row else (None,) * FACT_PARTS
        filled, distinct = int(got[0] or 0), int(got[1] or 0)
        out.append(
            Facts(
                name=name,
                type=kind,
                filled=filled,
                distinct=distinct,
                low=number(got[2]),
                high=number(got[3]),
                low_positive=number(got[4]),
                nonpositive=int(got[5] or 0),
                whole=bool(got[6]),
                numbers=int(got[7] or 0),
                dates=(int(got[8] or 0), int(got[9] or 0), int(got[10] or 0)),
                days=int(got[11] or 0),
                months=int(got[12] or 0),
                sample=tuple(samples.get(name, ())[:SAMPLE_VALUES]),
                values=tuple(values.get(name, ())[:VALUES_KEPT]),
                identifier=is_identifier(name, kind, filled, distinct),
            )
        )
    return rows, out


# ===== which columns fit a slot =====

NEEDS: dict[str, str] = {
    "number": "a number column",
    "whole": "a whole-number column",
    "date": "a date column",
    "category": "a text column whose values repeat",
    "yesno": "a yes/no column (two values)",
}


def kinds_of(f: Facts) -> frozenset[str]:
    """The contract kinds a column is (C.KINDS): a whole-number column is both number and whole; any
    column with exactly two values is yes/no."""
    kinds: set[str] = set()
    if f.dated:
        return frozenset({"date"})
    if f.family == "number":
        kinds.add("number")
        if f.whole or _integer_type(f.type):
            kinds.add("whole")
    if f.family in ("text", "boolean"):
        kinds.add("category")
    if f.family == "boolean" or (f.distinct == 2 and f.family in ("text", "number")):
        kinds.add("yesno")
    return frozenset(kinds)


def _integer_type(duckdb_type: str) -> bool:
    return duckdb_type.upper().lstrip("U") in ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT")


def needs_words(slot: Slot) -> str:
    """What a slot takes, by its kinds: "a number column or a yes/no column (two values)"."""
    return " or ".join(NEEDS[k] for k in slot.accepts if k in NEEDS) or "a column"


@dataclass(frozen=True)
class Fit:
    fits: bool
    why: str = ""  # when it does not: the reason, in plain words
    cautions: tuple[str, ...] = ()  # "should" checks that failed: it is offered, the caution said


def spans(f: Facts, orders: float) -> bool:
    """Do a number column's values above zero span `orders` orders of magnitude (Benford's range)?"""
    if f.family != "number" or not f.low_positive or not f.high or f.high <= 0:
        return False
    return math.log10(f.high / f.low_positive) >= orders


def failed(check: Check, f: Facts, rows: int) -> str | None:
    """Why column `f` fails `check`, or None when it passes. A predicted column (what a fix would make)
    passes the checks on ranges it cannot know yet."""
    n = check.n or 0
    if check.check == "not_identifier":
        return f"every row has a different {f.name}: an identifier tells nothing" if f.identifier else None
    if check.check == "distinct_min":
        if f.distinct >= n:
            return None
        return f"{f.name} has only one value" if f.distinct == 1 else f"{f.name} has no values"
    if check.check == "distinct_max":
        if f.distinct <= n:
            return None
        return f"{f.name} has {f.distinct:,} different values (at most {int(n):,})"
    if check.check == "two_values":
        return None if f.distinct == 2 else f"{f.name} has {f.distinct:,} different values, not two"
    if f.predicted:
        return None
    if check.check == "some_positive":
        return None if f.low_positive is not None else f"{f.name} has no values above zero"
    if check.check == "spans_orders":
        if spans(f, n):
            return None
        return f"{f.name} stays within a narrow range: Benford's law needs values from 10s to 1,000s"
    if check.check == "all_positive":
        if not f.nonpositive:
            return None
        return f"{f.nonpositive:,} of {f.name}'s values are zero or negative (left out)"
    if check.check == "filled_share":
        blank = rows - f.filled
        if rows <= 0 or 100 * blank / rows <= (check.blank or 0):
            return None
        return f"{round(100 * blank / rows)}% of {f.name} is blank (left out)"
    if check.check == "periods_min":
        if f.days >= n:
            return None
        return f"{f.name} has dates on only {f.days:,} day{'' if f.days == 1 else 's'} (at least {int(n)})"
    return None


def check_column(slot: Slot, f: Facts, rows: int) -> Fit:
    """Does column `f` fit `slot`? Its kind first, then every "must" check; "should" checks that fail
    are cautions. The one rule the form, the chips, the buttons and the agent share."""
    if not kinds_of(f) & set(slot.accepts):
        return Fit(False, f"{f.name} is {_a(f.word)} column: {slot.label.lower()} needs {needs_words(slot)}")
    if f.filled == 0:
        return Fit(False, f"{f.name} is all blank")
    cautions: list[str] = []
    for check in slot.checks:
        said = failed(check, f, rows)
        if said is None:
            continue
        if check.level == "must":
            return Fit(False, said)
        cautions.append(said)
    return Fit(True, "", tuple(cautions))


def _a(word: str) -> str:
    return f"{'an' if word[:1] in 'aeiou' else 'a'} {word}"


def fits(slot: Slot, f: Facts, rows: int) -> bool:
    return check_column(slot, f, rows).fits


def words_of(name: str) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return [w.lower() for w in re.split(r"[^A-Za-z0-9]+", spaced) if w]


def name_score(slot: Slot, name: str) -> int:
    """How much a column's name says it is what the slot wants: the earlier its word in the slot's
    hints, the higher; 0 when no word matches."""
    words = words_of(name)
    for rank_, word in enumerate(slot.hints):
        if word in words:
            return len(slot.hints) - rank_
    return 0


def likeliest(slot: Slot, fitting: list[Facts]) -> tuple[Facts | None, str]:
    """(the pick, why in words) among the columns that fit a slot: the only one, else the likeliest by
    its name, else the first in the table's order (a column of the slot's first kind before another)."""
    if not fitting:
        return None, ""
    what = _plain(slot)
    if len(fitting) == 1:
        return fitting[0], f"the only {what}"

    def rank_(f: Facts) -> tuple[int, int, int]:
        first_kind = 1 if slot.accepts[0] in kinds_of(f) else 0
        return (name_score(slot, f.name), first_kind, -fitting.index(f))

    best = max(fitting, key=rank_)
    if name_score(slot, best.name):
        return best, "the likeliest, by its name"
    return best, f"the first {what}"


def _plain(slot: Slot) -> str:
    """A slot's kind as the chip's reason says it: "number column", "column that fits"."""
    if len(slot.accepts) == 1 and slot.accepts[0] in NEEDS:
        return NEEDS[slot.accepts[0]].split(" ", 1)[1].split(" (")[0]
    return "column that fits"


def rows_words(n: int) -> str:
    return f"{n:,} row{'s' if n != 1 else ''}"


YES_WORDS = ("true", "yes", "y", "1", "late", "won", "fraud", "churned", "returned", "approved", "success")
NO_WORDS = ("false", "no", "n", "0")
