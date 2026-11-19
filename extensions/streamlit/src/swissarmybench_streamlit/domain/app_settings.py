"""A Streamlit app's page settings and its live state (the Workbench's App mode, 2026-11-15).

PAGE SETTINGS (Properties with no block selected): the title, the icon, wide or centred, a logo and
the theme's colours. They are kept in the app's file (`"settings"`, beside the pages) and written into:

  the live page (Play)   the entry's st.set_page_config and st.logo, and .streamlit/config.toml in the
                         app's temporary folder (Streamlit reads it from the folder it runs in)
  an export              app.py's st.set_page_config and st.logo, and .streamlit/config.toml
  the saved pages        each pages/*.py starts with st.set_page_config and st.logo (a page dropped into
                         any app looks as designed); the project gets .streamlit/config.toml, and so
                         does its zip. A config.toml of the user's own (without this file's mark line)
                         is never written over

STATE (the State panel): the live page writes what its session holds (st.session_state: every widget's
value by its key, and the page's own values) to `_sab_state.json` in the app's temporary folder after
each run; the panel reads it, each key with the block whose widget it is. A value is shown as itself when
it is a plain one (text, a number, a date, a short list of those), else as what it is ("DataFrame, 10
rows"). Reset state starts the page again with a fresh session.

Pure rules, no I/O.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any

LAYOUTS: tuple[str, ...] = ("wide", "centered")
COLOURS: tuple[str, ...] = ("primary", "background", "secondary_background", "text")
# config.toml's [theme] key for each colour.
THEME_KEYS: dict[str, str] = {
    "primary": "primaryColor",
    "background": "backgroundColor",
    "secondary_background": "secondaryBackgroundColor",
    "text": "textColor",
}
MAX_TITLE: int = 120
MAX_ICON: int = 8
MAX_LOGO: int = 500
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
CONFIG_FILE: str = ".streamlit/config.toml"
CONFIG_MARK: str = "# Written by Swiss Army Bench from {app}: change the app's page settings, not this file."
STATE_FILE: str = "_sab_state.json"
MAX_STATE_KEYS: int = 200
MAX_VALUE_CHARS: int = 200


class AppSettingsError(ValueError):
    """Page settings that cannot be used as sent (the message says why)."""


@dataclass(frozen=True)
class AppSettings:
    title: str = ""  # "" : the app's own name
    icon: str = ""  # an emoji or a few letters ("" : Streamlit's own)
    layout: str = "wide"
    logo: str = ""  # an image's path, relative to the app's file (or whole); "" : none
    colours: dict[str, str] = field(default_factory=dict)  # primary, background, ... -> #rrggbb

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def is_default(self) -> bool:
        return self == AppSettings()


def _text(value: Any, name: str, most: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > most or "\n" in value or "\x00" in value:
        raise AppSettingsError(f"The {name} is one line of text (at most {most} characters).")
    return value.strip()


def changed(settings: AppSettings, sent: Any) -> AppSettings:
    """`settings` with what is sent changed: {"title", "icon", "layout", "logo", "colours": {...}};
    a colour sent as null goes back to the theme's own."""
    if not isinstance(sent, dict):
        raise AppSettingsError(
            'Send the page settings: {"title", "icon", "layout": "wide" or "centered", "logo", "colours"}.'
        )
    unknown = [key for key in sent if key not in ("title", "icon", "layout", "logo", "colours")]
    if unknown:
        raise AppSettingsError(f"No page setting is called {unknown[0]!r}.")
    out = settings
    if "title" in sent:
        out = replace(out, title=_text(sent["title"], "title", MAX_TITLE))
    if "icon" in sent:
        out = replace(out, icon=_text(sent["icon"], "icon", MAX_ICON))
    if "layout" in sent:
        if sent["layout"] not in LAYOUTS:
            raise AppSettingsError('The layout is "wide" or "centered".')
        out = replace(out, layout=str(sent["layout"]))
    if "logo" in sent:
        out = replace(out, logo=_text(sent["logo"], "logo's path", MAX_LOGO))
    if "colours" in sent:
        raw = sent["colours"]
        if not isinstance(raw, dict):
            raise AppSettingsError('The colours are {"primary": "#c8102e", ...}.')
        colours = dict(out.colours)
        for key, value in raw.items():
            if key not in COLOURS:
                raise AppSettingsError(
                    f"No theme colour is called {key!r}. The colours: {', '.join(COLOURS)}."
                )
            if value is None or value == "":
                colours.pop(key, None)
            elif isinstance(value, str) and _HEX.match(value):
                colours[key] = value.lower()
            else:
                raise AppSettingsError(f"The {key.replace('_', ' ')} colour is #rrggbb, like #c8102e.")
        out = replace(out, colours={k: colours[k] for k in COLOURS if k in colours})
    return out


