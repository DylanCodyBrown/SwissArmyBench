"""The Analyze page's rules (the owner, 2026-11-19: "make it stupid simple"; design principle 8.13).

Every analysis is data here: its toolbar group, its question in everyday words with the technical name
second, the column slots it needs (each saying in plain words what fits), its options (every one with a
default and a one-line meaning), and the sentence of what will run. From a table's column facts (counted
once: types, filled and different values, ranges, a few values) this module says, for one analysis:

  which columns fit each slot     only those are offered, each with its type as a word and a preview
  which one is picked             the only one that fits ("date: the only date column"), else the likeliest
                                  by its name (amount, total, price... for money; date, created, month...
                                  for time; an outcome's name for a target), else the first that fits
  what is missing                 one sentence when nothing fits (the form offers Change table)
  the sentence                    "Test whether amount follows Benford's first-digit law, on 12,400 rows
                                  of orders."
  the request                     the body the analysis's own route takes (domain/analysis.py and friends)

And the column-first ways in: the analyses a column fits (each one click), and the three a table suits
(Check this table). Standard library only; no I/O.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain.analysis import MAX_CATEGORIES, is_identifier
from swissarmybench.domain.datasets import quote
from swissarmybench.domain.steps import type_family


class AnalyzeError(ValueError):
    """An Analyze request that cannot be read: an unknown analysis, a column that does not fit."""


# ===== the catalog =====


@dataclass(frozen=True)
class Slot:
    key: str
    kind: str  # number, date, category, value, any, yesno, target, many, table
    words: str  # what fits, in plain words: "a number column: the amounts to test"
    label: str  # the chip's name: "Amounts"
    optional: bool = False


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    meaning: str  # one line, plain words
    default: Any
    choices: tuple[tuple[str, str], ...] = ()  # (value, words); none: a number or text box
    kind: str = "choice"  # choice, number, text, table (an open table), column (one that repeats)


@dataclass(frozen=True)
class Analysis:
    id: str
    group: str  # Describe, Test, Model, Time, Compare
    label: str  # the everyday question: "Do the first digits look natural?"
    name: str  # the technical name, second: "Benford's law"
    slots: tuple[Slot, ...] = ()
    options: tuple[Option, ...] = ()
    get: str = ""  # what you will get, in one line (the toolbar's tip)
    two_tables: bool = False
    route: str = ""  # the analysis it runs: fit_test, outliers, odds, ... (code and Show the math)


GROUPS: tuple[str, ...] = ("Describe", "Test", "Model", "Time", "Compare", "Yours")

_PERIODS = (("auto", "Picked from the dates"), ("day", "Day"), ("week", "Week"), ("month", "Month"))
_PERIODS += (("quarter", "Quarter"), ("year", "Year"))
_TOTALS = (("sum", "Add them up"), ("avg", "The average"), ("count", "Count the rows"))

ANALYSES: tuple[Analysis, ...] = (
    Analysis(
        "profile",
        "Describe",
        "What is in this table?",
        "profile",
        get="Every column's type, blanks, different values and range, in one table.",
    ),
    Analysis(
        "check",
        "Describe",
        "Check this table",
        "data shape check",
        get="How the table is shaped, and the three analyses that make sense for it.",
    ),
    Analysis(
        "benford",
        "Test",
        "Do the first digits look natural?",
        "Benford's law",
        (Slot("column", "number", "a number column: the amounts to test", "Amounts"),),
        (
            Option(
                "digits",
                "Digits",
                "The first digit, or the first two (finer, needs more rows).",
                "1",
                (("1", "The first digit"), ("2", "The first two digits")),
            ),
        ),
        get="Whether the amounts' first digits are as common as natural numbers' are, digit by digit.",
        route="fit_test",
    ),
    Analysis(
        "fit",
        "Test",
        "Is each value as common as expected?",
        "fit test",
        (Slot("column", "category", "a column whose values repeat: the groups to count", "Groups"),),
        (
            Option(
                "reference",
                "Compare with",
                "Every value equally common, or as common as in another open table.",
                "",
                (("", "Every value equally common"),),
                "table",
            ),
        ),
        get="Whether some values turn up more or less often than they should.",
        route="fit_test",
    ),
    Analysis(
        "together",
        "Test",
        "Are these two related?",
        "chi-square test",
        (
            Slot("first", "category", "a column whose values repeat", "First"),
            Slot("second", "category", "another column whose values repeat", "Second"),
        ),
        get="Whether the two columns go together, and the combinations furthest from chance.",
        route="fit_test",
    ),
    Analysis(
        "outliers",
        "Test",
        "Find unusual values",
        "outliers",
        (Slot("column", "value", "a number column (or one whose values repeat): the values to check", "Values"),),
        (
            Option(
                "by",
                "Judge within each",
                "Judge each group by its own usual range (a vendor, a store, a month).",
                "",
                (("", "The whole column"),),
                "column",
            ),
            Option(
                "method",
                "How to judge",
                "Robust (the median) is the safe default: a few wild values cannot hide themselves.",
                "robust",
                (
                    ("robust", "Robust: distance from the median"),
                    ("iqr", "Quartile fences (Tukey)"),
                    ("zscore", "Mean and standard deviation"),
                ),
            ),
        ),
        get="The values far from the rest, and how far out each is.",
        route="outliers",
    ),
    Analysis(
        "odds",
        "Test",
        "How likely is each value?",
        "odds",
        (
            Slot("column", "any", "the column to count: each value's share and odds", "Column"),
            Slot("outcome", "yesno", "optional: a yes/no column to count the odds of", "Outcome", optional=True),
        ),
        (
            Option("yes", "Counts as yes", "Which value of the outcome counts as yes.", "", (), "text"),
            Option("buckets", "Ranges for a number", "How many equal-sized ranges a number is cut into.", "", (), "number"),
        ),
        get="How often each value shows up; with an outcome, which values raise its odds.",
        route="odds",
    ),
    Analysis(
        "predictors",
        "Test",
        "What explains this?",
        "find predictors",
        (
            Slot("target", "any", "the column to explain", "Explain"),
            Slot("candidates", "many", "optional: the columns that might explain it (every other one)", "With", optional=True),
        ),
        (Option("buckets", "Ranges for numbers", "How many equal-sized ranges numbers are cut into.", "", (), "number"),),
        get="Every other column ranked by how much it tells about this one.",
        route="predictors",
    ),
    Analysis(
        "regression",
        "Model",
        "Predict a number",
        "regression",
        (
            Slot("target", "target", "a number (or yes/no) column: what to predict", "Predict"),
            Slot("predictors", "many", "one or more columns that might explain it", "From"),
        ),
        (Option("yes", "Counts as yes", "For a yes/no target: which value counts as yes.", "", (), "text"),),
        get="How much each column moves the target, the others held steady.",
        route="regression",
    ),
    Analysis(
        "whatif",
        "Model",
        "What if…?",
        "what-if",
        (
            Slot("target", "target", "a number (or yes/no) column: what to predict", "Predict"),
            Slot("predictors", "many", "one or more columns to set", "From"),
        ),
        (Option("yes", "Counts as yes", "For a yes/no target: which value counts as yes.", "", (), "text"),),
        get="The prediction for one row you describe, with its range (each column starts at its typical value).",
        route="regression",
    ),
    Analysis(
        "time_series",
        "Time",
        "Spot the trend and the seasons",
        "time series",
        (
            Slot("date", "date", "a date column", "Dates"),
            Slot("metric", "number", "optional: a number to total (else the rows are counted)", "Amounts", optional=True),
        ),
        (
            Option("period", "Each point is a", "How the dates are grouped.", "auto", _PERIODS),
            Option("total", "Per period", "What each period shows of the number.", "sum", _TOTALS),
        ),
        get="The trend, the season, the periods that stand out and where the level stepped.",
        route="time_series",
    ),
    Analysis(
        "forecast",
        "Time",
        "What comes next?",
        "forecast",
        (
            Slot("date", "date", "a date column", "Dates"),
            Slot("metric", "number", "optional: a number to total (else the rows are counted)", "Amounts", optional=True),
        ),
        (
            Option("horizon", "Periods ahead", "How far ahead to forecast.", 6, (), "number"),
            Option("period", "Each point is a", "How the dates are grouped.", "auto", _PERIODS),
            Option("total", "Per period", "What each period shows of the number.", "sum", _TOTALS),
        ),
        get="The periods ahead with their likely ranges, checked on the last periods held back.",
        route="forecast",
    ),
    Analysis(
        "tie_out",
        "Compare",
        "Do two tables add up the same?",
        "tie-out",
        (Slot("other", "table", "the table to tie out against", "Against"),),
        (Option("tolerance", "Still ties within", "How far apart two totals may be and still tie.", 0, (), "number"),),
        get="Per group, whether both tables' rows and totals match, and which groups are off.",
        two_tables=True,
        route="tie_out",
    ),
    Analysis(
        "key_finder",
        "Compare",
        "Which columns join two tables?",
        "Key Finder",
        (Slot("other", "table", "the table to join to (or every other open table)", "Against", optional=True),),
        (
            Option(
                "ignore_case",
                "Ignore case",
                "Count Smith and SMITH as the same value.",
                "no",
                (("no", "No"), ("yes", "Yes")),
            ),
        ),
        get="The column pairs that share values, how much of each side, and this table's likely key.",
        two_tables=True,
        route="key_finder",
    ),
)
BY_ID: dict[str, Analysis] = {a.id: a for a in ANALYSES}


def analysis(analysis_id: Any) -> Analysis:
    found = BY_ID.get(str(analysis_id))
    if found is None:
        raise AnalyzeError(f"No analysis {analysis_id!r}: one of {', '.join(BY_ID)}.")
    return found


def catalog() -> dict[str, Any]:
    """The toolbar as data: the groups in order, each analysis's question, name, tip and slots."""
    return {
        "groups": list(GROUPS),
        "analyses": [
            {
                "id": a.id,
                "group": a.group,
                "label": a.label,
                "name": a.name,
                "get": a.get,
                "two_tables": a.two_tables,
                "slots": [{"key": s.key, "kind": s.kind, "words": s.words, "label": s.label} for s in a.slots],
            }
            for a in ANALYSES
        ],
    }


