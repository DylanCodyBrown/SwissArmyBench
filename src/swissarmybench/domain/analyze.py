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
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import analysis_contracts as C
from swissarmybench.domain.analysis import wide_series
from swissarmybench.domain.analysis_contracts import Contract, Slot
from swissarmybench.domain.analysis_facts import (
    DATE_FORMATS,
    FACT_PARTS,
    NO_WORDS,
    SAMPLE_VALUES,
    VALUES_KEPT,
    YES_WORDS,
    Facts,
    Fit,
    check_column,
    date_sql,
    facts_query,
    fits,
    kinds_of,
    likeliest,
    name_score,
    needs_words,
    number_sql,
    read_facts,
    sample_query,
    spans,
    type_word,
    values_query,
)
from swissarmybench.domain.analysis_facts import rows_words as _rows
from swissarmybench.domain.analysis_fixes import (
    READS_SHARE,
    TOP_N,
    Fix,
    best_date_styles,
    fix_drop_blanks,
    fix_group_by_key,
    fix_group_by_period,
    fix_keep_positive,
    fix_period_column,
    fix_text_to_date,
    fix_text_to_number,
    fix_top_n,
    fix_yes_no_value,
    fix_yes_no_words,
    fixes,
    with_fixes,
    yes_no_words,
)

__all__ = [
    "DATE_FORMATS",
    "FACT_PARTS",
    "READS_SHARE",
    "SAMPLE_VALUES",
    "TOP_N",
    "VALUES_KEPT",
    "AnalyzeError",
    "Facts",
    "Fit",
    "Fix",
    "Plan",
    "catalog",
    "check_column",
    "contract",
    "date_sql",
    "facts_query",
    "fits",
    "fix_drop_blanks",
    "fix_group_by_key",
    "fix_group_by_period",
    "fix_keep_positive",
    "fix_period_column",
    "fix_text_to_date",
    "fix_text_to_number",
    "fix_top_n",
    "fix_yes_no_value",
    "fix_yes_no_words",
    "fixes",
    "for_column",
    "kinds_of",
    "likeliest",
    "name_score",
    "needed_fixes",
    "needs_words",
    "number_sql",
    "period_for",
    "plan",
    "rank",
    "read_facts",
    "request",
    "sample_query",
    "sentence",
    "spans",
    "table_notes",
    "top_three",
    "type_word",
    "values_query",
    "what_if_values",
    "with_fixes",
    "yes_default",
    "yes_no_words",
]


class AnalyzeError(ValueError):
    """An Analyze request that cannot be read or run: an unknown analysis, a column that does not fit."""


def contract(analysis_id: Any) -> Contract:
    """An analysis's contract by its id (or the contract itself: a blade's, which the service reads)."""
    if isinstance(analysis_id, Contract):
        return analysis_id
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
    out.fixes = fixes(c, rows, out.values, facts)
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
    return f"Run {c.label} {on}."


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
    if c.id.startswith(C.BLADE):  # your own analysis: its slots' columns, in slot order, as its `columns`
        picked: list[str] = []
        for slot in c.slots:
            value = v.get(slot.key)
            picked += [str(x) for x in (value if isinstance(value, list) else [value]) if x]
        return {"columns": picked}
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
        elif f.family == "text" and best_date_styles(f):
            say("warn", f"{f.name} is text that reads as dates ({max(f.dates):,} of {f.filled:,} values).")
    identifiers = [f.name for f in facts if f.identifier]
    if identifiers:
        say("ok", f"Identifiers (never analysed): {', '.join(identifiers)}.")
    return notes
