/**
 * environmentPage.ts: the Environment (the owner, 2026-11-21/22; Plans/environment.plan.md): everything the
 * project holds on one page, a tab for each kind, and the same list as the Workbench's right pane. [SHARED]
 *
 *   [TABS]    Tables, Variables (what the code makes), Structures, Settings and secrets, Libraries: each
 *             its own columns; a column hides from its heading's menu, kept per tab.
 *   [SEARCH]  one box over every tab (the server's: the Data Explorer's matching, any case, by parts): each
 *             tab's count lights up, a line names the other tabs that match, the match is marked in the row
 *             and a row that matched inside opens there.
 *   [BROWSE]  a row unfolds in place (a table's columns with ranges and blanks, a structure's paths, a
 *             list's items, a setting's source and uses); the place is kept when the list follows a change.
 *   [VIEWER]  beside the list (folds with Ctrl+B): the row's facts, every place that uses it (each a link
 *             that goes there), its actions; a table's "Also delete it in Python" tick for Remove.
 *   [KEYS]    Up, Down move; Right opens a level, Left closes; Enter opens the row where it lives; F2
 *             renames; Delete removes; / goes to the search.
 *   [LIVE]    it follows the `environment_changed` notice by itself: no Refresh. Tables are added on the
 *             Connections page; Interrupt and Restart stay on the Notebooks and Scripts pages.
 *   [PAGE]    a page of the rail's over any page (areaPage.ts): open=environment&at=<tab>&name=<row>.
 *
 * ROUTING: GET /environment ?search=  ·  GET /environment/columns ?name=  ·  POST /environment/open, /insert,
 *          /rename, /remove, /keep, /clear  ·  GET /environment/libraries ?check=1  ·  POST
 *          /environment/libraries/install, /update, /pin  ·  POST /variables/reveal (Show: the user's)
 *          notice environment_changed
 */
import { onNotice } from "./api";
import { openAreaPage, type PageElement } from "./areaPage";
import { button, h, recall } from "./dom";
import { clearDialog, openItem, removeDialog, renameDialog } from "./environmentActions";
import { draw } from "./environmentDraw";
import { check, load, setFolded, setTab, toggle } from "./environmentMoves";
import { type Kind, KINDS, type Listing, stepped } from "./environmentRules";
import { type Environment, type EnvironmentOptions, find, items } from "./environmentState";
import { mountKeyVaults } from "./keyVaults";
import { dismissDialog, go, layerOpened, registerLayer, setOverTitle, watchLayerDialog, withParams } from "./nav";

export type { Item, Kind, Used } from "./environmentRules";
export { type EnvironmentOptions, marked } from "./environmentState";

export interface EnvironmentView {
  element: HTMLElement;
  refresh: () => Promise<void>;
  /** What the list last read (the agent's workbench_window reads it). */
  snapshot: () => Listing | null;
  show: (tab: Kind, name?: string) => void;
  dispose: () => void;
}

// The Environment is in parts (the craft review of 2026-11-22, refactor 8): its state is one record
// (environmentState.ts) handed to each part: the rules that need no page (environmentRules.ts, tested in
// Node), reading and moving (…Moves), what a row does and its dialogs (…Actions), the columns (…Columns),
// the drawing and the viewer (…Draw). This file makes the record, listens (the keys, the search, the
// notice) and is the page and the Workbench's pane.

