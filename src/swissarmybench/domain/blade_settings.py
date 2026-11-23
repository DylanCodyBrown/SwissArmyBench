"""A blade's settings: the values in its code a person fills in (a server, a database, a path, a flag),
found with `ast` and never by running it, and a value written back into only its own characters.

Moved out of domain/blades.py (2026-11-22, the craft review: blades.py sat at its 1,500-line ceiling and
this part changes for its own reason, the connection forms); blades.py re-exports every public name here, so
`from swissarmybench.domain.blades import detect_settings` reads as before.

  detect_settings(code)          every setting in the code, in the order it is written
  apply_settings(code, values)   the code with those values written in (a `${NAME}` as os.environ)
  env_settings(code)             the settings that read an environment variable (an export's, Run settings')
  is_placeholder(value)          a value still to be filled in (<server>, YOUR_SERVER)
  parse_code, BladeCodeError     the code read as Python, or the line that cannot be (here because this
                                 module and blades.py both read code, and blades.py imports this one)
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Any

from swissarmybench.domain import certificate_files, sql_server
from swissarmybench.domain import variable_refs as refs


class BladeCodeError(ValueError):
    """The code cannot be read as Python. The message gives the line."""


def parse_code(code: str, label: str = "the blade") -> ast.Module:
    try:
        return ast.parse(code, filename=label)
    except SyntaxError as error:
        where = f" on line {error.lineno}" if error.lineno else ""
        raise BladeCodeError(f"{label} is not valid Python{where}: {error.msg}.") from error


# ===== the settings =====
# The values a blade's code is written with that each person fills in for themselves: its settings.
#
# A blade from someone else says `host="their-server"` or `"Server=their-server;Database=sales;"`.
# These are read from the code with `ast` (never run), so the import review and the save screen can show
# one field per setting, flag the ones that are still placeholders (`my-server`, `<your host>`,
# `example`), suggest values (the user's other blades, a few standard environment variables), and write a
# new value back into exactly that place in the code.
#
# What counts as a setting:
#
# - a keyword argument whose name is a connection setting (`host=`, `port=`, `dbname=`, `user=`,
#   `account=`, `warehouse=`, `http_path=`, `vault_url=`, ...) given a literal: `host="my-server"`;
# - a top-level name given a literal or a path: `project = "my-project"`,
#   `path = Path(r"C:\data\orders.csv")`;
# - a path given as the first argument of a call: `duckdb.connect(r"C:\data\shop.duckdb")`;
# - a `Key=value;` part of a connection string: `"Server=my-server;Database=my_database;"`.
#
# Passwords, tokens and keys are never settings: they belong in `secret("...")`. Standard library only.

# Keyword arguments that hold a connection setting, and the plain name each is shown and matched as.
KEYWORDS: dict[str, str] = {
    "host": "server",
    "hostname": "server",
    "server": "server",
    "server_hostname": "server",
    "address": "server",
    "port": "port",
    "database": "database",
    "dbname": "database",
    "db": "database",
    "user": "user",
    "username": "user",
    "account": "account",
    "warehouse": "warehouse",
    "schema": "schema",
    "role": "role",
    "catalog": "catalog",
    "http_path": "http path",
    "dsn": "data source",
    "project": "project",
    "region_name": "region",
    "region": "region",
    "vault_url": "vault address",
    "url": "address",
    "base_url": "address",
    "service_name": "service",
    "sid": "service",
    # Encryption (SSL/TLS): the scheme, and the certificate authority's file (.pem) the client trusts.
    "http_scheme": "scheme",
    "verify": "certificate file",
    "sslrootcert": "certificate file",
    "ssl_ca": "certificate file",
    "ca": "certificate file",
    "sslmode": "encryption",
    "trust_server_certificate": "trust server certificate",
    # A client certificate's files: a keystore (Trino's second way to sign in), or a certificate and key.
    "keystore": "keystore",
    "sslcert": "client certificate file",
    "ssl_cert": "client certificate file",
    "sslkey": "client key file",
    "ssl_key": "client key file",
    **sql_server.KEYWORDS,  # SQL Server's options, and an app registration's ids
}
# The parts of a connection string (ODBC, DB2, OLE DB) that are settings, by their key ignoring case.
CONNECTION_KEYS: dict[str, str] = {
    "server": "server",
    "hostname": "server",
    "host": "server",
    "data source": "server",
    "address": "server",
    "port": "port",
    "database": "database",
    "initial catalog": "database",
    "uid": "user",
    "user id": "user",
    "dsn": "data source",
    "dbq": "path",
    "driver": "driver",
    "trustservercertificate": "trust server certificate",
    "encrypt": "encrypt",
}
# Settings that are on or off (a checkbox): True/False in code, yes/no in a connection string.
FLAGS = frozenset({"trust server certificate", "encrypt"}) | sql_server.FLAGS
# Never a setting, wherever it appears: these belong in secret("...").
_SECRET_WORDS = re.compile(r"pass|pwd|token|secret|credential|api_?key|private", re.IGNORECASE)
# The first argument of these calls is a file or folder.
_PATH_CALLS = frozenset(
    "Path connect open read_csv read_excel read_parquet read_json read_table read_feather dotenv_values "
    "load_workbook ExcelFile".split()
)
_PLACEHOLDER = re.compile(
    r"(^|[^a-z])(my|your)([-_ .]|$)|example|<[^>]*>|\{\{|change[-_ ]?me|xxx|abc123|1234567890|placeholder",
    re.IGNORECASE,
)
_LOOKS_LIKE_PATH = re.compile(r"^([a-z]:[\\/]|[\\/]|~|\.{1,2}[\\/])|[\\/].*\.[a-z0-9]{1,8}$", re.IGNORECASE)
_PAIR = re.compile(r"(?:^|;)\s*([A-Za-z][A-Za-z ]*?)\s*=\s*([^;]*)")


class FillError(ValueError):
    """A value that cannot be written into the code as it stands. The message says why."""


@dataclass
class Setting:
    """One value in the code a person may need to change."""

    id: str  # where it is in this code: "<start>:<end>"; changes when the code does
    name: str  # what it is: "server", "database", "path", or the code's own name
    key: str  # as the code writes it: host, Server, path, project...
    value: str | int | float | bool
    line: int
    where: str  # keyword, name, argument or connection string
    placeholder: bool  # still a stand-in such as my-server: it needs the person's own value
    suggestions: list[dict[str, str]] = field(default_factory=list)  # {"value", "from"}
    env: str | None = None  # read from this variable (value: its default); a file says always, others mapped
    # What the setting's one box holds (design principle 12.7): its value with `${NAME}` for each variable
    # it reads (`${NAME:-default}`), a literal `${` escaped as `$${`. None for an on/off.
    text: str | None = None
    number: bool = False  # a number in the code (a variable read as int(...) still is)

    def __post_init__(self) -> None:
        if self.text is None and self.env:  # os.environ.get("NAME", "this computer's path")
            self.text = "${" + self.env + ":-" + refs.escape(str(self.value)) + "}"
        elif self.text is None and not isinstance(self.value, bool):
            self.text = refs.escape(self.value) if isinstance(self.value, str) else str(self.value)
            self.number = not isinstance(self.value, str)

    def to_json(self) -> dict[str, Any]:
        mappable = {"env": self.env} if certificate_files.says_source(self.name, self.env) else {}
        mappable |= {"text": self.text} if self.text is not None else {}
        return mappable | {
            "id": self.id,
            "name": self.name,
            "key": self.key,
            "value": self.value,
            "type": "flag" if self.name in FLAGS else "number" if self.number else "text",
            "line": self.line,
            "where": self.where,
            "placeholder": self.placeholder,
            "suggestions": self.suggestions,
        }


@dataclass(frozen=True)
class _Found:
    setting: Setting
    start: int  # character offsets of what a new value replaces, in the code
    end: int
    raw: bool  # a raw string literal (r"..."): paths keep their backslashes as written
    inside_string: bool  # a Key=value part: the value is text inside a larger string literal
    # (an environment variable's form: start and end span the whole os.environ.get(...) call)


def is_placeholder(value: object) -> bool:
    return isinstance(value, str) and bool(_PLACEHOLDER.search(value))


def _lines(code: str) -> list[str]:
    """The code's lines as ast counts them: split on newlines only (splitlines also splits on form
    feeds and other characters, which would shift every position after one)."""
    parts = code.split("\n")
    return [part + "\n" for part in parts[:-1]] + [parts[-1]]


def _offsets(code: str) -> list[int]:
    """The character offset where each line starts (ast gives byte columns; the code may hold é)."""
    starts, total = [0], 0
    for line in _lines(code):
        total += len(line)
        starts.append(total)
    return starts


def _char(code_lines: list[str], starts: list[int], line: int, byte_col: int) -> int:
    text = code_lines[line - 1] if line - 1 < len(code_lines) else ""
    return starts[line - 1] + len(text.encode("utf-8")[:byte_col].decode("utf-8", "replace"))


def _literal(node: ast.expr | None) -> ast.Constant | None:
    """A str, int or float literal (not a bool or None), or Path(<str literal>)'s argument."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str | int | float):
        return None if isinstance(node.value, bool) else node
    if (
        isinstance(node, ast.Call)
        and _call_name(node) == "Path"
        and len(node.args) == 1
        and not node.keywords
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0]
    return None


