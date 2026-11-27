# ruff: noqa: E501 (the TypeScript is written as the template's own compiler and linter take it)
"""A code app's pages: each page owns everything it needs (the owner, 2026-11-17: "I develop react by treating
each page as a lane. We should do the same"; "Lanes should be pages").

    src/pages/<Page>/
      <Page>Page.tsx    the page's root: its state lives here (useReducer), handed down by props
      components/       only this page's components
      hooks/            this page's data and logic (use<Page>: loading, error and refresh)
      state.ts          the page's own state and reducer (never app-wide)
      types.ts          its row and other types
      index.ts          its one public face: the page and its entry in the list of pages
    src/pages.ts        the list of pages (id, title, component); App.tsx draws a switcher from it
    src/shared/         what pages share: the Page type, the loading hook, a data table, a form field, the
                        app's context (the signed-in user, the environment), data.ts (the data notebook's
                        fixed results, never the app's data layer)

A page never imports from another page; only from `src/shared/` (cross_page_imports flags it, with the fix:
move the piece to `src/shared/`). Adding a page: its folder, then one line in `src/pages.ts` (register).

Defaults (the owner may change them; each sits in one place): hand-written hooks (no query library), the
built-in switcher in App.tsx (no router), plain controlled inputs (no form library). Nothing is added to the
template's packages. The template's TypeScript settings are followed: `import type` (verbatimModuleSyntax), no
enums (erasableSyntaxOnly), nothing unused (noUnusedLocals).

The starter page is "Accounts": a list, a detail, the selection lifted to its page, its hook over the
generated Dataverse service when the app has one (`src/generated/services/AccountsService.ts` with a
read-all method), made-up rows when it has none.

Pure rules over names, paths and text.
"""

from __future__ import annotations

import posixpath
import re
from typing import Any