# ===== a table's column facts =====


@dataclass(frozen=True)
class Facts:
    """One column as the forms see it (counted once over the table's view)."""

    name: str
    type: str
    filled: int = 0
    distinct: int = 0
    low: float | None = None  # numbers: lowest; dates: the earliest, as days since 1970
    high: float | None = None
    low_positive: float | None = None  # numbers: the lowest above zero (what Benford reads)
    sample: tuple[str, ...] = ()
    identifier: bool = False

    @property
    def family(self) -> str:
        return type_family(self.type)

    @property
    def word(self) -> str:
        return type_word(self.type)


def type_word(duckdb_type: str) -> str:
    """A type as a word a person reads: number, date, date and time, text, yes/no, list..."""
    family = type_family(duckdb_type)
    words = {"number": "number", "date": "date", "timestamp": "date and time", "boolean": "yes/no", "text": "text"}
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


SAMPLE_VALUES = 3


def facts_query(relation: str, columns: list[tuple[str, str]]) -> str:
    """Rows, then for each (name, type): filled, different, lowest, highest, lowest above zero. One pass.
    A date's range is in days since 1970 (epoch_days), so one number type holds every family's range."""
    parts = ["count(*)"]
    for name, kind in columns:
        c = quote(name)
        family = type_family(kind)
        parts += [f"count({c})", f"count(DISTINCT {c})"]
        if family == "number":
            x = f"CAST({c} AS DOUBLE)"
            finite = f"isfinite({x})"
            parts += [
                f"min({x}) FILTER (WHERE {finite})",
                f"max({x}) FILTER (WHERE {finite})",
                f"min({x}) FILTER (WHERE {finite} AND {x} > 0)",
            ]
        elif family in ("date", "timestamp"):
            parts += [f"min(CAST({c} AS DATE)) - DATE '1970-01-01'", f"max(CAST({c} AS DATE)) - DATE '1970-01-01'", "NULL"]
        else:
            parts += ["NULL", "NULL", "NULL"]
    return f"SELECT {', '.join(parts)} FROM {relation}"


