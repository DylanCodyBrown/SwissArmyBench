"""The Analyze page's rules (the owner, 2026-11-19: "make it stupid simple"; design principle 8.13).

One checker over one source: every analysis's data contract (domain/analysis_contracts.py). From a
table's column facts (counted in one pass: types, filled and different values, ranges, what text reads
as, a few values) this module says, for one analysis:

  what fits each slot           check_column: fits or not, and why, in plain words; cautions for a "should"
  which column is picked        the only one that fits ("the only date column"), else the likeliest by its
                                name (the slot's hints), else the first that fits
  what is missing               one sentence when nothing fits (the form offers Change table)
  how to make it fit            fixes: the grid's own steps (text read as numbers or dates, a month column,
                                the ten most common values and Other, blanks left out, values above zero, a
                                yes/no column, totals per month or per key), one sentence each with its count
  the sentence                  "Test whether amount follows Benford's first-digit law, on 12,400 rows of
                                orders."
  the request                   the body the analysis's own route takes (domain/analysis.py and friends)

And the two column-first ways in: the analyses a column fits (for_column), and the analyses ranked for a
table (rank: fits now, fits after N fixes, does not; a reason each). The form, the chips, the column-first
buttons, Check this table, the Data shape check, the agent's analyze_check and sab.analyze all read this.
Standard library only; no I/O.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import Any

from swissarmybench.domain import analysis_contracts as C
from swissarmybench.domain.analysis import is_identifier, wide_series
from swissarmybench.domain.analysis_contracts import Check, Contract, Slot
from swissarmybench.domain.datasets import quote
from swissarmybench.domain.steps import type_family


class AnalyzeError(ValueError):
    """An Analyze request that cannot be read or run: an unknown analysis, a column that does not fit."""


def contract(analysis_id: Any) -> Contract:
    try:
        return C.contract(analysis_id)
    except KeyError as error:
        raise AnalyzeError(str(error.args[0])) from error


def catalog() -> dict[str, Any]:
    """The toolbar as data: the groups in order, each analysis's question, name and tip."""
    return {
        "groups": list(C.GROUPS),
        "analyses": [
            {
                "id": c.id,
                "group": c.group,
                "label": c.label,
                "name": c.name,
                "get": c.get,
                "two_tables": c.two_tables,
            }
            for c in C.CONTRACTS
        ],
    }


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


def _failed(check: Check, f: Facts, rows: int) -> str | None:
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
        said = _failed(check, f, rows)
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


def _words(name: str) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return [w.lower() for w in re.split(r"[^A-Za-z0-9]+", spaced) if w]


def name_score(slot: Slot, name: str) -> int:
    """How much a column's name says it is what the slot wants: the earlier its word in the slot's
    hints, the higher; 0 when no word matches."""
    words = _words(name)
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


# ===== a form, planned =====


@dataclass
class Plan:
    contract: Contract
    rows: int
    table: str
    slots: list[dict[str, Any]] = field(default_factory=list)
    options: list[dict[str, Any]] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)
    chosen: dict[str, Any] = field(default_factory=dict)  # option values in force
    missing: str | None = None
    cautions: list[str] = field(default_factory=list)
    gone: list[str] = field(default_factory=list)  # columns asked for that the table no longer has
    refused: list[str] = field(default_factory=list)  # columns asked for that do not fit, with why
    fixes: list[Fix] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.missing is None

    def to_json(self) -> dict[str, Any]:
        c = self.contract
        return {
            "analysis": c.id,
            "label": c.label,
            "name": c.name,
            "get": c.get,
            "rows": self.rows,
            "table": self.table,
            "slots": self.slots,
            "options": self.options,
            "columns": self.values,
            "settings": self.chosen,
            "missing": self.missing,
            "ready": self.ready,
            "cautions": self.cautions,
            "gone": self.gone,
            "refused": self.refused,
            "fixes": [f.to_json() for f in self.fixes],
            "sentence": sentence(self) if self.ready else None,
        }


def _offer(f: Facts, fit: Fit) -> dict[str, Any]:
    return {"name": f.name, "type": f.word, "preview": list(f.sample), "cautions": list(fit.cautions)}


def _rows(n: int) -> str:
    return f"{n:,} row{'s' if n != 1 else ''}"