def _flag(node: ast.expr | None, name: str | None) -> ast.Constant | None:
    """A True/False literal for an on/off setting (FLAGS); other booleans are never settings."""
    if name in FLAGS and isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node
    return None


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def detect_settings(code: str) -> list[Setting]:
    """Every setting in the code, in the order it is written. Raises BladeCodeError for code that is
    not Python."""
    return [replace(f.setting, suggestions=list(f.setting.suggestions)) for f in _detect(code)]


@lru_cache(maxsize=1024)
def _detect(code: str) -> tuple[_Found, ...]:
    """Every setting with where it is. Kept by the text: read only (detect_settings hands out copies).
    Two passes over the tree: the top-level names first (a name labels its own value), then every call's
    keywords and path arguments and every connection string."""
    finder = _Finder(code)
    tree = parse_code(code)
    finder.names(tree)
    finder.calls(tree)
    return tuple(sorted(finder.found.values(), key=lambda f: f.start))


class _Finder:
    """One code's settings as they are found, each by its place (start, end) in the text: the first to
    claim a place keeps it."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.lines = _lines(code)
        self.starts = _offsets(code)
        self.found: dict[tuple[int, int], _Found] = {}

    def span(self, node: ast.expr) -> tuple[int, int]:
        """A node's place in the text (it has its end: the caller checked)."""
        start = _char(self.lines, self.starts, node.lineno, node.col_offset)
        return start, _char(self.lines, self.starts, node.end_lineno or 0, node.end_col_offset or 0)

    def add(self, node: ast.Constant, name: str, key: str, where: str) -> None:
        none = key in certificate_files.VARIABLE_ONLY and node.value == ""  # a password's variable: none
        if (_SECRET_WORDS.search(key) and not none) or node.end_lineno is None or node.end_col_offset is None:
            return
        start, end = self.span(node)
        source = self.code[start:end]
        if isinstance(node.value, str):
            if "\n" in node.value or len(node.value) > 500 or not _plain_string(source):
                return  # an f-string piece, a multi-line text or a joined string: not a single value
            if where != "connection string" and _pairs(node.value):
                self.add_pairs(node, start, end)
                return
        value = node.value
        if (start, end) in self.found or not isinstance(value, str | int | float):
            return
        self.found[(start, end)] = _Found(
            Setting(f"{start}:{end}", name, key, value, node.lineno, where, is_placeholder(value)),
            start,
            end,
            source.lstrip("bBuU")[:1] in ("r", "R"),
            False,
        )

    def add_refs(self, node: ast.expr, name: str, key: str, where: str) -> bool:
        """A setting written as the variables it reads (12.7; variable_refs.setting_read): its value is
        the box's text. False when the expression is not one of those."""
        read = refs.setting_read(certificate_files.unwrapped(node))  # certificate_file(os.environ[...]) too
        if (
            read is None
            or (_SECRET_WORDS.search(key) and key not in certificate_files.VARIABLE_ONLY)
            or node.end_lineno is None
            or node.end_col_offset is None
        ):
            return False
        text, number = read
        start, end = self.span(node)
        if (start, end) in self.found or "\n" in text:
            return True
        written = self.code[start:end]
        self.found[(start, end)] = _Found(
            Setting(f"{start}:{end}", name, key, text, node.lineno, where, False, text=text, number=number),
            start,
            end,
            'r"' in written or "r'" in written,
            False,
        )
        return True

    def add_env(
        self, call: ast.expr, variable: str, default: ast.Constant, name: str, key: str, where: str
    ) -> None:
        """A certificate or keystore file read from an environment variable, its path the default."""
        if call.end_lineno is None or call.end_col_offset is None or default.end_lineno is None:
            return
        start, end = self.span(call)
        default_source = self.code[slice(*self.span(default))]
        value = str(default.value)
        if (start, end) in self.found or "\n" in value or not _plain_string(default_source):
            return
        self.found[(start, end)] = _Found(
            Setting(
                f"{start}:{end}", name, key, value, call.lineno, where, is_placeholder(value), env=variable
            ),
            start,
            end,
            default_source.lstrip("bBuU")[:1] in ("r", "R"),
            False,
        )

    def add_pairs(self, node: ast.Constant, start: int, end: int) -> None:
        """A connection string's known parts, each a setting of its own at its value's place."""
        source = self.code[start:end]
        for match in _PAIR.finditer(str(node.value)):
            key, value = match.group(1).strip(), match.group(2).strip()
            name = CONNECTION_KEYS.get(key.casefold())
            if name is None or not value or _SECRET_WORDS.search(key):
                continue
            spot, written, raw = _pair_written(source, key, value)
            if spot is None:
                continue
            value_start = start + spot.end() - len(written)
            pair_key = (value_start, value_start + len(written))
            if pair_key in self.found:
                continue
            self.found[pair_key] = _Found(
                Setting(
                    f"{pair_key[0]}:{pair_key[1]}",
                    name,
                    key,
                    value,
                    node.lineno + source[: spot.start()].count("\n"),
                    "connection string",
                    is_placeholder(value),
                ),
                pair_key[0],
                pair_key[1],
                raw,
                True,
            )

    def add_pairs_of(self, node: ast.Constant) -> None:
        """A string's connection string, where the string's end is known."""
        if node.end_lineno is not None and node.end_col_offset is not None:
            self.add_pairs(node, *self.span(node))

    def names(self, tree: ast.Module) -> None:
        """First: a top-level name labels its own value (path = Path(...))."""
        for statement in tree.body:
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                target, value = statement.targets[0], statement.value
            elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
                target, value = statement.target, statement.value
            else:
                continue  # not one value's assignment (a chained a = b = "x", a call, an import)
            if getattr(target, "id", "").startswith("_"):
                continue  # a private constant: the code's own, never a setting
            mapped = certificate_files.env_default(value)
            if isinstance(target, ast.Name) and mapped is not None:
                word = certificate_files.plain_name(target.id, KEYWORDS)
                if certificate_files.mappable(word):
                    self.add_env(value, mapped[0], mapped[1], word, target.id, "name")
                    continue
            if isinstance(target, ast.Name) and value is not None:
                known = certificate_files.plain_name(target.id, KEYWORDS)
                if self.add_refs(value, known or target.id, target.id, "name"):
                    continue
            if mapped is not None:
                continue
            literal = _literal(value)
            if isinstance(target, ast.Name):
                literal = literal or _flag(value, KEYWORDS.get(target.id.casefold()))
            if isinstance(target, ast.Name) and literal is not None:
                # A known setting's own word first (verify = r"...pem" is a certificate file, not any path).
                known = certificate_files.plain_name(target.id, KEYWORDS)
                name = (
                    known
                    if known
                    else "path"
                    if isinstance(literal.value, str) and _LOOKS_LIKE_PATH.search(literal.value)
                    else target.id
                )
                self.add(literal, name, target.id, "name")

    def calls(self, tree: ast.Module) -> None:
        """Then every call's keywords and path argument, and every string that is a connection string."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                self.keywords(node)
                if node.args and _call_name(node) in _PATH_CALLS:
                    literal = _literal(node.args[0])
                    if literal is not None and isinstance(literal.value, str):
                        if _LOOKS_LIKE_PATH.search(literal.value):
                            self.add(literal, "path", _call_name(node), "argument")
                        elif _pairs(literal.value, least=1) and literal.end_lineno and literal.end_col_offset:
                            self.add_pairs(literal, *self.span(literal))
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _pairs(node.value):
                self.add_pairs_of(node)

    def keywords(self, node: ast.Call) -> None:
        for keyword in node.keywords:
            word = KEYWORDS.get(keyword.arg.casefold()) if keyword.arg else None
            mapped = certificate_files.env_default(keyword.value)
            if keyword.arg and certificate_files.mappable(word) and mapped is not None:
                self.add_env(keyword.value, mapped[0], mapped[1], word, keyword.arg, "keyword")
                continue
            if word and keyword.arg and self.add_refs(keyword.value, word, keyword.arg, "keyword"):
                continue
            literal = _literal(keyword.value) or _flag(keyword.value, word)
            if keyword.arg and literal is not None and keyword.arg.casefold() in KEYWORDS:
                self.add(literal, KEYWORDS[keyword.arg.casefold()], keyword.arg, "keyword")


def _pair_written(source: str, key: str, value: str) -> tuple[re.Match[str] | None, str, bool]:
    """Where a connection string's part's value is written in the source, after "Key=": as parsed in a raw
    string, with each backslash doubled in a plain one (Server=db01\\\\SQLEXPRESS). (None, ...) when it is
    written some other way: anything else is left alone."""
    spot, written, raw = None, value, False
    for candidate in dict.fromkeys((value, value.replace("\\", "\\\\"))):
        spot = re.search(rf"(?<![A-Za-z]){re.escape(key)}\s*=\s*{re.escape(candidate)}(?=\s*[;\"'])", source)
        if spot is None:
            continue
        quote = max(source.rfind('"', 0, spot.start()), source.rfind("'", 0, spot.start()))
        raw = quote > 0 and source[quote - 1] in "rR"
        if "\\" not in value or raw == (candidate == value):
            written = candidate
            break
        spot = None
    return spot, written, raw


def _pairs(text: str, least: int = 2) -> bool:
    """A connection string: `least` or more Key=value parts, at least one a known setting. One part is
    enough for the string a connect call is given ("DSN=sales")."""
    pairs = [m.group(1).strip().casefold() for m in _PAIR.finditer(text)]
    return len(pairs) >= least and any(p in CONNECTION_KEYS for p in pairs)


def _plain_string(source: str) -> bool:
    """One string literal (not implicit concatenation, not an f-string or bytes), or a number."""
    if not source or source[0].isdigit() or source[0] in "-.":
        return True
    prefix = re.match(r"[A-Za-z]*", source)
    letters = (prefix.group(0) if prefix else "").casefold()
    if set(letters) - {"r", "u"}:
        return False
    body = source[len(letters) :]
    quote = body[:3] if body[:3] in ('"""', "'''") else body[:1]
    return body.endswith(quote) and quote not in body[len(quote) : -len(quote)]