def sample_query(relation: str, name: str) -> str:
    """A few different values of one column, from the view's first rows: the slot's tiny preview."""
    c = quote(name)
    return (
        f"SELECT DISTINCT CAST({c} AS VARCHAR) FROM (SELECT {c} FROM {relation} LIMIT 500) "
        f"WHERE {c} IS NOT NULL LIMIT {SAMPLE_VALUES}"
    )


def read_facts(
    columns: list[tuple[str, str]], row: tuple[Any, ...], samples: dict[str, list[str]]
) -> tuple[int, list[Facts]]:
    """facts_query's one row (and each column's sample) as (rows, Facts per column)."""
    rows = int(row[0] or 0) if row else 0
    out: list[Facts] = []
    for i, (name, kind) in enumerate(columns):
        at = 1 + 5 * i
        filled = int(row[at] or 0) if row else 0
        distinct = int(row[at + 1] or 0) if row else 0
        number = (lambda v: None if v is None else float(v))
        out.append(
            Facts(
                name,
                kind,
                filled,
                distinct,
                number(row[at + 2]) if row else None,
                number(row[at + 3]) if row else None,
                number(row[at + 4]) if row else None,
                tuple(samples.get(name, ())[:SAMPLE_VALUES]),
                is_identifier(name, kind, filled, distinct),
            )
        )
    return rows, out