def plan(
    analysis_id: Any,
    table: str,
    rows: int,
    facts: list[Facts],
    given: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    tables: list[dict[str, Any]] | None = None,
) -> Plan:
    """The form for one analysis on a table: each slot's fitting columns (and the ones that do not fit,
    with why), its pick (what was given, when it fits; else the obvious one), the options with their
    values, what is missing in one sentence, and the fixes that would make the table fit.

    `given`: {slot: column or [columns]} (the user's chips, remembered or from Run again; "" leaves an
    optional slot empty); `settings`: {option: value}; `tables`: the other open tables [{"grid",
    "label"}] for a two-table slot."""
    c = contract(analysis_id)
    given = dict(given or {})
    settings = dict(settings or {})
    out = Plan(c, rows, table)
    taken: set[str] = set()
    by_name = {f.name: f for f in facts}
    if rows < c.table.rows_min:
        least = f"at least {_rows(c.table.rows_min)}"
        out.missing = (
            f"{table} has no rows: {c.label.rstrip('?…')} needs {least}."
            if rows == 0
            else f"{table} has only {_rows(rows)}: {c.label.rstrip('?…')} needs {least}."
        )
    elif rows < c.table.rows_should:
        out.cautions.append(
            f"Only {_rows(rows)}: the result will be rough ({c.table.rows_should:,} is better)."
        )

    def lost(name: Any, slot: Slot) -> bool:
        """A column that was asked for and cannot be used: noted, so a run refuses and a form says so."""
        if not isinstance(name, str) or not name:
            return False
        if name not in by_name:
            out.gone.append(name)
            return True
        fit = check_column(slot, by_name[name], rows)
        if not fit.fits:
            out.refused.append(fit.why)
            return True
        return False

    for slot in c.slots:
        entry: dict[str, Any] = {
            "key": slot.key,
            "label": slot.label,
            "words": slot.words,
            "optional": slot.optional,
            "many": slot.many,
            "table": slot.table,
        }
        if slot.table:
            others = tables or []
            pick = given.get(slot.key)
            if pick not in {t["grid"] for t in others}:
                pick = None if slot.optional else (others[0]["grid"] if others else None)
            said = ""
            if pick is not None and given.get(slot.key) != pick:
                said = "the only other open table" if len(others) == 1 else "the first other open table"
            entry |= {
                "offered": [{"name": t["grid"], "type": "table", "preview": [t["label"]]} for t in others],
                "rejected": [],
                "value": pick,
                "said": said,
            }
            if pick is None and not slot.optional:
                out.missing = out.missing or f"{c.label.rstrip('?…')} needs a second open table."
            out.slots.append(entry)
            out.values[slot.key] = pick
            continue
        checked = [(f, check_column(slot, f, rows)) for f in facts]
        fitting = [f for f, fit in checked if fit.fits]
        entry |= {
            "offered": [_offer(f, fit) for f, fit in checked if fit.fits],
            "rejected": [
                {"name": f.name, "type": f.word, "why": fit.why} for f, fit in checked if not fit.fits
            ],
        }
        wanted = given.get(slot.key)
        if slot.many:
            if isinstance(wanted, str):
                wanted = [wanted] if wanted else []
            if isinstance(wanted, list) and wanted:
                value = [n for n in wanted if not lost(n, slot) and isinstance(n, str) and n not in taken]
                said = ""
            elif slot.optional:
                value, said = [], "every other column"
            else:
                value = [f.name for f in fitting if f.name not in taken]
                said = "every column that fits"
            entry |= {"value": value, "said": said}
            if not value and not slot.optional:
                besides = f" besides {', '.join(sorted(taken))}" if taken else ""
                out.missing = out.missing or (
                    f"Nothing in {table} fits {slot.label.lower()}{besides}: it needs {slot.words}."
                )
            out.values[slot.key] = value
            out.slots.append(entry)
            continue
        pool = [f for f in fitting if f.name not in taken]
        pick_f: Facts | None = None
        said = ""
        if isinstance(wanted, str) and wanted and not lost(wanted, slot):
            pick_f = by_name[wanted]
        elif wanted == "" and slot.optional:
            pick_f = None
        elif slot.optional:
            # An optional slot is filled only when a column is clearly named for it (an outcome's name).
            named = [f for f in pool if name_score(slot, f.name)]
            if named:
                pick_f, said = likeliest(slot, named)
        else:
            pick_f, said = likeliest(slot, pool)
        if pick_f is None and not slot.optional:
            out.missing = out.missing or (
                f"Nothing in {table} fits {slot.label.lower()}: it needs {slot.words}."
            )
        if pick_f is not None:
            taken.add(pick_f.name)
            entry["cautions"] = list(check_column(slot, pick_f, rows).cautions)
        entry |= {"value": pick_f.name if pick_f else None, "said": said}
        out.values[slot.key] = pick_f.name if pick_f else None
        out.slots.append(entry)
    _options(out, settings, facts, by_name, taken, tables or [])
    out.fixes = fixes(out, facts)
    return out


def _options(
    out: Plan,
    settings: dict[str, Any],
    facts: list[Facts],
    by_name: dict[str, Facts],
    taken: set[str],
    tables: list[dict[str, Any]],
) -> None:
    c = out.contract
    group_slot = Slot("by", "By", "", ("category", "whole", "yesno"), checks=(C.NOT_ID, C.TWO, C.FEW))
    for opt in c.options:
        value = settings.get(opt.key, opt.default)
        choices = [list(pair) for pair in opt.choices]
        if opt.type == "table":
            choices += [[t["grid"], t["label"]] for t in tables]
        if opt.type == "column":
            choices += [
                [f.name, f.name] for f in facts if fits(group_slot, f, out.rows) and f.name not in taken
            ]
        if choices and str(value) not in {str(choice[0]) for choice in choices}:
            value = opt.default
        if opt.type == "number" and value not in ("", None) and _number(value) is None:
            value = opt.default
        if opt.key == "yes":
            if not _needs_yes(c, out.values, by_name):
                continue
            target = _target_facts(c, out.values, by_name)
            known = [v for v, _ in target.values] if target else []
            choices = [[v, v] for v in known]
            if not value or (known and str(value) not in known):
                value = yes_default(target)
        out.options.append(
            {
                "key": opt.key,
                "label": opt.label,
                "meaning": opt.meaning,
                "value": value,
                "default": opt.default,
                "choices": choices,
                "type": "choice" if choices else opt.type,
            }
        )
        out.chosen[opt.key] = value
    if c.id == "whatif" and out.ready:
        for name in out.values.get("predictors") or []:
            f = by_name[name]
            key = f"value:{name}"
            known = [v for v, _ in f.values] or list(f.sample)
            value = settings.get(key, _typical(f))
            numeric = f.family == "number"
            if (numeric and _number(value) is None) or (not numeric and known and str(value) not in known):
                value = _typical(f)
            out.options.append(
                {
                    "key": key,
                    "label": name,
                    "meaning": f"The {name} to try (it starts at a typical value).",
                    "value": value,
                    "default": _typical(f),
                    "choices": [] if numeric else [[v, v] for v in known],
                    "type": "number" if numeric else "choice",
                    "what_if": True,
                }
            )
            out.chosen[key] = value


