"""`${NAME}`: a variable anywhere a value is typed (design principle 12.7; the owner, 2026-11-18: "a reserved
char that allows us to use env variable almost anywhere in the app" / "Let's do it. ${ it is").

  a reference  exactly `${` + NAME + `}`, NAME a letter or `_` then letters, digits and `_`; or
               `${NAME:-default}`, the default literal text up to the first `}` (no nesting)
  as typed     everything else: `pa$$word`, `Sheet1$`, `[Orders$]`, `${not a name}`, `${ X}`, `${}`
  the escape   `$${NAME}` is the literal text `${NAME}` (one `$` kept); `escape` writes a literal back so
               that reading it again gives the same text
  one pass     only typed text is read: a value that came from a variable is put in exactly as stored, and
               nothing is expanded twice
  SQL          a reference outside quoted strings, quoted names and comments becomes a bound parameter in
               the driver's own style (PEP 249's paramstyle, DuckDB's `$1`); never pasted into the text. One
               that stands where a name goes (after FROM, JOIN, INTO, AS, beside a `.`, glued to a name) is
               refused: a name cannot be a parameter
  Python       the export form: `os.environ["NAME"]`, `os.environ.get("NAME", "default")`, joined to the
               text around it with `+` (no f-string); read back from the same shapes (ast)
  missing      one error: "NAME is not set on this computer", with Set it (MissingVariables)

Standard library only, so the plain client (a %%sql cell in any Python) reads references by the same rules.
The SQL scanner is our own: it keeps the positions of strings and comments, which sqlglot's tokenizer drops,
and the client cannot count on sqlglot (tests/test_variable_refs.py checks it against sqlglot's tokens).
Pure rules: no I/O.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_REF = re.compile(r"(?P<escape>\$)?\$\{(?P<name>" + NAME + r")(?::-(?P<default>[^}]*))?\}")
_NAME = re.compile(rf"^{NAME}$")


@dataclass(frozen=True)
class Ref:
    """One reference in a text: its name, its default (None: none given), and where it stands."""

    name: str
    default: str | None
    start: int
    end: int

    @property
    def text(self) -> str:
        return f"${{{self.name}}}" if self.default is None else f"${{{self.name}:-{self.default}}}"


Part = str | Ref


def parts(text: str) -> list[Part]:
    """The text as literal pieces (an escape already made its one `$`) and references, in order. Two
    literal pieces never stand side by side."""
    out: list[Part] = []
    at = 0

    def literal(piece: str) -> None:
        if not piece:
            return
        if out and isinstance(out[-1], str):
            out[-1] += piece
        else:
            out.append(piece)

    for match in _REF.finditer(text):
        literal(text[at : match.start()])
        if match.group("escape"):
            literal(match.group(0)[1:])  # $${NAME} -> ${NAME}
        else:
            out.append(Ref(match.group("name"), match.group("default"), match.start(), match.end()))
        at = match.end()
    literal(text[at:])
    return out


def find(text: str) -> list[Ref]:
    """The references in a text, in order (an escaped one is not a reference)."""
    return [p for p in parts(text) if isinstance(p, Ref)]


def names(text: str) -> list[str]:
    """The variables a text names, each once, in order."""
    return list(dict.fromkeys(r.name for r in find(text)))


def holds(text: Any) -> bool:
    """Whether a text names a variable."""
    return isinstance(text, str) and "${" in text and bool(find(text))


def literal(text: str) -> str | None:
    """The text as it is used when it names no variable (escapes made one `$`); None when it names one."""
    found = parts(text)
    pieces = [p for p in found if isinstance(p, str)]
    if len(pieces) != len(found):
        return None
    return pieces[0] if pieces else ""


def escape(value: str) -> str:
    """A literal value as a box shows it: each `${` that would read as a reference (or an escape) gets a
    second `$`, so `parts(escape(v)) == [v]`."""
    return _REF.sub(lambda m: "$" + m.group(0), value) if "${" in value else value


def is_name(name: Any) -> bool:
    return isinstance(name, str) and bool(_NAME.match(name))


# ===== resolved: a value, or the one missing error =====


class MissingVariables(ValueError):
    """Variables a text names that this computer does not set (and that give no default). 9.5's shape:
    what happened, where, the fix (Set it, on the Variables page, for that name)."""

    def __init__(self, missing: Iterable[str], where: str = "") -> None:
        self.missing = list(dict.fromkeys(missing))
        self.where = where
        super().__init__(missing_words(self.missing, where))

    def to_json(self) -> dict[str, Any]:
        return {
            "error": str(self),
            "where": self.where,
            "missing_variables": self.missing,
            "fixes": [
                {
                    "label": "Set it",
                    "action": "set_variable",
                    "command": "variables_set",
                    "page": "variables",
                    "name": name,
                }
                for name in self.missing
            ],
        }


def missing_words(missing: list[str], where: str = "") -> str:
    if not missing:
        return ""
    if len(missing) == 1:
        said = f"{missing[0]} is not set on this computer"
    else:
        said = f"{', '.join(missing[:-1])} and {missing[-1]} are not set on this computer"
    return f"{said} ({where})." if where else f"{said}."


Lookup = Callable[[str], str | None]


def lookup_in(values: Mapping[str, str]) -> Lookup:
    return values.get


def unresolved(text: str, lookup: Lookup) -> list[str]:
    """The names a text needs that the lookup does not give and that have no default."""
    return list(dict.fromkeys(r.name for r in find(text) if r.default is None and lookup(r.name) is None))


def value_of(ref: Ref, lookup: Lookup) -> str | None:
    found = lookup(ref.name)
    return found if found is not None else ref.default


def resolve(text: str, lookup: Lookup, where: str = "") -> str:
    """The text with each reference's value put in, in one pass (a value is never read again). Raises
    MissingVariables naming every variable not set here that gives no default."""
    if "${" not in text:
        return text
    missing = unresolved(text, lookup)
    if missing:
        raise MissingVariables(missing, where)
    out = []
    for part in parts(text):
        if isinstance(part, str):
            out.append(part)
        else:
            value = value_of(part, lookup)
            out.append("" if value is None else value)
    return "".join(out)


def resolve_all(values: Mapping[str, Any], lookup: Lookup, where: str = "") -> dict[str, Any]:
    """Each text value of a mapping resolved (others as they are); every missing name said at once."""
    missing: list[str] = []
    for value in values.values():
        if isinstance(value, str):
            missing += unresolved(value, lookup)
    if missing:
        raise MissingVariables(missing, where)
    return {k: resolve(v, lookup, where) if isinstance(v, str) else v for k, v in values.items()}


def preview(text: str, lookup: Lookup, secret: Callable[[str], bool]) -> dict[str, Any]:
    """What a box resolves to here, for the box's line and the agent: the text, the value with each secret's
    part masked (never its value), and the names not set. {"text", "value", "masked", "missing", "names"}."""
    missing = unresolved(text, lookup)
    out: list[str] = []
    masked = False
    for part in parts(text):
        if isinstance(part, str):
            out.append(part)
            continue
        value = value_of(part, lookup)
        if part.name in missing:
            out.append(part.text)
        elif secret(part.name) and lookup(part.name) is not None:
            out.append("••••••••")
            masked = True
        else:
            out.append("" if value is None else value)
    answer: dict[str, Any] = {
        "text": text,
        "names": names(text),
        "value": "".join(out),
        "masked": masked,
        "missing": missing,
    }
    if missing:
        answer["error"] = MissingVariables(missing).to_json()
    return answer


# ===== a vault's secret names as variables =====


def env_name_for_secret(secret: str) -> str:
    """A secret's variable, named as in the vault: SqlPassword stays SqlPassword, Sql--Password becomes
    Sql__Password (Azure's convention for a section: `--` in the vault, `__` in the environment), any
    other character a variable cannot hold becomes _ (warehouse-password -> warehouse_password,
    op://Private/Warehouse/password -> Private_Warehouse_password). Case is kept."""
    bare = re.sub(r"^[a-z][a-z0-9+.-]*://", "", secret.strip(), flags=re.IGNORECASE)
    words = re.sub(r"[^A-Za-z0-9_]", "_", bare.replace("--", "__")).strip("_")[:128] or "SECRET"
    return words if not words[0].isdigit() else f"_{words}"[:128]


def every_secret(names: Iterable[str], renamed: Mapping[str, str]) -> dict[str, str]:
    """A vault's mapping when it loads every secret: each name its own variable, but a secret the user
    renamed (`renamed`: variable -> secret) keeps that name. Variable -> secret."""
    by_secret = {secret: env for env, secret in renamed.items()}
    found: dict[str, str] = {}
    for name in names:
        if name not in by_secret:
            found.setdefault(env_name_for_secret(name), name)
    return found | dict(renamed)


# ===== the export form: Python that reads the variables where it runs =====


def _quoted(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def python_expr(text: str, quote: Callable[[str], str] = _quoted) -> str:
    """Python for a typed value: a string literal when it names no variable; else `os.environ["NAME"]`
    (`os.environ.get("NAME", "default")` with a default) joined to the text around it by `+`. `quote`
    writes a literal piece (a raw string for a path, where the caller wants one)."""
    pieces = []
    for part in parts(text):
        if isinstance(part, str):
            pieces.append(quote(part))
        elif part.default is None:
            pieces.append(f"os.environ[{_quoted(part.name)}]")
        else:
            pieces.append(f"os.environ.get({_quoted(part.name)}, {quote(part.default)})")
    return " + ".join(pieces) if pieces else quote("")


def _is_os_environ(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _string(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def env_read(node: ast.expr) -> tuple[str, str | None] | None:
    """`os.environ["NAME"]` -> (NAME, None); `os.environ.get("NAME", "d")` or `os.getenv("NAME", "d")` ->
    (NAME, "d"); a one-argument get -> (NAME, None). Else None."""
    if isinstance(node, ast.Subscript) and _is_os_environ(node.value):
        name = _string(node.slice)
        return (name, None) if name and is_name(name) else None
    if not isinstance(node, ast.Call) or node.keywords or not 1 <= len(node.args) <= 2:
        return None
    func = node.func
    getter = isinstance(func, ast.Attribute) and (
        (func.attr == "get" and _is_os_environ(func.value))
        or (func.attr == "getenv" and isinstance(func.value, ast.Name) and func.value.id == "os")
    )
    name = _string(node.args[0])
    if not getter or not name or not is_name(name):
        return None
    if len(node.args) == 1:
        return name, None
    default = _string(node.args[1])
    return (name, default) if default is not None and "}" not in default else None


def from_python(node: ast.expr | None) -> str | None:
    """The typed text an expression written by `python_expr` reads as: a string literal (escaped), a
    variable read, or `+` of those. None for any other expression."""
    if node is None:
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = from_python(node.left), from_python(node.right)
        if left is None or right is None:
            return None
        if not (_has_read(node.left) or _has_read(node.right)):
            return None  # "a" + "b": not ours
        return left + right
    text = _string(node)
    if text is not None:
        return escape(text)
    read = env_read(node)
    if read is None:
        return None
    name, default = read
    return f"${{{name}}}" if default is None else f"${{{name}:-{escape(default)}}}"


def setting_read(node: ast.expr) -> tuple[str, bool] | None:
    """A connection's setting written as the variables it reads: `from_python`'s shapes, or int(...) /
    float(...) of one for a number. (the box's text, a number?), or None when it names no variable."""
    number = (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in ("int", "float")
        and len(node.args) == 1
        and not node.keywords
    )
    inner = node.args[0] if number and isinstance(node, ast.Call) else node
    text = from_python(inner)
    if text is None or not holds(text) or "\n" in text:
        return None
    return text, number


def setting_code(text: str, key: str, quote: Callable[[str], str], number: str | None = None) -> str:
    """The code for a setting whose box names variables: `python_expr`, inside int(...) or float(...) for
    a number (`number`: "int" or "float")."""
    if "\n" in text:
        raise ValueError(f"{key} is one line of text.")
    expr = python_expr(text, quote)
    return f"{number}({expr})" if number else expr


def _has_read(node: ast.expr) -> bool:
    if isinstance(node, ast.BinOp):
        return _has_read(node.left) or _has_read(node.right)
    return env_read(node) is not None


# ===== SQL: a reference is a bound parameter, never pasted text =====

# PEP 249's paramstyle, and DuckDB's own `$1`.
STYLES = ("qmark", "numeric", "named", "format", "pyformat", "dollar")
_BACKSLASH_DIALECTS = frozenset({"mysql", "mariadb", "bigquery", "spark", "databricks", "hive", "clickhouse"})
_BRACKET_DIALECTS = frozenset({"tsql", "duckdb", "dataverse", "fabric", "sqlserver", "access", "odbc"})
_DOLLAR_DIALECTS = frozenset({"postgres", "duckdb", "redshift", "snowflake", None, ""})
_HASH_COMMENT = frozenset({"mysql", "mariadb", "bigquery", "hive"})
# A name follows these words: a parameter cannot stand there.
_NAME_BEFORE = frozenset(
    {"from", "join", "into", "update", "table", "as", "view", "schema", "database", "use"}
)


class SqlRefError(ValueError):
    """A reference that cannot be a bound parameter where it stands (a table's or a column's name)."""


@dataclass(frozen=True)
class BoundSql:
    """The SQL with each reference a placeholder, and the references in placeholder order."""

    sql: str
    refs: tuple[Ref, ...]
    style: str

    def params(self, lookup: Lookup, where: str = "") -> list[str] | dict[str, str]:
        """The values in order (a named style: by name). Raises MissingVariables."""
        missing = list(
            dict.fromkeys(r.name for r in self.refs if r.default is None and lookup(r.name) is None)
        )
        if missing:
            raise MissingVariables(missing, where)
        values = [value_of(r, lookup) or "" for r in self.refs]
        if self.style in ("named", "pyformat"):
            return {f"p{i}": v for i, v in enumerate(values, start=1)}
        return values


def _spans(sql: str, dialect: str | None) -> list[tuple[int, int]]:
    """Where the SQL's quoted strings, quoted names and comments are: (start, end) each."""
    spans: list[tuple[int, int]] = []
    d = (dialect or "").lower()
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if (c == "-" and sql.startswith("--", i)) or (c == "#" and d in _HASH_COMMENT):
            end = sql.find("\n", i)
            end = n if end < 0 else end
            spans.append((i, end))
            i = end
            continue
        if c == "/" and sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            end = n if end < 0 else end + 2
            spans.append((i, end))
            i = end
            continue
        if c in "'\"`":
            j = i + 1
            while j < n:
                if sql[j] == "\\" and c != "`" and d in _BACKSLASH_DIALECTS:
                    j += 2
                    continue
                if sql[j] == c:
                    if j + 1 < n and sql[j + 1] == c:  # '' inside a string
                        j += 2
                        continue
                    break
                j += 1
            spans.append((i, min(j + 1, n)))
            i = j + 1
            continue
        if c == "[" and d in _BRACKET_DIALECTS:
            end = sql.find("]", i + 1)
            end = n if end < 0 else end + 1
            spans.append((i, end))
            i = end
            continue
        if c == "$" and d in _DOLLAR_DIALECTS:
            tag = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", sql[i:])
            if tag:
                end = sql.find(tag.group(0), i + len(tag.group(0)))
                end = n if end < 0 else end + len(tag.group(0))
                spans.append((i, end))
                i = end
                continue
        i += 1
    return spans


_SENTINEL = "\x00"


def bind_sql(sql: str, dialect: str | None = "duckdb", style: str = "dollar") -> BoundSql:
    """The SQL with each reference outside strings, quoted names and comments as a placeholder of `style`
    (inside one it stays as typed; `$${X}` is the text `${X}`). Raises SqlRefError for a reference where a
    name goes. With format or pyformat, each `%` of the text is doubled, as those drivers read it."""
    if style not in STYLES:
        raise ValueError(f"style is one of {', '.join(STYLES)}.")
    plain = literal(sql)
    if plain is not None:
        return BoundSql(plain, (), style)
    pieces = parts(sql)
    # The text with each reference as one sentinel character pair, so the scanner sees it in place.
    masked: list[str] = []
    refs: list[Ref] = []
    for part in pieces:
        if isinstance(part, str):
            masked.append(part.replace(_SENTINEL, " "))
        else:
            masked.append(f"{_SENTINEL}{len(refs)}{_SENTINEL}")
            refs.append(part)
    text = "".join(masked)
    inside = _spans(text, dialect)
    out: list[str] = []
    bound: list[Ref] = []
    at = 0
    for match in re.finditer(rf"{_SENTINEL}(\d+){_SENTINEL}", text):
        ref = refs[int(match.group(1))]
        start, end = match.span()
        quoted = any(s <= start < e for s, e in inside)
        out.append(_percent(text[at:start], style))
        if quoted:
            out.append(_percent(ref.text, style) if style in ("format", "pyformat") else ref.text)
        else:
            _check_value_place(text, start, end, ref)
            bound.append(ref)
            out.append(_placeholder(style, len(bound)))
        at = end
    out.append(_percent(text[at:], style))
    return BoundSql("".join(out), tuple(bound), style)


def _percent(text: str, style: str) -> str:
    return text.replace("%", "%%") if style in ("format", "pyformat") else text


def _placeholder(style: str, n: int) -> str:
    return {
        "qmark": "?",
        "numeric": f":{n}",
        "named": f":p{n}",
        "format": "%s",
        "pyformat": f"%(p{n})s",
        "dollar": f"${n}",
    }[style]


def _check_value_place(text: str, start: int, end: int, ref: Ref) -> None:
    before = text[:start]
    after = text[end:]
    glued = (before[-1:].isalnum() or before[-1:] in ("_", ".", '"', "]", "`")) or (
        after[:1].isalnum() or after[:1] in ("_", ".", "(", '"', "[", "`")
    )
    word = re.search(r"([A-Za-z_]+)\s*$", before)
    if glued or (word and word.group(1).lower() in _NAME_BEFORE):
        raise SqlRefError(
            f"{ref.text} stands where a table's or a column's name goes: a variable is sent as a value, "
            "never pasted into the query, so it cannot name a table or a column."
        )


def paramstyle_of(module: Any) -> str:
    """A DB-API module's paramstyle (qmark when it does not say)."""
    style = getattr(module, "paramstyle", "qmark")
    return style if style in STYLES else "qmark"


# ===== saved items that already hold the pattern (the first start's list) =====


def holding(items: Iterable[tuple[str, str]]) -> list[dict[str, Any]]:
    """Of (where, text) pairs, those whose text now reads as naming a variable: {"where", "names"}."""
    out = []
    for where, text in items:
        if holds(text):
            out.append({"where": where, "names": names(text)})
    return out
