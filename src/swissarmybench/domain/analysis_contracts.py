"""Each analysis's data contract (the owner, 2026-11-19: "We need a data structure contract format for each
analysis with a clear definition of what types of data columns and what format the data has to be in; then
present that to the agent, and mock up a sample to include in each analysis input window").

A contract is data, one entry per analysis, in one format (FORMAT, versioned). The form, the column picking,
the column-first buttons, Check this table, the Data shape check, the made-up sample and the agent all read
it; domain/analyze.py is the one checker. Standard library only; no I/O.

    id, label, name, get         the analysis; its everyday question; its technical name; what you get
    group                        its place on the Analyze toolbar (Describe, Test, Model, Time, Compare)
    table                        rows (at least, must; and should), one row per what ("one row per order"),
                                 a series' grain ("one row per date"), two tables (and what they share)
    slots                        key; plain words; the kinds it accepts (number, whole number, date or time,
                                 text category, yes/no, any); how many (one, one or more, optional);
                                 constraints in plain words AND as checks; the name hints for the likeliest
    options                      key, label, type, default, allowed values, one plain line
    output                       the cards it makes; a table result's columns and types (Open as grid)
    sample                       how its made-up sample is built (generated: sample()), and its notes

A check is {"check": id, ...parameters, "level": "must" | "should", "words": plain words}: a "must" that
fails means the column does not fit (the form does not offer it, and says why); a "should" that fails is
a caution (the column is offered, the caution said).
"""

from __future__ import annotations

import ast
import datetime as dt
from dataclasses import dataclass, field
from typing import Any

FORMAT = 1  # the contract format's version: a change of shape is a new number

# The kinds a slot accepts, in plain words (a column's own kinds are domain/analyze.py's kinds_of).
KINDS: dict[str, str] = {
    "number": "number",
    "whole": "whole number",
    "date": "date or time",
    "category": "text category",
    "yesno": "yes/no",
    "any": "any column",
}
COUNTS: dict[str, str] = {
    "one": "exactly one",
    "many": "one or more",
    "optional": "optional (one or none)",
    "any": "optional (none, one or more)",
}
CHECKS: dict[str, str] = {
    "not_identifier": "not an identifier (a different value on every row tells nothing)",
    "distinct_min": "at least {n} different values",
    "distinct_max": "at most {n} different values",
    "two_values": "exactly two different values",
    "some_positive": "values above zero",
    "spans_orders": "values above zero spanning {n} orders of magnitude (10s to 1,000s)",
    "filled_share": "at most {blank}% blank (blanks are left out)",
    "periods_min": "dates on at least {n} different days",
    "all_positive": "no zero or negative values (they are left out)",
}
# The fixes Analyze can propose when a table almost fits (domain/analyze.py builds each as grid steps).
FIXES: dict[str, str] = {
    "text_to_number": "a text column whose values are numbers, read as numbers",
    "text_to_date": "a text column whose values are dates, read as dates",
    "period_column": "a date column grouped by month, as a category",
    "group_by_period": "the rows totalled per month (one row per month)",
    "group_by_key": "the rows totalled per key (one row per customer, vendor...)",
    "keep_positive": "only the rows above zero kept",
    "top_n_other": "the ten most common values kept, the rest called Other",
    "drop_blanks": "the rows with no value left out",
    "yes_no": "a yes/no column made from Y/N, 1/0 or one value of a text column",
}
OUTPUT_CARDS: dict[str, str] = {"note": "a report-style note", "plotly": "a chart", "table": "a table"}


@dataclass(frozen=True)
class Check:
    check: str
    level: str = "must"
    n: float | None = None
    blank: float | None = None

    @property
    def words(self) -> str:
        return CHECKS[self.check].format(n=_number_words(self.n), blank=_number_words(self.blank))

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"check": self.check, "level": self.level, "words": self.words}
        if self.n is not None:
            out["n"] = self.n
        if self.blank is not None:
            out["blank"] = self.blank
        return out


def _number_words(n: float | None) -> str:
    if n is None:
        return ""
    return f"{int(n):,}" if float(n).is_integer() else f"{n:g}"