def _target_facts(c: Contract, values: dict[str, Any], by_name: dict[str, Facts]) -> Facts | None:
    name = values.get("outcome" if c.id == "odds" else "target")
    return by_name.get(name) if isinstance(name, str) else None


def _needs_yes(c: Contract, values: dict[str, Any], by_name: dict[str, Facts]) -> bool:
    f = _target_facts(c, values, by_name)
    if f is None:
        return False
    return c.id == "odds" or f.family != "number"


YES_WORDS = ("true", "yes", "y", "1", "late", "won", "fraud", "churned", "returned", "approved", "success")
NO_WORDS = ("false", "no", "n", "0")


def yes_default(f: Facts | None) -> str:
    """Which of a yes/no column's values counts as yes: a word that says yes, else the rarer value."""
    if f is None:
        return ""
    known = [v for v, _ in f.values] or list(f.sample)
    for v in known:
        if v.strip().lower() in YES_WORDS:
            return v
    for v in known:
        if v.strip().lower() not in NO_WORDS:
            return v
    return known[-1] if known else ""


def _typical(f: Facts) -> Any:
    if f.family == "number" and f.low is not None and f.high is not None:
        mid = (f.low + f.high) / 2
        return round(mid, 2) if not mid.is_integer() else int(mid)
    if f.values:
        return f.values[0][0]
    return f.sample[0] if f.sample else ""


def period_for(span_days: float | None) -> str:
    """A date column's period when the form says "Picked from the dates": a few dozen points or more."""
    if span_days is None:
        return "month"
    if span_days <= 92:
        return "day"
    if span_days <= 548:
        return "week"
    if span_days <= 15 * 366:
        return "month"
    return "year"


# ===== the sentence of what will run =====


def sentence(p: Plan) -> str:
    """One short sentence of what will run, in the form's own words."""
    v, o, c = p.values, p.chosen, p.contract
    on = f"on {_rows(p.rows)} of {p.table}"
    if c.id == "profile":
        return f"Describe every column of {p.table} ({_rows(p.rows)})."
    if c.id == "check":
        return f"Check how {p.table} is shaped and which analyses suit it ({_rows(p.rows)})."
    if c.id == "benford":
        which = "first-digit" if str(o.get("digits", "1")) == "1" else "first-two-digits"
        return f"Test whether {v['column']} follows Benford's {which} law, {on}."
    if c.id == "fit":
        against = "as common as in the other table" if o.get("reference") else "equally common"
        return f"Test whether each {v['column']} is {against}, {on}."
    if c.id == "together":
        return f"Test whether {v['first']} and {v['second']} go together, {on}."
    if c.id == "outliers":
        within = f" within each {o['by']}" if o.get("by") else ""
        return f"Find the unusual values of {v['column']}{within}, {on}."
    if c.id == "odds":
        if v.get("outcome"):
            return f"Count the odds of {v['outcome']} = {o.get('yes') or '?'} for each {v['column']}, {on}."
        return f"Count how often each {v['column']} shows up, {on}."
    if c.id == "predictors":
        pool = v.get("candidates") or []
        among = f"among {', '.join(pool)}" if pool else "among every other column"
        return f"Rank what explains {v['target']} {among}, {on}."
    if c.id in ("regression", "whatif"):
        verb = "Predict" if c.id == "regression" else "Try a what-if for"
        return f"{verb} {v['target']} from {', '.join(v.get('predictors') or [])}, {on}."
    if c.id in ("time_series", "forecast"):
        metric = v.get("metric")
        total = o.get("total") or "sum"
        what = metric or "the rows"
        verb = "Count" if not metric or total == "count" else "Average" if total == "avg" else "Total"
        if c.id == "forecast":
            return f"Forecast {what} {o.get('horizon', 6)} periods ahead by {v['date']}, {on}."
        return f"{verb} {what} by {v['date']} and spot the trend and seasons, {on}."
    if c.id == "tie_out":
        return f"Tie out {p.table} against the other table, group by group."
    if c.id == "key_finder":
        other = "the other table" if v.get("other") else "every other open table"
        return f"Find the columns that join {p.table} to {other}."
    return f"Run {c.name} {on}."


# ===== the request each analysis's own route takes =====