# ===== which columns fit a slot =====

KIND_WORDS: dict[str, str] = {
    "number": "number",
    "date": "date",
    "category": "column whose values repeat",
    "value": "number column (or one whose values repeat)",
    "any": "column that is not an identifier",
    "yesno": "yes/no column (two values)",
    "target": "number or yes/no column",
    "many": "column that is not an identifier or a date",
}
# What a missing kind needs, said once (Never a dead end, 8.13.7).
KIND_NEEDS: dict[str, str] = {
    "number": "a column of numbers (amounts, counts, prices)",
    "date": "a column of dates or times",
    "category": "a column whose values repeat (a region, a status, a category)",
    "value": "a column of numbers, or one whose values repeat",
    "any": "a column that is not an identifier (a different value on every row tells nothing)",
    "yesno": "a column with two values (yes and no, late and on time)",
    "target": "a column of numbers, or one with two values (yes and no)",
    "many": "another column that is not an identifier or a date",
}


def _dated(f: Facts) -> bool:
    return f.family in ("date", "timestamp")


def _yesno(f: Facts) -> bool:
    return f.family == "boolean" or (f.distinct == 2 and not _dated(f))


def fits(kind: str, f: Facts) -> bool:
    """Does column `f` fit a slot of `kind`? The rules the Data shape check states, as one yes or no."""
    if kind == "date":
        return _dated(f)
    if kind == "yesno":
        return _yesno(f) and not f.identifier
    if f.identifier or f.distinct < 2:
        return False
    if kind == "number":
        return f.family == "number"
    if kind == "category":
        return not _dated(f) and f.family in ("text", "number", "boolean") and f.distinct <= MAX_CATEGORIES
    if kind == "value":
        return f.family == "number" or fits("category", f)
    if kind == "target":
        return f.family == "number" or _yesno(f)
    if kind in ("any", "many"):
        return not _dated(f) and f.family in ("text", "number", "boolean")
    return False


# Name words that make a column the likelier pick for a slot (the owner's examples first).
MONEY_WORDS = ("amount", "total", "value", "price", "revenue", "cost", "sales", "spend", "paid", "balance", "fee")
TIME_WORDS = ("date", "created", "month", "day", "time", "at", "when", "period", "week", "year", "ordered")
OUTCOME_WORDS = (
    "late", "churn", "churned", "fraud", "returned", "cancelled", "canceled", "default", "defaulted", "won",
    "lost", "success", "failed", "approved", "outcome", "target", "flag", "is", "has", "converted", "paid",
)  # fmt: skip
GROUP_WORDS = (
    "region", "category", "type", "status", "segment", "country", "state", "city", "group", "channel",
    "department", "vendor", "product", "store", "branch", "team", "kind", "class", "tier",
)  # fmt: skip
_PREFER: dict[str, tuple[str, ...]] = {
    "number": MONEY_WORDS,
    "value": MONEY_WORDS,
    "date": TIME_WORDS,
    "category": GROUP_WORDS,
    "yesno": OUTCOME_WORDS,
    "target": MONEY_WORDS + OUTCOME_WORDS,
    "any": GROUP_WORDS,
}