/** The state record of a new list, its elements made and laid out. */
function newEnvironment(options: EnvironmentOptions): Environment {
  const compact = Boolean(options.compact);
  const tab: Kind = options.tab ?? "table";
  const search = h("input", {
    type: "search",
    class: "env-search",
    placeholder: compact ? "Search every tab" : "Search every tab: names, columns, keys, variables, where used…",
    "aria-label": "Search the environment",
    autocomplete: "off",
    spellcheck: false,
    "data-no-variables": "",
  }) as HTMLInputElement;
  const hint = h("span", { class: "env-hint", role: "status" });
  const tools = h("span", { class: "env-tools" });
  const tabs = h("div", { class: "env-tabs", role: "tablist", "aria-label": "Kinds" });
  const session = h("div", { class: "env-session" });
  const projectHost = h("div", { class: "env-project-lines" });
  const vaults = mountKeyVaults();
  vaults.element.hidden = true;
  const list = h("div", { class: "env-list", role: "tree", "aria-label": "Everything the project holds", tabindex: -1 });
  const viewer = h("aside", { class: "env-side", "aria-label": "Viewer" });
  const main = h("div", { class: "env-main" }, h("section", { class: "env-page", "aria-label": "Environment list" }, session, tabs, h("div", { class: "env-find" }, search, hint, tools), projectHost, vaults.element, list), viewer);
  const element = h("div", { class: `env${compact ? " env-compact" : ""}` }, main);
  const foldKey = compact ? "env.viewer.pane" : "env.viewer.page";
  const env: Environment = {
    options,
    compact,
    tab,
    query: "",
    listing: null,
    failed: null,
    selected: options.name ? `${tab}:${options.name}` : null,
    opened: new Set(),
    columnsOf: new Map(),
    revealed: new Map(),
    checking: false,
    disposed: false,
    asked: 0,
    foldKey,
    folded: recall(foldKey) === "1",
    pythonTick: null,
    search,
    hint,
    tools,
    tabs,
    session,
    projectHost,
    vaults,
    list,
    viewer,
    element,
    act: { draw: () => draw(env) },
  };
  return env;
}

/** The keys: Up, Down move; Right opens a level, Left closes; Enter opens the row where it lives; F2
 *  renames; Delete removes; / goes to the search; Ctrl+B folds the viewer (the page's). */
function onKey(env: Environment, e: KeyboardEvent): void {
  const target = e.target as HTMLElement;
  const typing = target.matches("input, textarea, select, [contenteditable='true']");
  if (target.closest("dialog") || (!env.element.contains(target) && target !== document.body)) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b" && !env.compact) {
    e.preventDefault();
    setFolded(env, !env.folded);
    return;
  }
  if (e.key === "/" && !typing) {
    e.preventDefault();
    env.search.focus();
    return;
  }
  if (typing && !(target === env.search && e.key === "ArrowDown")) return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const shown = items(env);
  const item = shown.find((i) => i.id === env.selected);
  if (e.key === "ArrowDown" || e.key === "ArrowUp") env.selected = stepped(shown.map((i) => i.id), env.selected, e.key);
  else if (e.key === "ArrowRight" && item) return void (e.preventDefault(), toggle(env, item, true), focusRow(env));
  else if (e.key === "ArrowLeft" && item) return void (e.preventDefault(), toggle(env, item, false), focusRow(env));
  else if (e.key === "Enter" && item && target.closest(".env-row")) return void (e.preventDefault(), openItem(env, item));
  else if (e.key === "F2" && item) return void (e.preventDefault(), renameDialog(env, item));
  else if (e.key === "Delete" && item) return void (e.preventDefault(), removeDialog(env, item));
  else return;
  e.preventDefault();
  env.options.moved?.(env.tab, find(env, env.selected)?.name ?? null);
  draw(env);
  focusRow(env);
}

function focusRow(env: Environment): void {
  const made = env.list.querySelector<HTMLElement>(".env-row.sel");
  made?.focus();
  made?.scrollIntoView({ block: "nearest" });
}

// ===== the list, for the page and for the Workbench's pane =====

export function mountEnvironment(options: EnvironmentOptions = {}): EnvironmentView {
  const env = newEnvironment(options);
  const keys = (e: KeyboardEvent): void => onKey(env, e);
  document.addEventListener("keydown", keys);

  let typed = 0;
  env.search.addEventListener("input", () => {
    window.clearTimeout(typed);
    typed = window.setTimeout(() => {
      env.query = env.search.value.trim();
      void load(env);
    }, 120);
  });

  const unheard = onNotice((n) => {
    if (n.type === "environment_changed") void load(env);
  });

  if (options.actions) options.actions.append(button("Clear…", () => void clearDialog(env), { class: "ghost env-clear", title: "Clear what is not kept…" }));
  draw(env);
  void load(env).then(() => {
    if (env.tab === "library") void check(env);
  });

  return {
    element: env.element,
    refresh: () => load(env),
    snapshot: () => env.listing,
    show: (kind, name) => setTab(env, kind, name),
    dispose: () => {
      env.disposed = true;
      unheard();
      document.removeEventListener("keydown", keys);
      env.element.remove();
    },
  };
}