def request(p: Plan, by_name: dict[str, Facts]) -> dict[str, Any]:
    """The body the analysis's route takes (see routes_analysis.py and friends), from a ready plan."""
    if p.missing is not None:
        raise AnalyzeError(p.missing)
    v, o, c = p.values, p.chosen, p.contract
    body: dict[str, Any]
    if c.id == "benford":
        return {
            "columns": [v["column"]],
            "expected": "benford" if str(o.get("digits", "1")) == "1" else "benford2",
        }
    if c.id == "fit":
        body = {"columns": [v["column"]], "expected": "even"}
        if o.get("reference"):
            body |= {"expected": "grid", "reference": {"grid": o["reference"], "column": v["column"]}}
        return body
    if c.id == "together":
        return {"columns": [v["first"], v["second"]], "expected": "together"}
    if c.id == "outliers":
        f = by_name[v["column"]]
        if f.family != "number":
            return {"column": v["column"], "look": "frequency"}
        body = {"column": v["column"], "look": "amount", "method": o.get("method") or "robust"}
        if o.get("by"):
            body["by"] = o["by"]
        return body
    if c.id == "odds":
        body = {"column": v["column"]}
        if _number(o.get("buckets")):
            body["buckets"] = int(_number(o["buckets"]) or 0)
        if v.get("outcome"):
            body["outcome"] = {"column": v["outcome"], "values": [str(o.get("yes") or "")]}
        return body
    if c.id == "predictors":
        body = {"target": v["target"]}
        if v.get("candidates"):
            body["candidates"] = list(v["candidates"])
        if _number(o.get("buckets")):
            body["buckets"] = int(_number(o["buckets"]) or 0)
        return body
    if c.id in ("regression", "whatif"):
        body = {"target": v["target"], "predictors": list(v.get("predictors") or [])}
        if "yes" in o:
            body["outcome"] = {"column": v["target"], "values": [str(o.get("yes") or "")]}
        return body
    if c.id in ("time_series", "forecast"):
        date = by_name[v["date"]]
        period = o.get("period") or "auto"
        if period == "auto":
            period = period_for(None if date.low is None or date.high is None else date.high - date.low)
        total = o.get("total") or "sum"
        if not v.get("metric"):
            total = "count"
        body = {"date": v["date"], "period": period, "total": total}
        if v.get("metric") and total != "count":
            body["metric"] = v["metric"]
        if c.id == "forecast":
            body["horizon"] = max(1, int(_number(o.get("horizon")) or 6))
        return body
    if c.id == "tie_out":
        body = {"other": v["other"]}
        if _number(o.get("tolerance")):
            body["tolerance"] = _number(o["tolerance"])
        return body
    if c.id == "key_finder":
        return {
            "target": v.get("other") or "*",
            "options": {"trim": True, "ignore_case": o.get("ignore_case") == "yes", "max_length": 128},
        }
    return {}


def what_if_values(p: Plan) -> dict[str, Any]:
    """The what-if row: each predictor's value from the form (value:<column>)."""
    out: dict[str, Any] = {}
    for name in p.values.get("predictors") or []:
        raw = p.chosen.get(f"value:{name}")
        number = _number(raw)
        out[name] = number if number is not None else raw
    return out


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


# ===== make it fit: fixes as the grid's own steps =====

TOP_N = 10
READS_SHARE = 0.5  # a text column is offered as numbers (or dates) when at least half its values read so
YES_VALUES = frozenset({"y", "yes", "true", "t", "1"})
NO_VALUES = frozenset({"n", "no", "false", "f", "0"})


@dataclass(frozen=True)
class Fix:
    """One way to make the table fit: grid steps (DuckDB over the user's table, undoable in the steps
    strip), one plain sentence with its count. Never applied by itself: the user's Apply, or the agent's
    steps commands."""

    kind: str  # C.FIXES
    column: str
    label: str  # the button's words: "Read amount as numbers"
    sentence: str
    steps: tuple[dict[str, Any], ...]
    slot: str = ""
    level: str = "needed"  # needed: the slot has nothing without it; better: it runs, this improves it
    count: int | None = None
    count_sql: str | None = None  # the count, when the facts do not hold it: one number over {relation}
    fills: str | None = None  # the column the slot takes once applied
    makes: Facts | None = None  # that column as the checker will see it (its ranges unknown)
    variant: str = ""

    @property
    def id(self) -> str:
        return ":".join(part for part in (self.kind, self.column, self.variant) if part)

    def counted(self, n: int) -> Fix:
        return replace(self, count=n, sentence=self.sentence.replace("{n}", f"{n:,}"), count_sql=None)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "level": self.level,
            "slot": self.slot,
            "column": self.column,
            "label": self.label,
            "sentence": self.sentence,
            "count": self.count,
            "steps": [dict(s) for s in self.steps],
            "fills": {self.slot: self.fills} if self.slot and self.fills else {},
        }


def _sql_step(sql: str) -> dict[str, Any]:
    return {"kind": "sql", "params": {"sql": sql}}


def _free(name: str, taken: set[str]) -> str:
    """A new column's name no column has (compared without case, as DuckDB does)."""
    lowered = {t.lower() for t in taken}
    if name.lower() not in lowered:
        return name
    n = 2
    while f"{name}_{n}".lower() in lowered:
        n += 1
    return f"{name}_{n}"