# ===== writing a value back =====


def _string_literal(value: str, raw: bool) -> str:
    """Python text for the value: a raw string for a path when it can be one, else a quoted string."""
    if raw and '"' not in value and "\n" not in value and not value.endswith("\\"):
        return f'r"{value}"'
    return json.dumps(value, ensure_ascii=False)


def apply_settings(code: str, values: dict[str, Any]) -> str:
    """The code with each setting (by its id from `detect_settings` on this same code) set to a new value.
    Raises FillError when a value cannot go where its setting is."""
    by_id = {f.setting.id: f for f in _detect(code)}
    edits: list[tuple[int, int, str]] = []
    needs_os = False
    for setting_id, new in values.items():
        spot = by_id.get(setting_id)
        if spot is None:
            raise FillError("The code changed since its settings were read: read them again.")
        old = spot.setting.value
        variable = spot.setting.env
        if isinstance(new, dict) and isinstance(new.get("text"), str):
            # {"text": ...}: the one box's text (12.7), the whole of it: a variable only where it names one.
            new, variable = new["text"], None
        if isinstance(new, dict):  # {"value": path, "env": "NAME" or null}: a certificate file's source
            if "env" in new:
                try:
                    variable = certificate_files.variable_choice(
                        new.get("env"), spot.setting.name, spot.setting.key
                    )
                except certificate_files.MappingError as error:
                    raise FillError(str(error)) from None
            new = new.get("value", old)
        elif isinstance(new, str) and refs.holds(new):
            # The box names a variable (12.7): the code reads it where it runs, never its value here.
            edits.append((spot.start, spot.end, _reads_variables(spot, new)))
            needs_os = True
            continue
        elif isinstance(new, str):
            new = refs.literal(new)  # $${X} typed: the text ${X}
            if spot.setting.number and isinstance(old, str):  # was a variable read as a number
                old = 0
        if spot.setting.key in certificate_files.VARIABLE_ONLY and str(new or ""):
            # A password is never written into the code: its variable, or none (never the typed text).
            raise FillError(
                f"{spot.setting.key} takes a variable on its own, such as ${{NAME}}, or nothing: a password "
                "is never written into the code."
            )
        if variable:
            text = str(new)
            if "\n" in text:
                raise FillError(f"{spot.setting.key} is one line of text.")
            default = _string_literal(text, spot.raw or "\\" in text)
            edits.append((spot.start, spot.end, certificate_files.expression(variable, default)))
            needs_os = True
            continue
        if isinstance(old, bool):  # an on/off setting: True or False
            on = new is True or str(new).strip().casefold() in ("true", "yes", "1", "on")
            edits.append((spot.start, spot.end, "True" if on else "False"))
            continue
        if spot.inside_string and spot.setting.name in FLAGS:  # yes or no, as the driver reads it
            on = new is True or str(new).strip().casefold() in ("true", "yes", "1", "on")
            # true/false where the code said so; else yes/no (Encrypt=strict becomes yes or no)
            was_bool = str(old).strip().casefold() in ("true", "false")
            word = ("true" if on else "false") if was_bool else ("yes" if on else "no")
            edits.append((spot.start, spot.end, word))
            continue
        if spot.inside_string:
            text = str(new).strip()
            if not text or re.search(r"[;\"'\n]", text):
                raise FillError(f"{spot.setting.key} cannot hold ; quotes or a line break here.")
            edits.append((spot.start, spot.end, text if spot.raw else text.replace("\\", "\\\\")))
            continue
        if isinstance(old, int | float) and not isinstance(old, bool):
            try:
                number = float(new) if isinstance(old, float) else int(str(new).strip())
            except ValueError:
                raise FillError(f"{spot.setting.key} is a number.") from None
            edits.append((spot.start, spot.end, repr(number)))
            continue
        text = str(new)
        if "\n" in text:
            raise FillError(f"{spot.setting.key} is one line of text.")
        edits.append((spot.start, spot.end, _string_literal(text, spot.raw)))
    for start, end, text in sorted(edits, reverse=True):
        code = code[:start] + text + code[end:]
    try:
        parse_code(code)
    except BladeCodeError as error:
        raise FillError(f"That value would break the code: {error}") from None
    if certificate_files.HELPER in code:  # certificate_file(...) defined while a setting calls it
        code = certificate_files.with_helper(code)
    return certificate_files.with_import_os(code) if needs_os else code