// ===== the Workbench's right pane: the same list (it replaced workbenchVariables.ts, 2026-11-22) =====

export interface EnvironmentPane {
  element: HTMLElement;
  refresh: () => Promise<void>;
  snapshot: () => Listing | null;
}

/** The Environment as the Workbench's right pane: the list, narrower, its viewer under it; Insert into code
 *  goes to the focused document (`insert`; false: nothing took it, it is copied). */
export function environmentPane(onClose: () => void, insert: (code: { python?: string; sql?: string }) => boolean): EnvironmentPane {
  const mounted = mountEnvironment({ compact: true, tab: "variable", insert });
  const element = h(
    "section",
    { class: "wb-vars wb-environment", "aria-label": "Environment" },
    h(
      "div",
      { class: "wb-vars-head" },
      h("h2", {}, "Environment"),
      button("Open the Environment page", () => openEnvironment(), { icon: "popout", iconOnly: true, class: "ghost" }),
      button("Hide Environment", onClose, { icon: "close", iconOnly: true, class: "ghost" }),
    ),
    mounted.element,
  );
  return { element, refresh: mounted.refresh, snapshot: mounted.snapshot };
}

// ===== the page =====

let shownPage: PageElement | null = null;
let view: EnvironmentView | null = null;
const isKind = (word: string | null | undefined): word is Kind => KINDS.includes(word as Kind);
/** A tab named in an address: its kind, or the word the tab shows (at=settings, at=libraries). */
const TAB_NAMES: Record<string, Kind> = { tables: "table", variables: "variable", structures: "structure", settings: "setting", secrets: "setting", libraries: "library" };
const asKind = (word: string | null | undefined): Kind | undefined => (isKind(word) ? word : TAB_NAMES[String(word ?? "").toLowerCase()]);

registerLayer("environment", {
  isOpen: () => Boolean(shownPage?.open),
  open: (url) => drawPage(url?.searchParams.get("at"), url?.searchParams.get("name")),
  show: (url) => {
    const at = asKind(url.searchParams.get("at"));
    if (at) view?.show(at, url.searchParams.get("name") ?? undefined);
  },
  dismiss: () => {
    if (shownPage) dismissDialog(shownPage);
  },
});

// The Variables page folded in (2026-11-22): its old address lands on the Settings and secrets tab, at the
// setting it named (open=variables&name=REGION_DEFAULT), with the address put right.
registerLayer("variables", {
  isOpen: () => false,
  open: (url) => {
    const name = url?.searchParams.get("name") ?? undefined;
    void go(withParams({ open: "environment", at: "settings", name: name ?? null, type: null }), "replace").then(() => {
      if (shownPage?.open) view?.show("setting", name);
      else drawPage("setting", name);
    });
  },
  show: () => undefined,
  dismiss: () => undefined,
});

/** The Environment page, opened by the user (the rail's icon) or a link: on `tab`, at the row `name`. */
export function openEnvironment(tab?: Kind, name?: string): void {
  if (shownPage?.open) {
    if (tab) view?.show(tab, name);
    return;
  }
  layerOpened("environment", { at: tab ?? null, name: name ?? null });
  drawPage(tab, name);
}

function drawPage(at?: string | null, name?: string | null): void {
  const { element, body, actions, setHeading } = openAreaPage("environment", "Environment");
  shownPage = element;
  body.classList.add("env-page-body");
  setOverTitle("Environment");
  const project = h("span", { class: "env-project" });
  setHeading("Environment", project);
  view = mountEnvironment({
    tab: asKind(at),
    name: name ?? undefined,
    actions,
    // The tab and the row in the address, replaced (a row is a place, not a step back).
    moved: (tab, row) => {
      if (shownPage === element && element.open) void go(withParams({ open: "environment", at: tab, name: row }), "replace");
      const listing = view?.snapshot();
      project.textContent = listing?.project?.name ?? "";
    },
  });
  const mounted = view;
  body.append(mounted.element);
  void mounted.refresh().then(() => (project.textContent = mounted.snapshot()?.project?.name ?? ""));
  watchLayerDialog(element, "environment", ["at", "name"], () => {
    mounted.dispose();
    if (shownPage === element) shownPage = null;
    if (view === mounted) view = null;
  });
}