def fix_text_to_number(f: Facts, slot: str = "", level: str = "needed") -> Fix:
    lost = f.filled - f.numbers
    tail = f" ({lost:,} become blank)" if lost else ""
    return Fix(
        "text_to_number",
        f.name,
        f"Read {f.name} as numbers",
        f"Read {f.name} as numbers: {f.numbers:,} of {f.filled:,} values are numbers{tail}.",
        (_sql_step(f"SELECT * REPLACE ({number_sql(f.name)} AS {quote(f.name)}) FROM grid"),),
        slot,
        level,
        f.numbers,
        fills=f.name,
        makes=replace(
            f,
            type="DOUBLE",
            filled=f.numbers,
            distinct=min(f.distinct, f.numbers),
            identifier=is_identifier(f.name, "DOUBLE", f.numbers, min(f.distinct, f.numbers)),
            predicted=True,
            values=(),
        ),
    )


def fix_text_to_date(f: Facts, style: str, slot: str = "", level: str = "needed") -> Fix:
    at = [key for key, _, _ in DATE_FORMATS].index(style)
    reads = f.dates[at]
    words = DATE_FORMATS[at][1]
    lost = f.filled - reads
    tail = f" ({lost:,} become blank)" if lost else ""
    return Fix(
        "text_to_date",
        f.name,
        f"Read {f.name} as dates",
        f"Read {f.name} as dates ({words}): {reads:,} of {f.filled:,} values are dates{tail}.",
        (_sql_step(f"SELECT * REPLACE ({date_sql(f.name, style)} AS {quote(f.name)}) FROM grid"),),
        slot,
        level,
        reads,
        fills=f.name,
        makes=replace(
            f,
            type="DATE",
            identifier=False,
            filled=reads,
            distinct=min(f.distinct, reads),
            days=min(f.distinct, reads),
            months=min(f.distinct, reads),
            predicted=True,
            values=(),
        ),
        variant=style,
    )


def fix_period_column(f: Facts, names: set[str], slot: str = "", level: str = "needed") -> Fix:
    new = _free(f"{f.name}_month", names)
    expression = f"strftime(date_trunc('month', CAST({quote(f.name)} AS DATE)), '%Y-%m')"
    return Fix(
        "period_column",
        f.name,
        f"Group {f.name} by month",
        f"Group {f.name} by month into {new}: {f.months:,} month{'' if f.months == 1 else 's'}.",
        (_sql_step(f"SELECT *, {expression} AS {quote(new)} FROM grid"),),
        slot,
        level,
        f.months,
        fills=new,
        makes=Facts(new, "VARCHAR", f.filled, f.months, predicted=True),
    )


def fix_top_n(f: Facts, names: set[str], slot: str = "", level: str = "needed") -> Fix:
    new = _free(f"{f.name}_top", names)
    c = quote(f.name)
    top = f"SELECT {c} FROM grid WHERE {c} IS NOT NULL GROUP BY {c} ORDER BY count(*) DESC, {c} LIMIT {TOP_N}"
    expression = (
        f"CASE WHEN {c} IS NULL THEN NULL WHEN {c} IN ({top}) THEN CAST({c} AS VARCHAR) ELSE 'Other' END"
    )
    count_sql = (
        f"SELECT coalesce(sum(n), 0) FROM (SELECT count(*) AS n FROM {{relation}} WHERE {c} IS NOT NULL "
        f"GROUP BY {c} ORDER BY n DESC, {c} LIMIT {TOP_N})"
    )
    return Fix(
        "top_n_other",
        f.name,
        f"Keep the {TOP_N} most common {f.name}",
        f"Keep the {TOP_N} most common {f.name} in {new} and call the rest Other: "
        f"they cover {{n}} of {f.filled:,} rows.",
        (_sql_step(f"SELECT *, {expression} AS {quote(new)} FROM grid"),),
        slot,
        level,
        count_sql=count_sql,
        fills=new,
        makes=Facts(new, "VARCHAR", f.filled, TOP_N + 1, predicted=True),
    )


def fix_drop_blanks(f: Facts, rows: int, slot: str = "") -> Fix:
    blank = rows - f.filled
    return Fix(
        "drop_blanks",
        f.name,
        f"Leave out rows with no {f.name}",
        f"Leave out the {_rows(blank)} with no {f.name}.",
        ({"kind": "filter", "params": {"column": f.name, "op": "not_blank"}},),
        slot,
        "better",
        blank,
        fills=f.name,
    )


def fix_keep_positive(f: Facts, slot: str = "") -> Fix:
    return Fix(
        "keep_positive",
        f.name,
        f"Keep {f.name} above zero",
        f"Keep {f.name} above zero: leaves out {_rows(f.nonpositive)} at or below it.",
        ({"kind": "filter", "params": {"column": f.name, "op": "gt", "value": 0}},),
        slot,
        "better",
        f.nonpositive,
        fills=f.name,
    )


def yes_no_words(f: Facts) -> tuple[list[str], list[str]] | None:
    """(the values that say yes, the ones that say no) when every value of a text column is one of Y/N,
    yes/no, true/false, 1/0 in any case, and both sides are there, in more than two spellings."""
    if f.family != "text" or not f.values or len(f.values) != f.distinct or f.distinct <= 2:
        return None
    yes = [v for v, _ in f.values if v.strip().lower() in YES_VALUES]
    no = [v for v, _ in f.values if v.strip().lower() in NO_VALUES]
    if not yes or not no or len(yes) + len(no) != len(f.values):
        return None
    return yes, no