@dataclass(frozen=True)
class Slot:
    key: str
    label: str  # the chip's name
    words: str  # what fits, in plain words: "a number column: the amounts to test"
    accepts: tuple[str, ...]  # KINDS
    count: str = "one"  # COUNTS
    checks: tuple[Check, ...] = ()
    hints: tuple[str, ...] = ()  # name words that make a column the likelier pick, likeliest first
    sample: tuple[str, ...] = ()  # the sample's column(s) for this slot

    @property
    def optional(self) -> bool:
        return self.count in ("optional", "any")

    @property
    def many(self) -> bool:
        return self.count in ("many", "any")

    @property
    def required(self) -> bool:
        return self.count in ("one", "many")

    @property
    def table(self) -> bool:
        """A second table, not a column of this one."""
        return self.accepts == ("any",)

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "words": self.words,
            "accepts": list(self.accepts),
            "accepts_words": [KINDS[k] for k in self.accepts],
            "count": self.count,
            "count_words": COUNTS[self.count],
            "checks": [c.to_json() for c in self.checks],
            "hints": list(self.hints),
            "sample_columns": list(self.sample),
        }


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    meaning: str  # one plain line
    default: Any
    type: str = "choice"  # choice, number, text, table (another open table), column (one of this table's)
    choices: tuple[tuple[str, str], ...] = ()  # (value, words)

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "meaning": self.meaning,
            "type": self.type,
            "default": self.default,
            "allowed": [{"value": v, "words": w} for v, w in self.choices],
        }


@dataclass(frozen=True)
class Table:
    rows_min: int = 2  # must: fewer rows and it cannot run
    rows_should: int = 30  # should: fewer and the result is rough
    one_row_per: str = "one row per thing counted (an order, an invoice)"
    series: str | None = None  # a series' grain: "one row per date (or many, totalled per period)"
    two_tables: str | None = None  # what the two tables share

    def to_json(self) -> dict[str, Any]:
        return {
            "rows_min": self.rows_min,
            "rows_should": self.rows_should,
            "one_row_per": self.one_row_per,
            "series": self.series,
            "two_tables": self.two_tables,
        }


@dataclass(frozen=True)
class Output:
    cards: tuple[str, ...] = ("note", "plotly")
    table: tuple[tuple[str, str], ...] = ()  # Open as grid's columns and types

    def to_json(self) -> dict[str, Any]:
        return {
            "cards": [{"kind": c, "words": OUTPUT_CARDS[c]} for c in self.cards],
            "table": [{"column": c, "type": t} for c, t in self.table],
        }


@dataclass(frozen=True)
class Contract:
    id: str
    group: str
    label: str
    name: str
    get: str
    slots: tuple[Slot, ...] = ()
    options: tuple[Option, ...] = ()
    table: Table = field(default_factory=Table)
    output: Output = field(default_factory=Output)
    route: str = ""  # the analysis it runs (Copy code and Show the math): fit_test, outliers...
    sample: dict[str, Any] = field(default_factory=dict)  # how the made-up sample is built
    fixes: tuple[str, ...] = ()  # its own suggestions (FIXES), beside the ones every slot's checks bring

    @property
    def two_tables(self) -> bool:
        return self.table.two_tables is not None

    def to_json(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "id": self.id,
            "group": self.group,
            "label": self.label,
            "name": self.name,
            "get": self.get,
            "table": self.table.to_json(),
            "slots": [s.to_json() for s in self.slots],
            "options": [o.to_json() for o in self.options],
            "output": self.output.to_json(),
            "fixes": [{"kind": k, "words": FIXES[k]} for k in self.fixes],
        }


GROUPS: tuple[str, ...] = ("Describe", "Test", "Model", "Time", "Compare", "Yours")