def _words(name: str) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return [w.lower() for w in re.split(r"[^A-Za-z0-9]+", spaced) if w]


def name_score(kind: str, name: str) -> int:
    """How much a column's name says it is what the slot wants: the earlier its word in the slot's list,
    the higher; 0 when no word matches."""
    words = _words(name)
    prefer = _PREFER.get(kind, ())
    for rank, word in enumerate(prefer):
        if word in words:
            return len(prefer) - rank
    return 0


def _family_rank(kind: str, f: Facts) -> int:
    """Within a slot that takes several families, the one it is mostly for first."""
    if kind in ("value", "target"):
        return 1 if f.family == "number" else 0
    if kind == "category":
        return 1 if f.family != "number" else 0
    return 0


def likeliest(kind: str, fitting: list[Facts]) -> tuple[Facts | None, str]:
    """(the pick, why in words) among the columns that fit a slot: the only one, else the likeliest by its
    name, else the first in the table's order."""
    if not fitting:
        return None, ""
    what = ONLY_WORDS.get(kind, "column that fits")
    if len(fitting) == 1:
        return fitting[0], f"the only {what}"
    best = max(fitting, key=lambda f: (name_score(kind, f.name), _family_rank(kind, f), -fitting.index(f)))
    if name_score(kind, best.name):
        return best, "the likeliest, by its name"
    return best, f"the first {what}"


ONLY_WORDS: dict[str, str] = {
    "number": "number column",
    "date": "date column",
    "category": "column whose values repeat",
    "yesno": "yes/no column",
    "target": "number or yes/no column",
}


# ===== a form, planned =====


@dataclass
class Plan:
    analysis: Analysis
    rows: int
    table: str
    slots: list[dict[str, Any]] = field(default_factory=list)
    options: list[dict[str, Any]] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)
    chosen: dict[str, Any] = field(default_factory=dict)  # option values in force
    missing: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "analysis": self.analysis.id,
            "label": self.analysis.label,
            "name": self.analysis.name,
            "get": self.analysis.get,
            "rows": self.rows,
            "table": self.table,
            "slots": self.slots,
            "options": self.options,
            "columns": self.values,
            "settings": self.chosen,
            "missing": self.missing,
            "ready": self.missing is None,
            "sentence": sentence(self) if self.missing is None else None,
        }


def _offer(f: Facts) -> dict[str, Any]:
    return {"name": f.name, "type": f.word, "preview": list(f.sample)}