def fix_yes_no_words(f: Facts, names: set[str], slot: str = "", level: str = "needed") -> Fix | None:
    found = yes_no_words(f)
    if found is None:
        return None
    yes, no = found
    new = _free(f"{f.name}_yes_no", names)
    counted = sum(n for v, n in f.values if v in yes)
    step = {
        "kind": "categorize",
        "params": {
            "column": f.name,
            "as": new,
            "rules": [
                {"type": "in", "values": yes, "label": "yes"},
                {"type": "in", "values": no, "label": "no"},
            ],
            "unmatched": "no",
        },
    }
    return Fix(
        "yes_no",
        f.name,
        f"Make {f.name} a yes/no column",
        f"Make {new} from {f.name}: {', '.join(yes)} count as yes ({_rows(counted)}), {', '.join(no)} as no.",
        (step,),
        slot,
        level,
        counted,
        fills=new,
        makes=Facts(
            new, "VARCHAR", f.filled, 2, values=(("yes", counted), ("no", f.filled - counted)), predicted=True
        ),
        variant="words",
    )


def fix_yes_no_value(f: Facts, names: set[str], slot: str = "", level: str = "needed") -> Fix | None:
    """A yes/no column from one value of a text column with a handful of values: that value, or not."""
    if f.family != "text" or not 3 <= f.distinct <= VALUES_KEPT or len(f.values) != f.distinct:
        return None
    value = next((v for v, _ in f.values if v.strip().lower() in YES_WORDS), f.values[0][0])
    counted = dict(f.values)[value]
    part = "_".join(_words(value))[:30] or "value"
    new = _free(f"is_{part}", names)
    step = {
        "kind": "categorize",
        "params": {
            "column": f.name,
            "as": new,
            "rules": [{"type": "in", "values": [value], "label": "yes"}],
            "unmatched": "no",
        },
    }
    return Fix(
        "yes_no",
        f.name,
        f"Make a yes/no column: {f.name} is {value}",
        f"Make {new} from {f.name}: {value} is yes ({counted:,} of {_rows(f.filled)}), every other value no.",
        (step,),
        slot,
        level,
        counted,
        fills=new,
        makes=Facts(
            new, "VARCHAR", f.filled, 2, values=(("yes", counted), ("no", f.filled - counted)), predicted=True
        ),
        variant="value",
    )


def fix_group_by_period(date: Facts, number: Facts, names: set[str]) -> Fix:
    new = _free(f"{date.name}_month", names | {number.name})
    steps = (
        {"kind": "bucket", "params": {"column": date.name, "as": new, "mode": "date", "unit": "month"}},
        {
            "kind": "group_by",
            "params": {
                "keys": [new],
                "aggregates": [{"fn": "sum", "column": number.name, "as": number.name}],
            },
        },
    )
    return Fix(
        "group_by_period",
        date.name,
        f"Total {number.name} by month",
        f"Total {number.name} by month of {date.name}: {_rows(date.months)}, one per month.",
        steps,
        level="better",
        count=date.months,
        fills=number.name,
        variant=number.name,
    )


def fix_group_by_key(key: Facts, number: Facts) -> Fix:
    steps = (
        {
            "kind": "group_by",
            "params": {
                "keys": [key.name],
                "aggregates": [{"fn": "sum", "column": number.name, "as": number.name}],
            },
        },
    )
    return Fix(
        "group_by_key",
        key.name,
        f"Total {number.name} per {key.name}",
        f"Total {number.name} per {key.name}: {_rows(key.distinct)}, one per {key.name}.",
        steps,
        level="better",
        count=key.distinct,
        fills=number.name,
        variant=number.name,
    )


def _best_date_styles(f: Facts) -> list[str]:
    """The styles a text column reads as dates in: the one that reads the most; month/day and day/month
    both, when they read the same (the user picks: never guessed)."""
    best = max(f.dates)
    if best == 0 or best < READS_SHARE * f.filled:
        return []
    if f.dates[0] == best:
        return ["iso"]
    return [key for (key, _, _), n in zip(DATE_FORMATS, f.dates, strict=True) if n == best and key != "iso"]


def _key_score(f: Facts, rows: int) -> int:
    """How good a column is as a key to total by: its values repeat, there are enough of them to
    compare, and it is named like a key or a group."""
    if f.dated or f.family not in ("text", "number") or f.distinct < 5 or f.distinct * 2 > rows:
        return 0
    words = _words(f.name)
    named = (
        2 if words and words[-1] in ("id", "key", "code") else 1 if set(words) & set(C.GROUPS_WORDS) else 0
    )
    return 1 + named


def fixes(p: Plan, facts: list[Facts]) -> list[Fix]:
    """How to make the table fit the plan's analysis, and suit it better: for an empty slot, the columns
    that almost fit (needed); for a picked column, its cautions' cures (better); and the contract's own."""
    c, rows = p.contract, p.rows
    names = {f.name for f in facts}
    by_name = {f.name: f for f in facts}
    out: list[Fix] = []
    for slot in c.slots:
        if slot.table:
            continue
        value = p.values.get(slot.key)
        empty = not value
        level = "needed" if empty and slot.required else "better"
        if empty:
            out += _fixes_for_empty(slot, facts, names, level)
            continue
        for name in value if isinstance(value, list) else [value]:
            f = by_name.get(str(name))
            if f is None:
                continue
            for check in slot.checks:
                if check.level != "should" or _failed(check, f, rows) is None:
                    continue
                if check.check == "filled_share":
                    out.append(fix_drop_blanks(f, rows, slot.key))
                if check.check == "all_positive":
                    out.append(fix_keep_positive(f, slot.key))
    if c.fixes:
        picked = by_name.get(str(p.values.get(c.slots[0].key))) if c.slots else None
        if picked is not None and picked.family == "number":
            if "group_by_period" in c.fixes:
                dates = [f for f in facts if f.dated and f.months >= 5]
                if dates and rows > max(f.months for f in dates):
                    out.append(fix_group_by_period(max(dates, key=lambda f: f.months), picked, names))
            if "group_by_key" in c.fixes:
                keys = sorted(
                    (f for f in facts if f.name != picked.name and _key_score(f, rows)),
                    key=lambda f: -_key_score(f, rows),
                )
                if keys:
                    out.append(fix_group_by_key(keys[0], picked))
    seen: set[str] = set()
    unique: list[Fix] = []
    for fix in out:
        if fix.id not in seen:
            seen.add(fix.id)
            unique.append(fix)
    return sorted(unique, key=lambda f: f.level != "needed")