NOT_ID = Check("not_identifier")
TWO = Check("distinct_min", n=2)
FEW = Check("distinct_max", n=200)
BLANKS = Check("filled_share", "should", blank=20)
POSITIVE = Check("all_positive", "should")
MONEY = ("amount", "total", "value", "price", "revenue", "cost", "sales", "spend", "paid", "balance", "fee")
TIME = ("date", "created", "month", "day", "time", "at", "when", "period", "week", "year", "ordered")
OUTCOME = (
    "late", "churn", "churned", "fraud", "returned", "cancelled", "canceled", "default", "defaulted", "won",
    "lost", "success", "failed", "approved", "outcome", "target", "flag", "is", "has", "converted",
)  # fmt: skip
GROUPS_WORDS = (
    "region", "category", "type", "status", "segment", "country", "state", "city", "group", "channel",
    "department", "vendor", "product", "store", "branch", "team", "kind", "class", "tier",
)  # fmt: skip
_PERIODS: tuple[tuple[str, str], ...] = (
    ("auto", "Picked from the dates"),
    ("day", "Day"),
    ("week", "Week"),
    ("month", "Month"),
    ("quarter", "Quarter"),
    ("year", "Year"),
)
_TOTALS = (("sum", "Add them up"), ("avg", "The average"), ("count", "Count the rows"))
_YES = Option("yes", "Counts as yes", "Which value of the yes/no column counts as yes.", "", "text")
_TARGET = Slot(
    "target",
    "Predict",
    "a number (or yes/no) column: what to predict",
    ("number", "yesno"),
    checks=(NOT_ID, TWO, BLANKS),
    hints=MONEY + OUTCOME,
    sample=("amount",),
)
_PREDICTORS = Slot(
    "predictors",
    "From",
    "one or more columns that might explain it",
    ("number", "category", "yesno"),
    "many",
    (NOT_ID, TWO, FEW, BLANKS),
    sample=("units", "region"),
)
_DATE = Slot(
    "date",
    "Dates",
    "a date column",
    ("date",),
    checks=(Check("periods_min", n=4),),
    hints=TIME,
    sample=("order_month",),
)
_METRIC = Slot(
    "metric",
    "Amounts",
    "optional: a number to total (else the rows are counted)",
    ("number",),
    "optional",
    (NOT_ID, BLANKS),
    MONEY,
    ("amount",),
)
_SERIES = Table(
    rows_min=4,
    rows_should=24,
    one_row_per="one row per sale or event, with its date (or one per period)",
    series="the dates are grouped into periods (day, week, month...): two full years of months show a season",
)