def _reads_variables(spot: _Found, text: str) -> str:
    """The code for a setting whose box names variables: `os.environ[...]` joined to its text, int(...)
    for a number. Refused inside a connection string and for an on/off setting."""
    s = spot.setting
    if s.name in FLAGS:
        raise FillError(f"{s.key} is on or off: it cannot name a variable.")
    if spot.inside_string:
        raise FillError(
            f"{s.key} is part of a connection string here, which cannot read a variable: type its value, "
            "or write the connection with its settings as keywords."
        )
    found = refs.parts(text.strip())
    alone = len(found) == 1 and isinstance(found[0], refs.Ref) and not found[0].default
    if s.key in certificate_files.VARIABLE_ONLY and not alone:  # no typed text beside it, no default
        raise FillError(
            f"{s.key} takes a variable on its own, such as ${{NAME}}, or nothing: a password is never "
            "written into the code."
        )
    number = ("float" if isinstance(s.value, float) else "int") if s.number else None
    try:
        code = refs.setting_code(text, s.key, lambda p: _string_literal(p, spot.raw or "\\" in p), number)
    except ValueError as error:
        raise FillError(str(error)) from None
    # A certificate a driver reads by path, its box one variable: a key vault's PEM text works too.
    return f"{certificate_files.HELPER}({code})" if certificate_files.wraps(s.name, text) else code


def env_settings(code: str) -> list[dict[str, str]]:
    """The certificate and keystore files this code reads from an environment variable: each one's
    variable, setting (its plain name), key (as the code writes it) and default (this computer's path).
    The shape the export, Run settings and a Variables page read. [] for code that is not Python."""
    try:
        found = detect_settings(code)
    except BladeCodeError:
        return []
    out: list[dict[str, str]] = []
    for s in found:
        if s.env:
            out.append({"variable": s.env, "setting": s.name, "key": s.key, "default": str(s.value)})
            continue
        for ref in refs.find(s.text or ""):
            out.append({"variable": ref.name, "setting": s.name, "key": s.key, "default": ref.default or ""})
    return out