def _fixes_for_empty(slot: Slot, facts: list[Facts], names: set[str], level: str) -> list[Fix]:
    out: list[Fix] = []
    accepts = set(slot.accepts)
    for f in facts:
        if f.filled == 0:
            continue
        if "number" in accepts and f.family == "text" and f.numbers and f.numbers >= READS_SHARE * f.filled:
            out.append(fix_text_to_number(f, slot.key, level))
        if "date" in accepts and f.family == "text":
            out += [fix_text_to_date(f, style, slot.key, level) for style in _best_date_styles(f)]
        if "yesno" in accepts and f.family == "text":
            made = fix_yes_no_words(f, names, slot.key, level)
            if made is None and level == "needed" and accepts == {"yesno"}:
                made = fix_yes_no_value(f, names, slot.key, level)
            if made is not None:
                out.append(made)
        if "category" in accepts and level == "needed":
            limit = next(
                (ch.n for ch in slot.checks if ch.check == "distinct_max" and ch.level == "must"), None
            )
            if f.family == "text" and limit and f.distinct > limit and not f.identifier:
                out.append(fix_top_n(f, names, slot.key, level))
            if f.dated and f.months >= 2:
                out.append(fix_period_column(f, names, slot.key, level))
    return out


def with_fixes(facts: list[Facts], applied: list[Fix]) -> list[Facts]:
    """The table's facts as they will be once `applied` are (each fix's `makes`: its column replaced,
    or added): what the ranking plans against. Ranges stay unknown until the fix is really applied."""
    out = list(facts)
    for fix in applied:
        if fix.makes is None:
            continue
        at = next((i for i, f in enumerate(out) if f.name == fix.makes.name), None)
        if at is None:
            out.append(fix.makes)
        else:
            out[at] = fix.makes
    return out


def needed_fixes(p: Plan) -> list[Fix]:
    """One fix for each required slot that has nothing: the first proposed (the likeliest column)."""
    out: list[Fix] = []
    for slot in p.contract.slots:
        if slot.table or not slot.required or p.values.get(slot.key):
            continue
        found = next((f for f in p.fixes if f.slot == slot.key and f.level == "needed"), None)
        if found is not None:
            out.append(found)
    return out


# ===== the column-first ways in =====


def for_column(column: str, rows: int, facts: list[Facts]) -> list[dict[str, Any]]:
    """What can I do with a column? Only the analyses whose first slot it fits with no caution about its
    range, each one click (the rest defaulted): [{"analysis", "label", "name", "get", "columns"}]."""
    f = next((x for x in facts if x.name == column), None)
    if f is None:
        raise AnalyzeError(f"No column {column!r} in this table.")
    out: list[dict[str, Any]] = []
    for c in C.CONTRACTS:
        first = next((s for s in c.slots if not s.table), None)
        if first is None or c.id == "whatif":  # what-if is Predict a number's form with values to try
            continue
        fit = check_column(first, f, rows)
        if not fit.fits or (c.id == "benford" and not spans(f, 2)):
            continue
        out.append(
            {"analysis": c.id, "label": c.label, "name": c.name, "get": c.get, "columns": {first.key: column}}
        )
    return out