CONTRACTS: tuple[Contract, ...] = (
    Contract(
        "profile",
        "Describe",
        "What is in this table?",
        "profile",
        "Every column's type, blanks, different values and range, in one table.",
        table=Table(rows_min=1, rows_should=1, one_row_per="any table"),
        output=Output(
            ("note",), (("column", "text"), ("type", "text"), ("blanks", "number"), ("distinct", "number"))
        ),
        sample={"rows": 8, "columns": ("order_id", "region", "amount", "order_date")},
    ),
    Contract(
        "check",
        "Describe",
        "Check this table",
        "data shape check",
        "How the table is shaped, and the three analyses that make sense for it.",
        table=Table(rows_min=1, rows_should=30, one_row_per="any table: long (one row per thing), not wide"),
        output=Output(("note",)),
        sample={"rows": 8, "columns": ("order_id", "region", "amount", "order_date")},
    ),
    Contract(
        "benford",
        "Test",
        "Do the first digits look natural?",
        "Benford's law",
        "Whether the amounts' first digits are as common as natural numbers' are, digit by digit.",
        (
            Slot(
                "column",
                "Amounts",
                "a number column: the amounts to test",
                ("number",),
                checks=(
                    NOT_ID,
                    Check("some_positive"),
                    Check("spans_orders", "should", n=2),
                    POSITIVE,
                    BLANKS,
                ),
                hints=MONEY,
                sample=("amount",),
            ),
        ),
        (
            Option(
                "digits",
                "Digits",
                "The first digit, or the first two (finer, needs more rows).",
                "1",
                choices=(("1", "The first digit"), ("2", "The first two digits")),
            ),
        ),
        Table(
            rows_min=10, rows_should=300, one_row_per="one row per amount (an invoice, a payment), not totals"
        ),
        Output(
            table=(("value", "text"), ("observed", "number"), ("expected", "number"), ("residual", "number"))
        ),
        "fit_test",
        {"rows": 12, "columns": ("invoice_id", "amount")},
    ),
    Contract(
        "fit",
        "Test",
        "Is each value as common as expected?",
        "fit test",
        "Whether some values turn up more or less often than they should.",
        (
            Slot(
                "column",
                "Groups",
                "a column whose values repeat: the groups to count",
                ("category", "whole", "yesno"),
                checks=(NOT_ID, TWO, FEW, BLANKS),
                hints=GROUPS_WORDS,
                sample=("weekday",),
            ),
        ),
        (
            Option(
                "reference",
                "Compare with",
                "Every value equally common, or as common as in another open table.",
                "",
                "table",
                (("", "Every value equally common"),),
            ),
        ),
        Table(rows_min=5, one_row_per="one row per thing counted (a shift, a ticket), not counts"),
        Output(
            table=(("value", "text"), ("observed", "number"), ("expected", "number"), ("residual", "number"))
        ),
        "fit_test",
        {"rows": 14, "columns": ("ticket_id", "weekday")},
    ),
    Contract(
        "together",
        "Test",
        "Are these two related?",
        "chi-square test",
        "Whether the two columns go together, and the combinations furthest from chance.",
        (
            Slot(
                "first",
                "First",
                "a column whose values repeat",
                ("category", "whole", "yesno"),
                checks=(NOT_ID, TWO, FEW, BLANKS),
                hints=GROUPS_WORDS,
                sample=("region",),
            ),
            Slot(
                "second",
                "Second",
                "another column whose values repeat",
                ("category", "whole", "yesno"),
                checks=(NOT_ID, TWO, FEW, BLANKS),
                hints=OUTCOME,
                sample=("late",),
            ),
        ),
        table=Table(rows_min=5, one_row_per="one row per thing (an order), both columns on it"),
        output=Output(table=(("a", "text"), ("b", "text"), ("observed", "number"), ("expected", "number"))),
        route="fit_test",
        sample={"rows": 12, "columns": ("order_id", "region", "late")},
    ),
    Contract(
        "outliers",
        "Test",
        "Find unusual values",
        "outliers",
        "The values far from the rest, and how far out each is.",
        (
            Slot(
                "column",
                "Values",
                "a number column (or one whose values repeat): the values to check",
                ("number", "category"),
                checks=(NOT_ID, TWO, BLANKS),
                hints=MONEY,
                sample=("unit_cost",),
            ),
        ),
        (
            Option(
                "by",
                "Judge within each",
                "Judge each group by its own usual range (a vendor, a store, a month).",
                "",
                "column",
                (("", "The whole column"),),
            ),
            Option(
                "method",
                "How to judge",
                "Robust (the median) is the safe default: a few wild values cannot hide themselves.",
                "robust",
                choices=(
                    ("robust", "Robust: distance from the median"),
                    ("iqr", "Quartile fences (Tukey)"),
                    ("zscore", "Mean and standard deviation"),
                ),
            ),
        ),
        Table(rows_min=5, one_row_per="one row per value (an invoice line), not totals"),
        Output(table=(("value", "number"), ("score", "number"))),
        "outliers",
        {"rows": 9, "columns": ("invoice_id", "vendor", "unit_cost")},
        ("group_by_period", "group_by_key"),
    ),
    Contract(
        "odds",
        "Test",
        "How likely is each value?",
        "odds",
        "How often each value shows up; with an outcome, which values raise its odds.",
        (
            Slot(
                "column",
                "Column",
                "the column to count: each value's share and odds",
                ("category", "number", "yesno"),
                checks=(NOT_ID, TWO, BLANKS),
                hints=GROUPS_WORDS,
                sample=("region",),
            ),
            Slot(
                "outcome",
                "Outcome",
                "optional: a yes/no column to count the odds of",
                ("yesno",),
                "optional",
                (Check("two_values"),),
                OUTCOME,
                ("late",),
            ),
        ),
        (
            _YES,
            Option(
                "buckets",
                "Ranges for a number",
                "How many equal-sized ranges a number is cut into.",
                "",
                "number",
            ),
        ),
        Table(
            rows_min=5, one_row_per="one row per chance (an order), the category and the outcome as columns"
        ),
        Output(table=(("value", "text"), ("rows", "number"), ("share", "number"), ("odds_ratio", "number"))),
        "odds",
        {"rows": 12, "columns": ("order_id", "region", "late")},
    ),
    Contract(
        "predictors",
        "Test",
        "What explains this?",
        "find predictors",
        "Every other column ranked by how much it tells about this one.",
        (
            Slot(
                "target",
                "Explain",
                "the column to explain",
                ("category", "number", "yesno"),
                checks=(NOT_ID, TWO, BLANKS),
                hints=OUTCOME + GROUPS_WORDS,
                sample=("late",),
            ),
            Slot(
                "candidates",
                "With",
                "optional: the columns that might explain it (every other one)",
                ("category", "number", "yesno"),
                "any",
                (NOT_ID, TWO, BLANKS),
                sample=("region", "size"),
            ),
        ),
        (
            Option(
                "buckets",
                "Ranges for numbers",
                "How many equal-sized ranges numbers are cut into.",
                "",
                "number",
            ),
        ),
        Table(
            rows_min=8,
            one_row_per="one row per thing predicted (an order), the target and every candidate as columns",
        ),
        Output(table=(("column", "text"), ("strength", "text"), ("cramers_v", "number"), ("p", "number"))),
        "predictors",
        {"rows": 12, "columns": ("order_id", "region", "size", "late")},
    ),
    Contract(
        "regression",
        "Model",
        "Predict a number",
        "regression",
        "How much each column moves the target, the others held steady.",
        (_TARGET, _PREDICTORS),
        (_YES,),
        Table(
            rows_min=5,
            rows_should=50,
            one_row_per="one row per thing predicted (an order), every column on it",
        ),
        Output(
            table=(
                ("term", "text"),
                ("coefficient", "number"),
                ("low", "number"),
                ("high", "number"),
                ("p", "number"),
            )
        ),
        "regression",
        {"rows": 10, "columns": ("order_id", "units", "region", "amount")},
    ),
    Contract(
        "whatif",
        "Model",
        "What if…?",
        "what-if",
        "The prediction for one row you describe, with its range (each column starts at a typical value).",
        (
            _TARGET,
            Slot(
                _PREDICTORS.key,
                _PREDICTORS.label,
                "one or more columns to set",
                _PREDICTORS.accepts,
                "many",
                _PREDICTORS.checks,
                sample=_PREDICTORS.sample,
            ),
        ),
        (_YES,),
        Table(
            rows_min=5,
            rows_should=50,
            one_row_per="one row per thing predicted (an order), every column on it",
        ),
        Output(
            table=(
                ("term", "text"),
                ("coefficient", "number"),
                ("low", "number"),
                ("high", "number"),
                ("p", "number"),
            )
        ),
        "regression",
        {"rows": 10, "columns": ("order_id", "units", "region", "amount")},
    ),
    Contract(
        "time_series",
        "Time",
        "Spot the trend and the seasons",
        "time series",
        "The trend, the season, the periods that stand out and where the level stepped.",
        (_DATE, _METRIC),
        (
            Option("period", "Each point is a", "How the dates are grouped.", "auto", choices=_PERIODS),
            Option("total", "Per period", "What each period shows of the number.", "sum", choices=_TOTALS),
        ),
        _SERIES,
        Output(table=(("period", "date"), ("value", "number"), ("trend", "number"), ("season", "number"))),
        "time_series",
        {"rows": 24, "columns": ("order_month", "amount")},
    ),
    Contract(
        "forecast",
        "Time",
        "What comes next?",
        "forecast",
        "The periods ahead with their likely ranges, checked on the last periods held back.",
        (_DATE, _METRIC),
        (
            Option("horizon", "Periods ahead", "How far ahead to forecast.", 6, "number"),
            Option("period", "Each point is a", "How the dates are grouped.", "auto", choices=_PERIODS),
            Option("total", "Per period", "What each period shows of the number.", "sum", choices=_TOTALS),
        ),
        Table(4, 24, _SERIES.one_row_per, _SERIES.series),
        Output(table=(("period", "date"), ("estimate", "number"), ("low95", "number"), ("high95", "number"))),
        "forecast",
        {"rows": 24, "columns": ("order_month", "amount")},
    ),
    Contract(
        "tie_out",
        "Compare",
        "Do two tables add up the same?",
        "tie-out",
        "Per group, whether both tables' rows and totals match, and which groups are off.",
        (Slot("other", "Against", "the table to tie out against", ("any",), sample=("ledger",)),),
        (
            Option(
                "tolerance",
                "Still ties within",
                "How far apart two totals may be and still tie.",
                0,
                "number",
            ),
        ),
        Table(
            rows_min=1,
            rows_should=1,
            one_row_per="both tables at the same grain",
            two_tables="columns of the same names: what to group by and the numbers to total",
        ),
        Output(("note", "table"), (("group", "text"), ("status", "text"))),
        "tie_out",
        {"rows": 8, "columns": ("region", "amount"), "other": ("region", "amount")},
    ),
    Contract(
        "key_finder",
        "Compare",
        "Which columns join two tables?",
        "Key Finder",
        "The column pairs that share values, how much of each side, and this table's likely key.",
        (
            Slot(
                "other",
                "Against",
                "the table to join to (or every other open table)",
                ("any",),
                "optional",
                sample=("customers",),
            ),
        ),
        (
            Option(
                "ignore_case",
                "Ignore case",
                "Count Smith and SMITH as the same value.",
                "no",
                choices=(("no", "No"), ("yes", "Yes")),
            ),
        ),
        Table(
            rows_min=1,
            rows_should=1,
            one_row_per="any two tables",
            two_tables="a column whose values the other table also has (a key)",
        ),
        Output(("note",), (("source_column", "text"), ("target_column", "text"), ("shared", "number"))),
        "key_finder",
        {"rows": 8, "columns": ("order_id", "customer_id", "amount"), "other": ("customer_id", "region")},
    ),
)
BY_ID: dict[str, Contract] = {c.id: c for c in CONTRACTS}