PAGES = "src/pages"
REGISTRY = "src/pages.ts"
APP = "src/App.tsx"
TEMPLATE_APP_MARK = "Vite + React"  # the template's own App.tsx says it; a person's own does not
_WORD = re.compile(r"[A-Za-z0-9]+")
_IMPORT = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(\s*|^\s*import\s+)(["'])([^"']+)\1""", re.MULTILINE)
RESERVED = frozenset({"App", "Page", "Shared", "Generated", "React"})


class PageError(ValueError):
    """A page's name that cannot be one, or a page that is there already."""


def names_of(title: Any) -> dict[str, str]:
    """A page's names from its title ("Open orders"): folder and component (OpenOrders, OpenOrdersPage), id
    (open-orders), hook (useOpenOrders), entry (openOrdersPage), row type (OpenOrdersRow), title."""
    text = str(title or "").strip()
    words = _WORD.findall(text)
    if not words or len(text) > 60 or not text[0].isalpha():
        raise PageError("A page's name: a few words starting with a letter, such as Accounts or Open orders.")
    pascal = "".join(w[:1].upper() + w[1:] for w in words)
    if pascal in RESERVED or pascal.endswith("Page"):
        raise PageError(f"{pascal} cannot be a page's name: choose another word.")
    return {
        "folder": pascal,
        "component": pascal + "Page",
        "id": "-".join(w.lower() for w in words),
        "hook": "use" + pascal,
        "entry": pascal[:1].lower() + pascal[1:] + "Page",
        "row": pascal + "Row",
        "title": " ".join(words),
        "state": pascal + "State",
        "action": pascal + "Action",
        "reducer": pascal[:1].lower() + pascal[1:] + "Reducer",
        "initial": "initial" + pascal + "State",
    }


def read_method(service_text: str) -> str | None:
    """The generated service's read-all method as the file spells it (getAll; Microsoft's docs also show
    getall), or None (a connector's actions have none)."""
    for name in ("getAll", "getall"):
        if re.search(rf"\b(?:static\s+)?(?:async\s+)?{name}\s*\(", service_text):
            return name
    return None


def service_of(service_path: str) -> str:
    return service_path.rsplit("/", 1)[-1].removesuffix(".ts")


# ===== a page's files =====


def page_files(title: Any, service_path: str | None = None, service_text: str = "") -> dict[str, str]:
    """A new page's files by their paths. With a generated service that reads rows, its hook reads through
    it and its row is the service's; else made-up rows."""
    n = names_of(title)
    folder = f"{PAGES}/{n['folder']}"
    method = read_method(service_text) if service_path else None
    service = service_of(service_path) if service_path and method else None
    if service is not None and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", service):
        service = None
    files = {
        f"{folder}/types.ts": _types(n, service, method),
        f"{folder}/state.ts": _state(n),
        f"{folder}/hooks/{n['hook']}.ts": _hook(n, service, method),
        f"{folder}/components/{n['folder']}List.tsx": _list(n),
        f"{folder}/components/{n['folder']}Detail.tsx": _detail(n),
        f"{folder}/{n['component']}.tsx": _page(n),
        f"{folder}/index.ts": _index(n),
    }
    return files


def _types(n: dict[str, str], service: str | None, method: str | None) -> str:
    if service and method:
        return (
            f'import type {{ {service} }} from "../../generated/services/{service}";\n\n'
            f"/** One row of the {n['title']} page: what the generated service reads. */\n"
            f'export type {n["row"]} = NonNullable<Awaited<ReturnType<typeof {service}.{method}>>["data"]>[number];\n'
        )
    return (
        f"/** One row of the {n['title']} page (made-up until the page reads a data source). */\n"
        f"export interface {n['row']} {{\n  name: string;\n  city: string;\n  revenue: number;\n}}\n"
    )


def _state(n: dict[str, str]) -> str:
    return f"""\
import type {{ {n["row"]} }} from "./types";

/** The {n["title"]} page's own state: kept at the page's root, handed to its components. */
export interface {n["state"]} {{
  selected: {n["row"]} | null;
  filter: string;
}}

export type {n["action"]} = {{ type: "select"; row: {n["row"]} | null }} | {{ type: "filter"; text: string }};

export const {n["initial"]}: {n["state"]} = {{ selected: null, filter: "" }};

export function {n["reducer"]}(state: {n["state"]}, action: {n["action"]}): {n["state"]} {{
  switch (action.type) {{
    case "select":
      return {{ ...state, selected: action.row }};
    case "filter":
      return {{ ...state, filter: action.text }};
  }}
}}
"""


def _hook(n: dict[str, str], service: str | None, method: str | None) -> str:
    head = (
        f'import {{ useCallback }} from "react";\n'
        f'import {{ useLoad, type Loaded }} from "../../../shared/useLoad";\n'
        f'import type {{ {n["row"]} }} from "../types";\n'
    )
    if service and method:
        return (
            head
            + f'import {{ {service} }} from "../../../generated/services/{service}";\n\n'
            + f"/** The {n['title']} rows, read through the generated service. */\n"
            + f"export function {n['hook']}(): Loaded<{n['row']}> {{\n"
            + f"  const load = useCallback(async (): Promise<{n['row']}[]> => {{\n"
            + f"    const result = await {service}.{method}();\n"
            + "    return result.data ?? [];\n"
            + "  }, []);\n"
            + "  return useLoad(load);\n"
            + "}\n"
        )
    return (
        head
        + "\n"
        + f"const MADE_UP: {n['row']}[] = [\n"
        + '  { name: "Contoso", city: "Seattle", revenue: 120000 },\n'
        + '  { name: "Fabrikam", city: "Denver", revenue: 80000 },\n'
        + '  { name: "Northwind", city: "Boston", revenue: 95000 },\n'
        + "];\n\n"
        + f"/** The {n['title']} rows: made-up until the page reads a data source (a generated service). */\n"
        + f"export function {n['hook']}(): Loaded<{n['row']}> {{\n"
        + f"  const load = useCallback(async (): Promise<{n['row']}[]> => MADE_UP, []);\n"
        + "  return useLoad(load);\n"
        + "}\n"
    )


def _list(n: dict[str, str]) -> str:
    return f"""\
import {{ DataTable }} from "../../../shared/components/DataTable";
import {{ FormField }} from "../../../shared/components/FormField";
import type {{ {n["row"]} }} from "../types";

interface Props {{
  rows: {n["row"]}[];
  filter: string;
  selected: {n["row"]} | null;
  onFilter: (text: string) => void;
  onSelect: (row: {n["row"]}) => void;
}}

/** The {n["title"]} rows that match the filter; a row clicked is the page's selection. */
export function {n["folder"]}List({{ rows, filter, selected, onFilter, onSelect }}: Props) {{
  const wanted = filter.trim().toLowerCase();
  const shown = wanted ? rows.filter((r) => JSON.stringify(r).toLowerCase().includes(wanted)) : rows;
  return (
    <section>
      <FormField label="Filter" value={{filter}} onChange={{onFilter}} />
      <DataTable rows={{shown}} selected={{selected}} onSelect={{onSelect}} />
    </section>
  );
}}
"""


def _detail(n: dict[str, str]) -> str:
    return f"""\
import type {{ {n["row"]} }} from "../types";

/** The selected row, each field on a line. */
export function {n["folder"]}Detail({{ row }}: {{ row: {n["row"]} | null }}) {{
  if (!row) return <aside>Select a row.</aside>;
  return (
    <aside>
      <dl>
        {{Object.entries(row).map(([key, value]) => (
          <div key={{key}}>
            <dt>{{key}}</dt>
            <dd>{{String(value ?? "")}}</dd>
          </div>
        ))}}
      </dl>
    </aside>
  );
}}
"""


def _page(n: dict[str, str]) -> str:
    return f"""\
import {{ useReducer }} from "react";
import {{ {n["folder"]}Detail }} from "./components/{n["folder"]}Detail";
import {{ {n["folder"]}List }} from "./components/{n["folder"]}List";
import {{ {n["hook"]} }} from "./hooks/{n["hook"]}";
import {{ {n["initial"]}, {n["reducer"]} }} from "./state";

/** The {n["title"]} page: its rows, a list and a detail; the selection is kept here and handed down. */
export function {n["component"]}() {{
  const {{ rows, loading, error, refresh }} = {n["hook"]}();
  const [state, dispatch] = useReducer({n["reducer"]}, {n["initial"]});
  return (
    <div>
      <header>
        <h1>{n["title"]}</h1>
        <button onClick={{refresh}} disabled={{loading}}>
          Refresh
        </button>
      </header>
      {{error && <p role="alert">{{error}}</p>}}
      {{loading ? (
        <p>Loading…</p>
      ) : (
        <{n["folder"]}List
          rows={{rows}}
          filter={{state.filter}}
          selected={{state.selected}}
          onFilter={{(text) => dispatch({{ type: "filter", text }})}}
          onSelect={{(row) => dispatch({{ type: "select", row }})}}
        />
      )}}
      <{n["folder"]}Detail row={{state.selected}} />
    </div>
  );
}}
"""


def _index(n: dict[str, str]) -> str:
    return f"""\
import type {{ Page }} from "../../shared/page";
import {{ {n["component"]} }} from "./{n["component"]}";

/** The {n["title"]} page's one public face: its entry in the list of pages (src/pages.ts). */
export const {n["entry"]}: Page = {{ id: "{n["id"]}", title: "{n["title"]}", component: {n["component"]} }};

export {{ {n["component"]} }};
"""


# ===== the list of pages, App.tsx and what pages share =====

REGISTRY_TEXT = """\
import type { Page } from "./shared/page";

/** Every page of the app, in the order the navigation shows them. A new page: its folder under src/pages/,
 *  then its line here. */
export const pages: Page[] = [
];
"""


def register(registry: str | None, title: Any) -> str:
    """src/pages.ts with the page's import and its line added (unchanged when it is there already)."""
    n = names_of(title)
    text = registry if registry and "export const pages" in registry else REGISTRY_TEXT
    importing = f'import {{ {n["entry"]} }} from "./pages/{n["folder"]}";'
    if importing in text:
        return text
    lines = text.splitlines()
    last_import = max((i for i, line in enumerate(lines) if line.startswith("import ")), default=-1)
    lines.insert(last_import + 1, importing)
    start = next(i for i, line in enumerate(lines) if "export const pages" in line)
    end = next(i for i in range(start, len(lines)) if lines[i].strip().startswith("];"))
    lines.insert(end, f"  {n['entry']},")
    return "\n".join(lines) + "\n"


def registered(registry: str | None) -> list[str]:
    """The page folders src/pages.ts imports, in its order."""
    return re.findall(r'from\s+"\./pages/([A-Za-z0-9_]+)"', registry or "")


APP_TEXT = """\
import { useState } from "react";
import { pages } from "./pages.ts";
import { AppContextProvider } from "./shared/AppContext";

/** The app: a button per page (src/pages.ts), the chosen page below. A router can take this place later. */
function App() {
  const [current, setCurrent] = useState(pages[0]?.id ?? "");
  const page = pages.find((p) => p.id === current) ?? pages[0];
  const Shown = page?.component;
  return (
    <AppContextProvider>
      <nav>
        {pages.map((p) => (
          <button key={p.id} aria-current={p.id === page?.id ? "page" : undefined} onClick={() => setCurrent(p.id)}>
            {p.title}
          </button>
        ))}
      </nav>
      <main>{Shown ? <Shown /> : null}</main>
    </AppContextProvider>
  );
}

export default App;
"""

SHARED: dict[str, str] = {
    "src/shared/page.ts": """\
import type { ComponentType } from "react";

/** A page as the list of pages holds it (src/pages.ts): its id, its title in the navigation, its root. */
export interface Page {
  id: string;
  title: string;
  component: ComponentType;
}
""",
    "src/shared/useLoad.ts": """\
import { useCallback, useEffect, useRef, useState } from "react";

/** Rows read by a loader, with what a page needs around them. */
export interface Loaded<T> {
  rows: T[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/** Load once and on refresh: loading while it runs, the error's words when it fails; a late answer from an
 *  earlier load is dropped. Pass a loader made with useCallback, so it changes only when it should. */
export function useLoad<T>(load: () => Promise<T[]>): Loaded<T> {
  const [rows, setRows] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [asked, setAsked] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    const ticket = ++latest.current;
    load()
      .then((found) => {
        if (ticket !== latest.current) return;
        setRows(found);
        setError(null);
      })
      .catch((e: unknown) => {
        if (ticket === latest.current) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (ticket === latest.current) setLoading(false);
      });
  }, [load, asked]);

  const refresh = useCallback(() => {
    setLoading(true);
    setAsked((n) => n + 1);
  }, []);
  return { rows, loading, error, refresh };
}
""",
    "src/shared/components/DataTable.tsx": """\
interface Props<T extends object> {
  rows: T[];
  selected?: T | null;
  onSelect?: (row: T) => void;
}

/** Rows as a table: a column per field of the first row; a row clicked is selected. */
export function DataTable<T extends object>({ rows, selected, onSelect }: Props<T>) {
  const columns = rows.length ? Object.keys(rows[0]) : [];
  if (!rows.length) return <p>Nothing to show.</p>;
  return (
    <table>
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} aria-selected={row === selected} onClick={() => onSelect?.(row)}>
            {columns.map((c) => (
              <td key={c}>{String((row as Record<string, unknown>)[c] ?? "")}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
""",
    "src/shared/components/FormField.tsx": """\
import { useId } from "react";

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "number" | "email" | "date";
}

/** A labelled input whose value its owner keeps (a controlled input). */
export function FormField({ label, value, onChange, type = "text" }: Props) {
  const id = useId();
  return (
    <label htmlFor={id}>
      {label}
      <input id={id} type={type} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
""",
    "src/shared/appContext.ts": """\
import { createContext, useContext } from "react";

/** What every page may read: who is signed in and the environment, when the app knows them. */
export interface AppContextValue {
  user: string | null;
  environment: string | null;
}

export const NO_ONE: AppContextValue = { user: null, environment: null };
export const AppContext = createContext<AppContextValue>(NO_ONE);
export const useAppContext = (): AppContextValue => useContext(AppContext);
""",
    "src/shared/AppContext.tsx": """\
import type { ReactNode } from "react";
import { AppContext, NO_ONE, type AppContextValue } from "./appContext";

export function AppContextProvider({ children, value }: { children: ReactNode; value?: AppContextValue }) {
  return <AppContext.Provider value={value ?? NO_ONE}>{children}</AppContext.Provider>;
}
""",
}


def scaffold_plan(
    existing: dict[str, str | None], service_path: str | None, service_text: str
) -> dict[str, str]:
    """What the scaffold writes: what pages share, the list of pages with the Accounts page, App.tsx while it
    is the template's own. Only where no file is (a person's own file is never replaced). `existing`: each
    path's text now (None: none)."""
    out = {p: t for p, t in SHARED.items() if existing.get(p) is None}
    accounts = page_files("Accounts", service_path, service_text)
    if (
        not any(existing.get(p) is not None for p in accounts)
        and existing.get(f"{PAGES}/Accounts/index.ts") is None
    ):
        out |= accounts
        out[REGISTRY] = register(existing.get(REGISTRY), "Accounts")
    elif existing.get(REGISTRY) is None:
        out[REGISTRY] = REGISTRY_TEXT
    app = existing.get(APP)
    if app is None or TEMPLATE_APP_MARK in app:
        out[APP] = APP_TEXT
    return out


def scaffold_paths() -> list[str]:
    """Every path the scaffold may write (asked of the folder first)."""
    return [*SHARED, *page_files("Accounts"), REGISTRY, APP]


# ===== the rule: a page never imports from another page =====


def _page_of(path: str) -> str | None:
    parts = path.split("/")
    return parts[2] if len(parts) > 3 and parts[0] == "src" and parts[1] == "pages" else None


def cross_page_imports(path: str, text: str) -> list[dict[str, Any]]:
    """Each import of `path` (a page's file, or a shared one) that reaches into another page: the place, the
    words, and the fix (move the piece to src/shared/)."""
    rel = path.replace("\\", "/").lstrip("/")
    own = _page_of(rel)
    shared = rel.startswith("src/shared/")
    if own is None and not shared:
        return []
    problems: list[dict[str, Any]] = []
    for found in _IMPORT.finditer(text):
        spec = found.group(2)
        if spec.startswith("."):
            target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec))
        elif spec.startswith(("src/", "@/")):
            target = "src/" + spec.split("/", 1)[1]
        else:
            continue
        other = _page_of(target + "/x") if target.count("/") == 2 else _page_of(target)
        if other is None or other == own:
            continue
        line = text.count("\n", 0, found.start(2)) + 1
        col = found.start(2) - (text.rfind("\n", 0, found.start(2)) + 1) + 1
        piece = target.rsplit("/", 1)[-1]
        who = f"The {own} page" if own else "A shared file"
        problems.append(
            {
                "line": line,
                "col": col,
                "endLine": line,
                "endCol": col + len(spec),
                "message": f"{who} imports from the {other} page: a page never imports another page's code.",
                "hover": f"Move `{piece}` to `src/shared/` and import it from there in both pages.",
                "severity": "error",
                "fixes": [{"kind": "move", "title": "Move it to src/shared/", "target": target}],
                "imported": spec,
            }
        )
    return problems