def _reason(p: Plan, by_name: dict[str, Facts]) -> tuple[int, str]:
    """(how well the analysis suits the table, 0 to 100; why, in one line) for a plan that can run."""
    c, v, rows = p.contract, p.values, p.rows

    def col(key: str) -> Facts | None:
        name = v.get(key)
        return by_name.get(name) if isinstance(name, str) else None

    if c.id in ("time_series", "forecast"):
        date = col("date")
        months = date.months if date else 0
        if date is not None and date.predicted:
            return 70, f"{date.name} holds dates: a trend and seasons can show"
        less = 5 if c.id == "forecast" else 0
        if months >= 24:
            return 90 - less, f"{v['date']} covers {months:,} months: enough to show a season"
        if months >= 6:
            return 70 - less, f"{v['date']} covers {months:,} months: a trend, too short for a season"
        return 35 - less, f"{v['date']} covers only {months:,} month{'' if months == 1 else 's'}"
    if c.id == "benford":
        f = col("column")
        if f is None or not (f.predicted or spans(f, 2)):
            return 15, f"{v['column']} stays within a narrow range: first digits tell little"
        if f.predicted:
            return 60, f"{f.name} holds amounts to test"
        orders = math.log10((f.high or 1) / (f.low_positive or 1))
        enough = "" if rows >= 300 else ", few rows for it"
        return (85 if rows >= 300 else 55), (
            f"{f.name} spans {orders:.0f} orders of magnitude over {_rows(rows)}{enough}"
        )
    if c.id == "outliers":
        f = col("column")
        if f is not None and f.family == "number":
            return (75 if rows >= 30 else 45), f"{f.name} is a number column with values to judge"
        return 40, f"{v['column']} has values that might be rare"
    if c.id == "predictors":
        target = col("target")
        others = max(0, len(by_name) - 1)
        if target is not None and "yesno" in kinds_of(target):
            return 80, f"{target.name} is a yes/no column and {others:,} columns might explain it"
        return 60, f"{others:,} columns might explain {v['target']}"
    if c.id == "regression":
        n = len(v.get("predictors") or [])
        return (
            65 if rows >= 50 else 40
        ), f"{v['target']} could be predicted from {n:,} column{'' if n == 1 else 's'}"
    if c.id == "whatif":
        return 30, f"try values for {v['target']} once a model fits"
    if c.id == "odds":
        if v.get("outcome"):
            return 70, f"{v['outcome']} is a yes/no outcome to count for each {v['column']}"
        return 50, f"{v['column']} has values to count"
    if c.id == "together":
        return 55, f"{v['first']} and {v['second']} both repeat: they can be tested together"
    if c.id == "fit":
        return 45, f"{v['column']} has values that repeat"
    if c.id in ("tie_out", "key_finder"):
        return 35, "another table is open to compare with"
    return 10, c.get


def rank(
    table: str,
    rows: int,
    facts: list[Facts],
    tables: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Check this table: every analysis ranked for it. Each: {"analysis", "label", "name", "get",
    "status": "now" (fits now) | "fixes" (fits after its fixes) | "no", "fixes": [...], "reason",
    "score", "columns", "button"}; the best first, then the ones that do not fit, with why."""
    out: list[dict[str, Any]] = []
    for c in C.CONTRACTS:
        if c.id in ("profile", "check"):
            continue
        p = plan(c.id, table, rows, facts, tables=tables)
        applied: list[Fix] = []
        if not p.ready:
            applied = needed_fixes(p)
            if applied:
                given = {f.slot: f.fills for f in applied}
                p2 = plan(c.id, table, rows, with_fixes(facts, applied), given=given, tables=tables)
                if p2.ready:
                    p = p2
                else:
                    applied = []
        entry: dict[str, Any] = {
            "analysis": c.id,
            "label": c.label,
            "name": c.name,
            "get": c.get,
            "fixes": [f.to_json() for f in applied],
            "columns": {},
        }
        if not p.ready:
            entry |= {"status": "no", "reason": p.missing, "score": 0, "button": ""}
        else:
            facts_now = {f.name: f for f in with_fixes(facts, applied)}
            score, reason = _reason(p, facts_now)
            score = max(1, score - 10 * len(applied))
            lead = " and ".join(f.label for f in applied)
            entry |= {
                "status": "fixes" if applied else "now",
                "reason": reason,
                "score": score,
                "button": f"{lead} and run" if applied else "Run",
                "columns": dict(p.values) if not applied else {},
            }
        out.append(entry)
    order = {c.id: i for i, c in enumerate(C.CONTRACTS)}
    return sorted(out, key=lambda e: (-int(e["score"]), order[e["analysis"]]))


def top_three(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The three analyses that suit the table best (never one that does not fit)."""
    return [e for e in ranked if e["status"] != "no"][:3]


def table_notes(table: str, rows: int, facts: list[Facts]) -> list[dict[str, str]]:
    """The Data shape check's notes on the table itself: wide tables, few rows, blank columns,
    identifiers and text that reads as numbers or dates. {"level": ok | warn, "text"}."""
    notes: list[dict[str, str]] = []

    def say(level: str, text: str) -> None:
        notes.append({"level": level, "text": text})

    wide = wide_series([(f.name, f.family) for f in facts])
    if wide:
        kind, names = wide
        shown = ", ".join(names[:4]) + ("..." if len(names) > 4 else "")
        say(
            "warn",
            f"This table looks wide: {len(names)} number columns ({shown}) are one measure across {kind}s. "
            f"The analyses want one row per {kind} (long): unpivot it in a notebook first.",
        )
    if rows == 0:
        say("warn", f"{table} has no rows.")
    elif rows < 30:
        say("warn", f"Only {_rows(rows)}: results will be rough.")
    else:
        say("ok", f"{_rows(rows)}, {len(facts):,} column{'' if len(facts) == 1 else 's'}.")
    for f in facts:
        if rows and f.filled == 0:
            say("warn", f"{f.name} is all blank.")
        elif rows and 100 * (rows - f.filled) / rows > 20:
            say("warn", f"{round(100 * (rows - f.filled) / rows)}% of {f.name} is blank.")
        if f.family == "text" and f.numbers and f.numbers >= READS_SHARE * f.filled:
            say("warn", f"{f.name} is text that reads as numbers ({f.numbers:,} of {f.filled:,} values).")
        elif f.family == "text" and _best_date_styles(f):
            say("warn", f"{f.name} is text that reads as dates ({max(f.dates):,} of {f.filled:,} values).")
    identifiers = [f.name for f in facts if f.identifier]
    if identifiers:
        say("ok", f"Identifiers (never analysed): {', '.join(identifiers)}.")
    return notes