def every() -> dict[str, Any]:
    """Every contract as JSON, the toolbar's groups in order (analyze_contracts; the resource)."""
    return {
        "format": FORMAT,
        "groups": list(GROUPS),
        "kinds": dict(KINDS),
        "fixes": dict(FIXES),
        "contracts": [c.to_json() | {"sample": sample(c.id)} for c in CONTRACTS],
    }


def contract(contract_id: Any) -> Contract:
    found = BY_ID.get(str(contract_id))
    if found is None:
        raise KeyError(f"No analysis {contract_id!r}: one of {', '.join(BY_ID)}.")
    return found


# ===== your own analyses: an analysis blade's contract =====

BLADE = "blade:"  # an analysis blade's id on the toolbar: blade:<its name>
ANY_COLUMN: tuple[str, ...] = ("number", "whole", "date", "category", "yesno")


class ContractError(ValueError):
    """A declared contract that is not one: said with what is wrong."""


def from_json(raw: Any, contract_id: str, label: str, get: str) -> Contract:
    """A contract a blade declares (its CONTRACT dictionary): {"label"?, "name"?, "get"?, "one_row_per"?,
    "rows_min"?, "slots": [{"key", "label"?, "words"?, "accepts": [kinds], "count"?: one | many | optional
    | any, "hints"?: [words]}]}. Each slot's columns reach the blade's `columns`, in slot order."""
    if not isinstance(raw, dict):
        raise ContractError("CONTRACT is a dictionary.")
    slots: list[Slot] = []
    listed = raw.get("slots", [])
    if not isinstance(listed, list):
        raise ContractError("CONTRACT's slots is a list.")
    for entry in listed:
        if not isinstance(entry, dict) or not isinstance(entry.get("key"), str) or not entry["key"]:
            raise ContractError('Each slot is {"key": "amount", "accepts": ["number"]}.')
        key = entry["key"]
        accepts = entry.get("accepts") or list(ANY_COLUMN)
        if not isinstance(accepts, list) or not accepts or not all(k in ANY_COLUMN for k in accepts):
            raise ContractError(f"Slot {key}'s accepts is a list of {', '.join(ANY_COLUMN)}.")
        count = entry.get("count", "one")
        if count not in COUNTS:
            raise ContractError(f"Slot {key}'s count is one of {', '.join(COUNTS)}.")
        hints = entry.get("hints") or []
        if not isinstance(hints, list) or not all(isinstance(w, str) for w in hints):
            raise ContractError(f"Slot {key}'s hints is a list of words.")
        if any(s.key == key for s in slots):
            raise ContractError(f"Two slots are called {key}.")
        words = entry.get("words") or " or ".join(f"a {KINDS[k]} column" for k in accepts)
        slots.append(
            Slot(
                key,
                str(entry.get("label") or key.replace("_", " ").capitalize())[:60],
                str(words)[:200],
                tuple(accepts),
                count,
                (NOT_ID,) if entry.get("not_identifier") else (),
                tuple(w.lower() for w in hints),
                (key,),
            )
        )
    rows_min = raw.get("rows_min", 1)
    if isinstance(rows_min, bool) or not isinstance(rows_min, int) or rows_min < 0:
        raise ContractError("CONTRACT's rows_min is a whole number.")
    return Contract(
        contract_id,
        "Yours",
        str(raw.get("label") or label)[:120],
        str(raw.get("name") or "your analysis")[:60],
        str(raw.get("get") or get or "What your own analysis returns: notes, tables, pictures, figures.")[
            :300
        ],
        tuple(slots),
        (),
        Table(rows_min, rows_min, str(raw.get("one_row_per") or "whatever your analysis expects")[:200]),
        Output(("note", "table", "plotly")),
        "",
        {"rows": 8},
    )


