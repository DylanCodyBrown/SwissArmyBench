"""Make it fit (the owner, 2026-11-19: "and even suggestions for the current data to get the best
analysis"; design principle 8.13): when a table almost fits an analysis, the fixes that would make it fit,
each as the grid's own steps (DuckDB over the user's table, seen in the steps strip and undone there), one
plain sentence with its count. Never applied by itself: the user's Apply, or the agent's steps commands.

  text read as numbers or as dates (one style for the column, never guessed row by row), a date grouped by
  month as a category, the ten most common values and Other, the rows with no value left out, the values
  above zero kept, a yes/no column from Y/N and 1/0 in any spelling or from one value of a text column, and
  (the Outliers contract's own) the rows totalled per month or per key.

Standard library only; no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from swissarmybench.domain import analysis_contracts as C
from swissarmybench.domain.analysis import is_identifier
from swissarmybench.domain.analysis_contracts import Contract, Slot
from swissarmybench.domain.analysis_facts import (
    DATE_FORMATS,
    VALUES_KEPT,
    YES_WORDS,
    Facts,
    date_sql,
    failed,
    number_sql,
    rows_words,
    words_of,
)
from swissarmybench.domain.datasets import quote

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
        f"Leave out the {rows_words(blank)} with no {f.name}.",
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
        f"Keep {f.name} above zero: leaves out {rows_words(f.nonpositive)} at or below it.",
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
        f"Make {new} from {f.name}: {', '.join(yes)} count as yes ({rows_words(counted)}), "
        f"{', '.join(no)} as no.",
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
    part = "_".join(words_of(value))[:30] or "value"
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
        f"Make {new} from {f.name}: {value} is yes ({counted:,} of {rows_words(f.filled)}), every "
        f"other value no.",
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
        f"Total {number.name} by month of {date.name}: {rows_words(date.months)}, one per month.",
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
        f"Total {number.name} per {key.name}: {rows_words(key.distinct)}, one per {key.name}.",
        steps,
        level="better",
        count=key.distinct,
        fills=number.name,
        variant=number.name,
    )


def best_date_styles(f: Facts) -> list[str]:
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
    words = words_of(f.name)
    named = (
        2 if words and words[-1] in ("id", "key", "code") else 1 if set(words) & set(C.GROUPS_WORDS) else 0
    )
    return 1 + named


def fixes(c: Contract, rows: int, values: dict[str, Any], facts: list[Facts]) -> list[Fix]:
    """How to make the table fit the plan's analysis, and suit it better: for an empty slot, the columns
    that almost fit (needed); for a picked column, its cautions' cures (better); and the contract's own."""
    names = {f.name for f in facts}
    by_name = {f.name: f for f in facts}
    out: list[Fix] = []
    for slot in c.slots:
        if slot.table:
            continue
        value = values.get(slot.key)
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
                if check.level != "should" or failed(check, f, rows) is None:
                    continue
                if check.check == "filled_share":
                    out.append(fix_drop_blanks(f, rows, slot.key))
                if check.check == "all_positive":
                    out.append(fix_keep_positive(f, slot.key))
    if c.fixes:
        picked = by_name.get(str(values.get(c.slots[0].key))) if c.slots else None
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
            out += [fix_text_to_date(f, style, slot.key, level) for style in best_date_styles(f)]
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