def plan(
    analysis_id: Any,
    table: str,
    rows: int,
    facts: list[Facts],
    given: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    tables: list[dict[str, Any]] | None = None,
) -> Plan:
    """The form for one analysis on a table: each slot's fitting columns and its pick (what was given,
    when it fits; else the obvious one), the options with their values, and what is missing.

    `given`: {slot: column or [columns]} (the user's chips, remembered or from Run again); `settings`:
    {option: value}; `tables`: the other open tables [{"grid", "label"}] for a two-table slot."""
    a = analysis(analysis_id)
    given = dict(given or {})
    settings = dict(settings or {})
    out = Plan(a, rows, table)
    taken: set[str] = set()
    by_name = {f.name: f for f in facts}
    for slot in a.slots:
        if slot.kind == "table":
            others = tables or []
            pick = given.get(slot.key)
            if pick not in {t["grid"] for t in others}:
                pick = None if slot.optional else (others[0]["grid"] if others else None)
            entry = {
                "key": slot.key,
                "kind": "table",
                "label": slot.label,
                "words": slot.words,
                "optional": slot.optional,
                "many": False,
                "offered": [{"name": t["grid"], "type": "table", "preview": [t["label"]]} for t in others],
                "value": pick,
                "said": "" if pick is None else ("the only other open table" if len(others) == 1 else "the last one you had open"),
            }
            if pick is None and not slot.optional:
                out.missing = f"{a.label} needs a second open table: open another table first."
            out.slots.append(entry)
            out.values[slot.key] = pick
            continue
        fitting = [f for f in facts if fits(slot.kind, f)]
        offered = [_offer(f) for f in fitting]
        entry = {
            "key": slot.key,
            "kind": slot.kind,
            "label": slot.label,
            "words": slot.words,
            "optional": slot.optional,
            "many": slot.kind == "many",
            "offered": offered,
        }
        if slot.kind == "many":
            wanted = given.get(slot.key)
            if isinstance(wanted, list) and wanted:
                value = [n for n in wanted if n in by_name and fits("many", by_name[n]) and n not in taken]
                said = ""
            elif slot.optional:
                value = []
                said = "every other column"
            else:
                value = [f.name for f in fitting if f.name not in taken]
                said = "every column that could explain it"
            entry |= {"value": value, "said": said}
            if not value and not slot.optional:
                out.missing = out.missing or (
                    f"{a.label} needs {KIND_NEEDS['many']} besides {', '.join(sorted(taken)) or 'the target'}."
                )
            out.values[slot.key] = value
            out.slots.append(entry)
            continue
        wanted = given.get(slot.key)
        pool = [f for f in fitting if f.name not in taken]
        pick: Facts | None = None
        said = ""
        if isinstance(wanted, str) and wanted in by_name and by_name[wanted] in fitting:
            pick, said = by_name[wanted], ""
        elif wanted == "" and slot.optional:
            pick = None
        elif slot.optional:
            # An optional slot is filled only when a column is clearly named for it (an outcome's name).
            named = [f for f in pool if name_score(slot.kind, f.name)]
            if named and slot.kind == "yesno":
                pick, said = likeliest(slot.kind, named)
            elif named and slot.kind == "number" and a.id in ("time_series", "forecast"):
                pick, said = likeliest(slot.kind, named)
        else:
            pick, said = likeliest(slot.kind, pool)
        if pick is None and not slot.optional:
            out.missing = out.missing or (
                f"This table has no {KIND_WORDS[slot.kind]} for {slot.label.lower()}: "
                f"{a.label.rstrip('?…')} needs {KIND_NEEDS[slot.kind]}."
            )
        if pick is not None:
            taken.add(pick.name)
        entry |= {"value": pick.name if pick else None, "said": said}
        out.values[slot.key] = pick.name if pick else None
        out.slots.append(entry)
    for opt in a.options:
        value = settings.get(opt.key, opt.default)
        choices = [list(c) for c in opt.choices]
        if opt.kind == "table":
            choices += [[t["grid"], t["label"]] for t in tables or []]
        if opt.kind == "column":
            choices += [[f.name, f.name] for f in facts if fits("category", f) and f.name not in taken]
        if choices and str(value) not in {str(c[0]) for c in choices}:
            value = opt.default
        if opt.key == "yes":
            value = value or _yes_default(a, out.values, by_name)
            hidden = not _needs_yes(a, out.values, by_name)
        else:
            hidden = False
        if hidden:
            continue
        out.options.append(
            {"key": opt.key, "label": opt.label, "meaning": opt.meaning, "value": value, "choices": choices, "kind": opt.kind}
        )
        out.chosen[opt.key] = value
    if a.id == "whatif" and out.missing is None:
        for name in out.values.get("predictors") or []:
            f = by_name[name]
            key = f"value:{name}"
            typical = settings.get(key, _typical(f))
            out.options.append(
                {
                    "key": key,
                    "label": name,
                    "meaning": f"The {name} to try (it starts at a typical value).",
                    "value": typical,
                    "choices": [[v, v] for v in f.sample] if f.family != "number" else [],
                    "kind": "number" if f.family == "number" else "choice",
                }
            )
            out.chosen[key] = typical
    return out


def _target_facts(a: Analysis, values: dict[str, Any], by_name: dict[str, Facts]) -> Facts | None:
    key = "outcome" if a.id == "odds" else "target"
    name = values.get(key)
    return by_name.get(name) if isinstance(name, str) else None


def _needs_yes(a: Analysis, values: dict[str, Any], by_name: dict[str, Facts]) -> bool:
    f = _target_facts(a, values, by_name)
    if f is None:
        return False
    return a.id == "odds" or f.family != "number"


YES_WORDS = ("true", "yes", "y", "1", "late", "won", "fraud", "churned", "returned", "approved", "success")