def blade_contract(name: str, description: str, code: str) -> Contract:
    """An analysis blade's contract, read from its code and never by running it: the CONTRACT dictionary
    it declares at its top level (a literal), else what its `analyze` function takes: a `columns`
    parameter is one slot of any columns, none or more; without it, the table alone."""
    contract_id = f"{BLADE}{name}"
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        tree = ast.Module(body=[], type_ignores=[])
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(t, ast.Name) and t.id == "CONTRACT" for t in node.targets):
            try:
                declared = ast.literal_eval(node.value)
            except (ValueError, SyntaxError) as error:
                raise ContractError("CONTRACT is a plain dictionary of text, numbers and lists.") from error
            return from_json(declared, contract_id, name, description)
    takes = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "analyze":
            takes = any(a.arg == "columns" for a in [*node.args.args, *node.args.kwonlyargs])
    slots = [{"key": "columns", "label": "Columns", "count": "any", "words": "the columns it looks at"}]
    return from_json({"slots": slots if takes else []}, contract_id, name, description)


def generic_sample(c: Contract) -> dict[str, Any]:
    """A made-up sample for a contract that has none of its own (a blade's): one column per slot, named
    by the slot's key, of the first kind it accepts; an id column first."""
    columns = ["row_id"] + [s.key for s in c.slots if not s.table]
    kinds = {s.key: s.accepts[0] for s in c.slots if not s.table}
    rows: list[dict[str, Any]] = []
    for i in range(int(c.sample.get("rows") or 8)):
        row: dict[str, Any] = {"row_id": f"R-{1001 + i}"}
        for key, kind in kinds.items():
            if kind == "date":
                row[key] = (dt.date(2026, 1, 5) + dt.timedelta(days=9 * i)).isoformat()
            elif kind == "whole":
                row[key] = 2 + (i * 7) % 5
            elif kind == "number":
                row[key] = _WIDE[i % len(_WIDE)]
            elif kind == "yesno":
                row[key] = "yes" if i % 3 == 0 else "no"
            else:
                row[key] = _REGIONS[(i * 3 + i // 4) % 4]
        rows.append(row)
    return {
        "name": "sample_" + "".join(ch if ch.isalnum() else "_" for ch in c.id.removeprefix(BLADE)).lower(),
        "made_up": True,
        "columns": columns,
        "rows": rows,
        "slots": {s.key: [s.key] for s in c.slots if not s.table},
        "dates": [key for key, kind in kinds.items() if kind == "date"],
    }


# ===== the made-up sample, built from the contract =====

SAMPLE_DATES: tuple[str, ...] = ("order_month", "order_date")  # the sample columns that are dates
_REGIONS = ("West", "North", "East", "South")
_SIZES = ("small", "large", "medium")
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_VENDORS = ("Northwind", "Contoso", "Fabrikam")
# Amounts that grew naturally: first digits mostly 1 and 2, spanning 10s to 10,000s (Benford's shape).
_WIDE = (
    12.4,
    148.0,
    1890.5,
    23.75,
    310.0,
    4520.0,
    17.2,
    1210.0,
    260.3,
    31.9,
    11050.0,
    1.95,
    140.0,
    2250.0,
    19.8,
)


def _column(name: str, i: int, n: int, row: dict[str, Any]) -> Any:
    """Row i's made-up value for a sample column, by its name (deterministic, invented)."""
    if name.endswith("_id"):
        return f"{name[:1].upper()}-{1001 + i}"
    if name == "region":
        return _REGIONS[(i * 3 + i // 4) % 4]
    if name == "size":
        return _SIZES[i % 3]
    if name == "weekday":
        return _WEEKDAYS[(i * 2) % 7] if i % 5 else "Mon"
    if name == "vendor":
        return _VENDORS[i % 3]
    if name == "late":
        return "yes" if (row.get("region") in ("West", "North") and i % 3 != 2) or i % 7 == 0 else "no"
    if name == "units":
        return 2 + (i * 7) % 11
    if name == "unit_cost":
        return 88.0 if i == 5 else round(12.0 + (i % 4) * 0.35, 2)
    if name == "order_month":
        year, month = divmod(i, 12)
        return dt.date(2024 + year, month + 1, 1).isoformat()
    if name == "order_date":
        return (dt.date(2026, 1, 5) + dt.timedelta(days=9 * i)).isoformat()
    if name == "amount":
        if "units" in row:  # a model's target: the units times a price, a region's surcharge, a little noise
            surcharge = {"West": 20.0, "North": 5.0, "East": 0.0, "South": 12.0}.get(
                row.get("region", ""), 0.0
            )
            return round(row["units"] * 12.5 + surcharge + ((i * 37) % 9 - 4), 2)
        if "order_month" in row:  # a series: a trend and a summer peak
            month = i % 12
            season = {5: 1.25, 6: 1.35, 7: 1.3, 11: 1.2}.get(month, 1.0)
            return round((1000 + 22 * i) * season + (i * 53) % 40, 2)
        return _WIDE[i % len(_WIDE)]
    return f"{name} {i + 1}"


def sample(contract_id: str) -> dict[str, Any]:
    """The contract's made-up sample: {"name", "columns", "rows", "slots": {slot: columns}, "other"} (the
    second table for a two-table analysis). The same rows every time; invented values that satisfy every
    constraint; each slot's column named in "slots" so the form can highlight and label it."""
    c = BY_ID[contract_id]
    plan = c.sample
    dates = [name for name in plan.get("columns") or () if name in SAMPLE_DATES]

    def build(columns: tuple[str, ...], n: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for i in range(n):
            row: dict[str, Any] = {}
            for name in columns:
                row[name] = _column(name, i, n, row)
            rows.append(row)
        return rows

    columns = tuple(plan.get("columns") or ())
    n = int(plan.get("rows") or 8)
    out: dict[str, Any] = {
        "name": f"sample_{contract_id}",
        "made_up": True,
        "columns": list(columns),
        "rows": build(columns, n),
        "slots": {s.key: list(s.sample) for s in c.slots if s.accepts != ("any",)},
        "dates": dates,
    }
    if plan.get("other"):
        other = tuple(plan["other"])
        rows = build(other, 8 if c.id == "tie_out" else 4)
        if c.id == "tie_out":  # one group off by a little: something to see
            rows[3] = rows[3] | {"amount": round(float(rows[3]["amount"]) + 25.0, 2)}
        out["other"] = {"name": f"sample_{contract_id}_other", "columns": list(other), "rows": rows}
    return out