def read_settings(raw: Any) -> AppSettings:
    """Settings as an app's file keeps them (anything unreadable is left at its default)."""
    if not isinstance(raw, dict):
        return AppSettings()
    out = AppSettings()
    for key in ("title", "icon", "layout", "logo", "colours"):
        if key in raw:
            try:
                out = changed(out, {key: raw[key]})
            except AppSettingsError:
                continue
    return out


def read_app_settings(text: str) -> AppSettings:
    """The page settings an app's file holds (none: the defaults)."""
    try:
        data = json.loads(text)
    except ValueError:
        return AppSettings()
    return read_settings(data.get("settings")) if isinstance(data, dict) else AppSettings()


def file_line(settings: AppSettings) -> str | None:
    """The app's file's `"settings"` line (None: the defaults, so the line is left out)."""
    if settings.is_default():
        return None
    held = {
        k: v
        for k, v in settings.to_json().items()
        if v not in ("", {}, None) and not (k == "layout" and v == "wide")
    }
    if settings.layout != "wide":
        held["layout"] = settings.layout
    return f'  "settings": {json.dumps(held, ensure_ascii=False)},'


def page_head(settings: AppSettings, title: str, logo: str | None = None) -> list[str]:
    """A page's first Streamlit calls: st.set_page_config (title, icon, layout) and st.logo. `logo`: the
    logo's path as the page should name it (None: the settings' own)."""
    arguments = [f"page_title={(settings.title or title)!r}"]
    if settings.icon:
        arguments.append(f"page_icon={settings.icon!r}")
    arguments.append(f"layout={settings.layout!r}")
    lines = [f"st.set_page_config({', '.join(arguments)})"]
    shown = settings.logo if logo is None else logo
    if shown:
        lines.append(f"st.logo({shown!r})")
    return lines


def config_toml(settings: AppSettings, app: str) -> str | None:
    """.streamlit/config.toml for the theme's colours (None: no colour chosen). Its first line marks it
    as this app's, so it may be written again."""
    if not settings.colours:
        return None
    lines = [CONFIG_MARK.format(app=app.replace("\n", " ")), "[theme]"]
    lines += [f'{THEME_KEYS[key]} = "{value}"' for key, value in settings.colours.items()]
    return "\n".join(lines) + "\n"


def is_own_config(text: str | None) -> bool:
    """A config.toml this app wrote (or none at all): it may be written again."""
    return text is None or text.startswith("# Written by Swiss Army Bench from ")


def manifest(settings: AppSettings, title: str, logo: str | None) -> dict[str, Any]:
    """What the live app's entry reads from its manifest: the title, the icon, the layout, the logo
    (a whole path, or None)."""
    return {
        "title": settings.title or title,
        "icon": settings.icon or None,
        "layout": settings.layout,
        "logo": logo or None,
    }


# ===== the live page's state =====

# Added at the end of each page the live app runs (Play): what the session holds, for the State panel.
STATE_TAIL: str = f'''
# What this session holds now, for the Workbench's State panel (the live page only).
def _sab_state() -> None:
    import datetime as _dt
    import json as _json
    from pathlib import Path as _Path

    def _shown(value):
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return value[:{MAX_VALUE_CHARS}]
        if isinstance(value, (_dt.date, _dt.datetime, _dt.time)):
            return value.isoformat()
        if isinstance(value, (list, tuple)) and len(value) <= 20 and all(
            v is None or isinstance(v, (bool, int, float, str)) for v in value
        ):
            return [v[:{MAX_VALUE_CHARS}] if isinstance(v, str) else v for v in value]
        rows = getattr(value, "shape", None)
        if rows is not None and len(rows) >= 1:
            return {{"kind": type(value).__name__, "rows": int(rows[0])}}
        return {{"kind": type(value).__name__}}

    held = {{}}
    for key in list(st.session_state.keys())[:{MAX_STATE_KEYS}]:
        try:
            held[str(key)] = _shown(st.session_state[key])
        except Exception:
            held[str(key)] = {{"kind": "unreadable"}}
    try:
        target = _Path(__file__).resolve().parent / "{STATE_FILE}"
        partial = target.with_name(target.name + ".part")
        partial.write_text(_json.dumps(held, default=str), encoding="utf-8")
        partial.replace(target)
    except OSError:
        pass


_sab_state()
'''