def _yes_default(a: Analysis, values: dict[str, Any], by_name: dict[str, Facts]) -> str:
    f = _target_facts(a, values, by_name)
    if f is None:
        return ""
    for v in f.sample:
        if v.strip().lower() in YES_WORDS:
            return v
    return f.sample[-1] if f.sample else ""


def _typical(f: Facts) -> Any:
    if f.family == "number" and f.low is not None and f.high is not None:
        mid = (f.low + f.high) / 2
        return round(mid, 2) if not mid.is_integer() else int(mid)
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


def _rows(n: int) -> str:
    return f"{n:,} row{'s' if n != 1 else ''}"


def sentence(p: Plan) -> str:
    """One short sentence of what will run, in the form's own words."""
    v, o, a = p.values, p.chosen, p.analysis
    on = f"on {_rows(p.rows)} of {p.table}"
    if a.id == "profile":
        return f"Describe every column of {p.table} ({_rows(p.rows)})."
    if a.id == "check":
        return f"Check how {p.table} is shaped and which analyses suit it ({_rows(p.rows)})."
    if a.id == "benford":
        which = "first-digit" if str(o.get("digits", "1")) == "1" else "first-two-digits"
        return f"Test whether {v['column']} follows Benford's {which} law, {on}."
    if a.id == "fit":
        against = "as common as in the other table" if o.get("reference") else "equally common"
        return f"Test whether each {v['column']} is {against}, {on}."
    if a.id == "together":
        return f"Test whether {v['first']} and {v['second']} go together, {on}."
    if a.id == "outliers":
        within = f" within each {o['by']}" if o.get("by") else ""
        return f"Find the unusual values of {v['column']}{within}, {on}."
    if a.id == "odds":
        if v.get("outcome"):
            return f"Count the odds of {v['outcome']} = {o.get('yes') or '?'} for each {v['column']}, {on}."
        return f"Count how often each {v['column']} shows up, {on}."
    if a.id == "predictors":
        pool = v.get("candidates") or []
        among = f"among {', '.join(pool)}" if pool else "among every other column"
        return f"Rank what explains {v['target']} {among}, {on}."
    if a.id in ("regression", "whatif"):
        verb = "Predict" if a.id == "regression" else "Try a what-if for"
        return f"{verb} {v['target']} from {', '.join(v.get('predictors') or [])}, {on}."
    if a.id in ("time_series", "forecast"):
        what = v.get("metric") or "the rows"
        verb = "Total" if v.get("metric") and o.get("total") != "avg" else "Average" if v.get("metric") else "Count"
        if a.id == "forecast":
            return f"Forecast {what} {o.get('horizon', 6)} periods ahead by {v['date']}, {on}."
        return f"{verb} {what} by {v['date']} and spot the trend and seasons, {on}."
    if a.id == "tie_out":
        return f"Tie out {p.table} against the other table, group by group."
    if a.id == "key_finder":
        return f"Find the columns that join {p.table} to {'the other table' if v.get('other') else 'every other open table'}."
    return f"Run {a.name} {on}."


# ===== the request each analysis's own route takes =====