# ===== Now: what the property pane changes in the running app only (the owner, 2026-11-19) =====
#
# The pane's "Now" fields set st.session_state in the live page, and Clear this cache empties a cached
# function there; nothing of the cell's code changes. The server writes what was asked into NOW_FILE in the
# app's temporary folder (numbered, the last few kept) and the page reads it at its start: each session
# makes what it has not made yet, once. A session that starts later makes none of it (it starts fresh).
NOW_FILE: str = "_sab_now.json"
MAX_NOW: int = 20
NOW_HEAD: str = f'''# What the Workbench's property pane asked of this session (Now): the live page only.
def _sab_now() -> list:
    import datetime as _dt
    import json as _json
    from pathlib import Path as _Path

    try:
        asked = _json.loads((_Path(__file__).resolve().parent / "{NOW_FILE}").read_text(encoding="utf-8"))
        made = [op for op in asked["made"] if isinstance(op, dict)]
    except (OSError, ValueError, KeyError, TypeError):
        made = []
    last = max([int(op.get("n") or 0) for op in made] or [0])
    seen = st.session_state.get("_sab_now")
    st.session_state["_sab_now"] = last
    if seen is None:
        return []
    clear = []
    for op in made:
        if int(op.get("n") or 0) <= seen:
            continue
        clear += [str(name) for name in op.get("clear") or []]
        for key, value in (op.get("set") or {{}}).items():
            old = st.session_state.get(key)
            try:
                if isinstance(old, (_dt.datetime, _dt.date, _dt.time)) and isinstance(value, str):
                    value = type(old).fromisoformat(value)
                elif isinstance(old, tuple) and isinstance(value, list):
                    value = tuple(value)
                st.session_state[key] = value
            except Exception:
                pass
        for key in op.get("forget") or []:
            st.session_state.pop(key, None)
    return clear


_sab_clear = _sab_now()

'''
# After the state is written: the caches asked to be cleared are, and the page runs once more.
NOW_TAIL: str = """
if _sab_clear:
    for _name in _sab_clear:
        if _name == "*":
            st.cache_data.clear()
            st.cache_resource.clear()
        elif hasattr(globals().get(_name), "clear"):
            globals()[_name].clear()
    st.rerun()
"""


def check_now(body: Any) -> dict[str, Any]:
    """What Now may ask: {"key", "value"} (a session state key given a plain value), {"key", "forget": true}
    (the key taken out: its widget starts from its default again), {"clear": a cached function's name, or
    "*" for every cache}."""
    if not isinstance(body, dict):
        raise AppSettingsError('Send {"key": "region", "value": "North"} or {"clear": "monthly"}.')
    if "clear" in body:
        name = body["clear"]
        if not isinstance(name, str) or not re.fullmatch(r"\*|[A-Za-z_][A-Za-z0-9_]{0,99}", name):
            raise AppSettingsError('Clear a cache by its function\'s name, or "*" for every cache.')
        return {"clear": [name]}
    key = body.get("key")
    if not isinstance(key, str) or not key or len(key) > 200 or key.startswith(("_sab", "$$")):
        raise AppSettingsError("A session state key is its name, as the page's State lists it.")
    if body.get("forget") is True:
        return {"forget": [key]}
    if "value" not in body:
        raise AppSettingsError('Send the key\'s value: {"key": "region", "value": "North"}.')
    value = body["value"]
    try:
        text = json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        raise AppSettingsError("A session state value set from here is a plain one.") from None
    if len(text) > 20_000:
        raise AppSettingsError("That value is too long to set from here.")
    return {"set": {key: value}}


def now_file(made: Sequence[Mapping[str, Any]]) -> str:
    return json.dumps({"made": list(made)[-MAX_NOW:]})


_KEY = re.compile(r"\bkey\s*=\s*(['\"])([^'\"\n]{1,200})\1")


def widget_keys(code: str, block: str) -> list[str]:
    """The session state keys a block's widgets use on the page: the keys its code gives them, and the
    ones the page gives a widget that has none (`<block>_1`, `<block>_2`, ...; streamlit_cells.keyed)."""
    found: list[str] = []
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "key"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    found.append(keyword.value.value)
    else:
        found = [m.group(2) for m in _KEY.finditer(code)]
    return list(dict.fromkeys(found))


def state_rows(held: Any, blocks: Iterable[tuple[str, str, str]]) -> list[dict[str, Any]]:
    """The State panel's rows: each key the session holds, its value as shown, and the block whose
    widget it is (`blocks`: each block's id, name and code). Keys the app keeps for itself are left out."""
    if not isinstance(held, dict):
        return []
    owner: dict[str, str] = {}
    prefixes: list[tuple[str, str]] = []
    for block_id, name, code in blocks:
        for key in widget_keys(code, block_id):
            owner.setdefault(key, name)
        prefixes.append((f"{block_id}_", name))
    rows = []
    for key, value in list(held.items())[:MAX_STATE_KEYS]:
        if not isinstance(key, str) or key.startswith(("_sab", "$$")):
            continue
        block = owner.get(key) or next((name for prefix, name in prefixes if key.startswith(prefix)), None)
        rows.append({"key": key, "value": value, "block": block})
    return rows


def shown_value(value: Any) -> str:
    """A state value as the panel writes it: JSON for a plain value, else what it is."""
    if isinstance(value, dict) and "kind" in value:
        rows = value.get("rows")
        return f"{value['kind']}, {rows} rows" if isinstance(rows, int) else str(value["kind"])
    return json.dumps(value, ensure_ascii=False)


def block_values(rows: Sequence[Mapping[str, Any]], name: str) -> list[tuple[str, str]]:
    """A block's widget values (Properties' Widget value): each key and its value as shown."""
    return [(str(r["key"]), shown_value(r["value"])) for r in rows if r.get("block") == name]