def request(p: Plan, by_name: dict[str, Facts]) -> dict[str, Any]:
    """The body the analysis's route takes (see routes_analysis.py and friends), from a ready plan."""
    if p.missing is not None:
        raise AnalyzeError(p.missing)
    v, o, a = p.values, p.chosen, p.analysis
    if a.id == "benford":
        return {"columns": [v["column"]], "expected": "benford" if str(o.get("digits", "1")) == "1" else "benford2"}
    if a.id == "fit":
        body: dict[str, Any] = {"columns": [v["column"]], "expected": "even"}
        if o.get("reference"):
            body |= {"expected": "grid", "reference": {"grid": o["reference"], "column": v["column"]}}
        return body
    if a.id == "together":
        return {"columns": [v["first"], v["second"]], "expected": "together"}
    if a.id == "outliers":
        f = by_name[v["column"]]
        if f.family != "number":
            return {"column": v["column"], "look": "frequency"}
        body = {"column": v["column"], "look": "amount", "method": o.get("method") or "robust"}
        if o.get("by"):
            body["by"] = o["by"]
        return body
    if a.id == "odds":
        body = {"column": v["column"]}
        if _number(o.get("buckets")):
            body["buckets"] = int(_number(o["buckets"]) or 0)
        if v.get("outcome"):
            body["outcome"] = {"column": v["outcome"], "values": [str(o.get("yes") or "")]}
        return body
    if a.id == "predictors":
        body = {"target": v["target"]}
        if v.get("candidates"):
            body["candidates"] = list(v["candidates"])
        if _number(o.get("buckets")):
            body["buckets"] = int(_number(o["buckets"]) or 0)
        return body
    if a.id in ("regression", "whatif"):
        body = {"target": v["target"], "predictors": list(v.get("predictors") or [])}
        target = by_name[v["target"]]
        if target.family != "number":
            body["outcome"] = {"column": v["target"], "values": [str(o.get("yes") or "")]}
        return body
    if a.id in ("time_series", "forecast"):
        date = by_name[v["date"]]
        period = o.get("period") or "auto"
        if period == "auto":
            period = period_for(None if date.low is None or date.high is None else date.high - date.low)
        total = o.get("total") or "sum"
        if not v.get("metric"):
            total = "count"
        body = {"date": v["date"], "period": period, "total": total}
        if v.get("metric"):
            body["metric"] = v["metric"]
        if a.id == "forecast":
            body["horizon"] = int(_number(o.get("horizon")) or 6)
        return body
    if a.id == "tie_out":
        body = {"other": v["other"]}
        if _number(o.get("tolerance")):
            body["tolerance"] = _number(o["tolerance"])
        return body
    if a.id == "key_finder":
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
        out[name] = number if number is not None and not isinstance(raw, bool) else raw
    return out


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


# ===== the column-first ways in =====


def for_column(column: str, facts: list[Facts]) -> list[dict[str, Any]]:
    """What can I do with a column? Only the analyses whose first slot it fits, each one click (the rest
    defaulted): [{"analysis", "label", "name", "columns": {slot: column}}]."""
    f = next((x for x in facts if x.name == column), None)
    if f is None:
        raise AnalyzeError(f"No column {column!r} in this table.")
    out: list[dict[str, Any]] = []
    for a in ANALYSES:
        first = next((s for s in a.slots if s.kind not in ("table", "many")), None)
        if first is None:
            continue
        if a.id == "benford" and not _spans(f, 2):
            continue
        if a.id == "whatif":
            continue  # its form is Predict a number's, with values to try: reached from the toolbar
        if fits(first.kind, f):
            out.append({"analysis": a.id, "label": a.label, "name": a.name, "get": a.get, "columns": {first.key: column}})
    return out


def _spans(f: Facts, orders: float) -> bool:
    """Do a number column's values above zero span `orders` orders of magnitude (Benford's range)?"""
    if f.family != "number" or not f.low_positive or not f.high or f.high <= 0:
        return False
    return math.log10(f.high / f.low_positive) >= orders


def for_table(facts: list[Facts]) -> list[dict[str, Any]]:
    """Check this table: the three analyses that make sense for it, in order, each one click."""
    numbers = [f for f in facts if fits("number", f)]
    dates = [f for f in facts if fits("date", f)]
    groups = [f for f in facts if fits("category", f) and f.family != "number"]
    yesno = [f for f in facts if fits("yesno", f)]
    picks: list[tuple[str, dict[str, Any]]] = []
    if dates:
        picks.append(("time_series", {}))
    if any(_spans(f, 2) for f in numbers):
        best = max((f for f in numbers if _spans(f, 2)), key=lambda f: name_score("number", f.name))
        picks.append(("benford", {"column": best.name}))
    if numbers:
        picks.append(("outliers", {}))
    if yesno or (groups and len(facts) > 2):
        picks.append(("predictors", {}))
    if groups:
        picks.append(("odds", {}))
    if numbers and len(numbers) + len(groups) > 1:
        picks.append(("regression", {}))
    picks.append(("profile", {}))
    out: list[dict[str, Any]] = []
    for analysis_id, columns in picks:
        if any(o["analysis"] == analysis_id for o in out):
            continue
        a = BY_ID[analysis_id]
        out.append({"analysis": a.id, "label": a.label, "name": a.name, "get": a.get, "columns": columns})
        if len(out) == 3:
            break
    return out
