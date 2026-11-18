/**
 * dataExplorer.ts: the Data Explorer (the owner, 2026-11-17: "a pane called Data Explorer that allows us
 * to quickly search by column names, table name, connection to quickly find data like the structures").
 * [SHARED: one component, three hosts]
 *
 *   [HOSTS]    the Data page (dataPage.ts: the rail's Data, open=data; browsing first, dataBrowse.ts), the
 *              Workbench's pane (workbenchExplorer.ts; its Pop out opens the Data page in a window of its
 *              own: the popped-out window and its explorerPage.ts are gone), the grid page's Find data
 *              dialog (Ctrl+K)
 *   [SEARCH]   one box, as you type: connections, their loaded catalogs' tables and columns, the open
 *              tables and their columns, Structures, APIs, variables and blades, grouped and counted
 *              (services/explorer.py). Any case, by parts: cust finds customer_id and CustomerKey
 *   [FILTERS]  a chip per kind (none pressed: every kind), a connection picker, recent searches
 *   [RESULT]   its kind's icon, its name (a column's type), its path, its connection's colour
 *   [ACTIONS]  buttons and a right-click menu; Enter is the first. A table: Open as grid, Preview (its first
 *              rows, nothing kept), Copy SQL name, Insert into the cell, Query in a notebook; a column: Copy
 *              name, Insert, Show tables with this column; a Structures path: Open at this node, Copy path;
 *              a variable: Open in Variables; a blade: Insert its call
 *   [DRAG]     any result into a cell: the code its language writes (EXPLORER_DRAG: a SQL cell's SQL, a
 *              Python cell's Python), from this window or another (the Data page's)
 *   [STATE]    the search, its filters and the scroll: state() and setState(); the Data page's address
 *              carries them when the pane pops out (dataUrl)
 *
 * ROUTING: GET /explorer/search  GET /explorer/browse  POST /connections/{name}/open|preview|catalog
 *          GET /grids/{id}/rows  POST /workbench/window {command: "cell.insertBelow" | "explorer.insert"}
 */
import { api, errorText, onNotice, token } from "./api";
import { DROP_TYPE } from "./catalogRail";
import { queryInNotebook } from "./connectionTree";
import { type BrowseAnswer, mountBrowse } from "./dataBrowse";
import { button, clear, h, icon, showMenu, toast, type MenuItem } from "./dom";
import { tablePreview } from "./pythonConnectionForm";
import { openStructures } from "./structuresPage";
import type { Part } from "./structureTree";

/** A result's drag: {sql, python} (the code for each kind of cell). lazy/codeEditor.ts reads it. */
export const EXPLORER_DRAG = "application/x-sab-explorer";
/** The Data page's window when the pane pops out, by name: one at a time, found again by it. */
export const EXPLORER_WINDOW = "swissarmybench-explorer";

export const KINDS = ["connections", "tables", "columns", "structures", "apis", "variables", "blades"] as const;
export type ResultKind = (typeof KINDS)[number];
const LABELS: Record<ResultKind, string> = { connections: "Connections", tables: "Tables", columns: "Columns", structures: "Structures", apis: "APIs", variables: "Variables", blades: "Blades" };
const KIND_ICONS: Record<ResultKind, string> = { connections: "plug", tables: "table", columns: "columns", structures: "json", apis: "link", variables: "variables", blades: "blade" };

export interface ExplorerResult {
  key: string;
  kind: ResultKind;
  name: string;
  path: string[];
  connection: string | null;
  detail: string;
  icon: string;
  insert: { sql?: string; python?: string };
  sql?: string;
  type?: string;
  source?: "catalog" | "grid";
  grid?: string | null;
  dataset?: string;
  variable?: string;
  place?: { database: string; schema: string; table: string };
  loaded?: boolean;
  [more: string]: unknown;
}

interface Group {
  kind: ResultKind;
  label: string;
  count: number;
  results: ExplorerResult[];
}

export interface Answer {
  groups: Group[];
  total: number;
  offers: { connection: string; state: string; error?: string }[];
}

export interface ExplorerState {
  text: string;
  kinds: string[];
  connection: string;
  /** Show tables with this column: the column's name ("" for none). */
  column: string;
  scroll: number;
}

export const EMPTY_STATE: ExplorerState = { text: "", kinds: [], connection: "", column: "", scroll: 0 };

export interface ExplorerHost {
  /** Insert a result's code into the cell; where it went, in words. Null: this host has no cell. */
  insert: ((result: ExplorerResult) => Promise<string>) | null;
  /** The cell an Insert goes into, in words, for the button's title ("the selected cell of sales.ipynb"). */
  target: () => string;
  /** An open table's grid shown. */
  showGrid: (grid: string, dataset: string) => void;
  /** The Variables page, at a variable. */
  openVariable: (name: string) => void;
  /** A Structures result: its document opened at that node (default: the Structures page, here). */
  openStructure?: (result: ExplorerResult) => void;
  /** The search, a filter or the scroll changed (the host keeps it for the window). */
  changed?: (state: ExplorerState) => void;
  /** The Data page: with nothing typed it browses (a tree), and a table's detail shows beside it. */
  browse?: boolean;
  /** Whether Insert has a cell to go to now (default: whenever the host has an insert). */
  canInsert?: () => boolean;
}

export interface Explorer {
  element: HTMLElement;
  focus: () => void;
  state: () => ExplorerState;
  setState: (state: ExplorerState) => void;
  /** Search again (a catalog loaded, a table opened). */
  refresh: () => void;
  /** The last answer (the agent's explorer.results). */
  answer: () => Answer | null;
}

const RECENT_KEY = "explorer-recent";
const RECENT_MAX = 8;
const DEBOUNCE_MS = 150;

function recentSearches(): string[] {
  try {
    const list = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]") as unknown;
    return Array.isArray(list) ? list.filter((s): s is string => typeof s === "string").slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

function keepRecent(text: string): void {
  const words = text.trim();
  if (!words) return;
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify([words, ...recentSearches().filter((s) => s !== words)].slice(0, RECENT_MAX)));
  } catch {
    /* storage blocked: no recent searches */
  }
}

const copyText = (text: string, what: string): void =>
  void navigator.clipboard.writeText(text).then(
    () => toast(`Copied ${what}`),
    () => toast("The browser did not allow copying.", "error"),
  );

/** The imports a result's Python needs, for a drop that places a whole cell. */
function importsOf(code: string): string[] {
  const out: string[] = [];
  if (/\bsab\./.test(code)) out.push("import swissarmybench as sab");
  if (/\bos\.environ\b/.test(code)) out.push("import os");
  return out;
}

/** The Data page's address with a search (open=data; q, kinds, connection, column when set). */
export function dataUrl(state: ExplorerState): string {
  const params = new URLSearchParams({ open: "data" });
  if (state.text) params.set("q", state.text);
  if (state.kinds.length) params.set("kinds", state.kinds.join(","));
  if (state.connection) params.set("connection", state.connection);
  if (state.column) params.set("column", state.column);
  return `/workspace?${params.toString()}`;
}

/** The Data page in a window of its own with this search (the Workbench pane's Pop out): the pop-out and the
 *  Data page are one page (the owner, 2026-11-17). */
export function openDataWindow(state: ExplorerState): Window {
  const opened = window.open(`${dataUrl(state)}#${new URLSearchParams({ token }).toString()}`, EXPLORER_WINDOW);
  if (!opened) throw new Error("The browser blocked the new window. Allow pop-ups for this address.");
  opened.focus();
  return opened;
}

/** A result's drag: the code each kind of cell writes (EXPLORER_DRAG), the text, a Python cell's whole. */
export function dragData(r: { insert: { sql?: string; python?: string }; sql?: string; name: string }, e: DragEvent): void {
  const plain = r.insert.python ?? r.insert.sql ?? r.sql ?? r.name;
  e.dataTransfer?.setData("text/plain", plain);
  e.dataTransfer?.setData(EXPLORER_DRAG, JSON.stringify(r.insert));
  if (r.insert.python) e.dataTransfer?.setData(DROP_TYPE, JSON.stringify({ code: r.insert.python, imports: importsOf(r.insert.python) }));
  if (e.dataTransfer) e.dataTransfer.effectAllowed = "copy";
}

/** A Structures result's document on the Structures page, at its node: an open one by its id, a saved
 *  file opened first. */
export async function openStructureAt(r: ExplorerResult): Promise<void> {
  let id = typeof r.structure === "string" ? r.structure : null;
  if (!id && typeof r.file === "string") id = (await api<{ id: string }>("/structures/open", "POST", { path: r.file })).id;
  openStructures(id, Array.isArray(r.parts) ? (r.parts as Part[]) : null);
}

export function mountExplorer(host: ExplorerHost): Explorer {
  let state: ExplorerState = { ...EMPTY_STATE };
  let last: Answer | null = null;
  let asked = 0;
  let timer: number | null = null;
  let selectedKey: string | null = null;
  let connectionNames: string[] = [];

  const input = h("input", {
    type: "search",
    class: "ex-search",
    placeholder: "Find data",
    "aria-label": "Find data: tables, columns, connections",
    autocomplete: "off",
    spellcheck: "false",
  }) as HTMLInputElement;
  const chips = h("div", { class: "ex-chips", role: "group", "aria-label": "Kinds" });
  const picker = h("select", { class: "ex-connection", "aria-label": "Connection" }) as HTMLSelectElement;
  const columnChip = h("div", { class: "ex-column-chip", hidden: true });
  const recent = h("div", { class: "ex-recent", "aria-label": "Recent searches" });
  const offers = h("div", { class: "ex-offers" });
  const results = h("div", { class: "ex-results", role: "region", "aria-label": "Results" });
  // The Data page: the tree and the detail side in the results' place (dataBrowse.ts).
  let browsed: BrowseAnswer | null = null;
  const browse = host.browse
    ? mountBrowse({
        actions: (r, under) => actions(r as ExplorerResult, under),
        drag: (r, e) => dragData(r, e),
        only: (name) => {
          state.connection = name;
          drawPicker();
          searchNow();
        },
        loadCatalog: (name) => loadCatalog(name),
        search: input,
      })
    : null;
  if (browse) {
    results.classList.add("ex-results-browse");
    results.append(browse.element);
  }
  const element = h(
    "div",
    { class: browse ? "ex ex-browse" : "ex" },
    h("div", { class: "ex-head" }, h("span", { class: "ex-search-wrap" }, icon("zoom"), input), h("div", { class: "ex-filters" }, chips, picker), columnChip, recent),
    offers,
    results,
  );

  // ----- the filters
  function drawChips(): void {
    clear(
      chips,
      ...KINDS.map((kind) =>
        button(LABELS[kind], () => {
          const on = state.kinds.includes(kind);
          state.kinds = on ? state.kinds.filter((k) => k !== kind) : [...state.kinds, kind];
          drawChips();
          searchNow();
        }, { class: "ex-chip", pressed: state.kinds.includes(kind) }),
      ),
    );
  }

  function drawPicker(): void {
    const names = [...new Set([...connectionNames, ...(state.connection ? [state.connection] : [])])];
    clear(picker, h("option", { value: "" }, "All connections"), ...names.map((n) => h("option", { value: n, selected: n === state.connection }, n)));
    picker.value = state.connection;
  }
  picker.addEventListener("change", () => {
    state.connection = picker.value;
    searchNow();
  });

  async function loadConnections(): Promise<void> {
    try {
      const listed = await api<Answer>("/explorer/search?kinds=connections&limit=200");
      connectionNames = listed.groups.flatMap((g) => g.results.map((r) => r.name));
    } catch {
      connectionNames = [];
    }
    drawPicker();
  }

  function drawColumnChip(): void {
    columnChip.hidden = !state.column;
    if (!state.column) return clear(columnChip);
    clear(
      columnChip,
      h("span", {}, icon("columns"), `Tables with ${state.column}`),
      button("Show every result", () => {
        state.column = "";
        drawColumnChip();
        searchNow();
      }, { icon: "close", iconOnly: true, class: "ghost small" }),
    );
  }

  function drawRecent(): void {
    const list = state.text || state.column ? [] : recentSearches();
    recent.hidden = !list.length;
    clear(recent, ...list.map((text) => button(text, () => {
      input.value = text;
      state.text = text;
      searchNow();
    }, { icon: "history", class: "ex-recent-item ghost small" })));
  }

  // ----- the search
  function searchSoon(): void {
    if (timer !== null) window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      timer = null;
      void search();
    }, DEBOUNCE_MS);
  }

  function searchNow(): void {
    if (timer !== null) window.clearTimeout(timer);
    timer = null;
    void search();
  }

  input.addEventListener("input", () => {
    state.text = input.value;
    selectedKey = null;
    searchSoon();
  });

  async function search(keepScroll = false): Promise<void> {
    const n = ++asked;
    const params = new URLSearchParams();
    if (state.text.trim()) params.set("q", state.text.trim());
    if (state.kinds.length) params.set("kinds", state.kinds.join(","));
    if (state.connection) params.set("connection", state.connection);
    if (state.column) params.set("column", state.column);
    drawRecent();
    drawColumnChip();
    host.changed?.(state);
    try {
      const typed = Boolean(state.text.trim() || state.column);
      if (browse) {
        // The Data page: with nothing typed, the tree; typed, the tree narrowed to what matches.
        const filters = new URLSearchParams();
        if (state.kinds.length) filters.set("kinds", state.kinds.join(","));
        if (state.connection) filters.set("connection", state.connection);
        const [tree, answer] = await Promise.all([
          !typed || !browsed ? api<BrowseAnswer>(`/explorer/browse?${filters.toString()}`) : Promise.resolve(browsed),
          typed ? api<Answer>(`/explorer/search?${params.toString()}`) : Promise.resolve(null),
        ]);
        if (n !== asked) return;
        browsed = tree;
        last = answer;
        if (answer) {
          drawOffers(answer);
          browse.showSearch(answer, tree);
        } else {
          clear(offers);
          browse.showBrowse(tree);
        }
        element.dataset.searched = state.text.trim() || state.column;
        element.dataset.browsed = typed ? "" : "1";
        return;
      }
      const answer = await api<Answer>(`/explorer/search?${params.toString()}`);
      if (n !== asked) return; // a newer search is on its way
      last = answer;
      draw();
      if (!keepScroll) results.scrollTop = 0;
      element.dataset.searched = state.text.trim() || state.column;
    } catch (e) {
      if (n !== asked) return;
      if (browse) clear(offers, h("p", { class: "status-error" }, errorText(e)));
      else clear(results, h("p", { class: "status-error" }, errorText(e)));
    }
  }

  input.addEventListener("blur", () => keepRecent(state.text));
  results.addEventListener("scroll", () => {
    state.scroll = results.scrollTop;
    host.changed?.(state);
  });

  // ----- a result's actions
  interface Action {
    label: string;
    icon: string;
    run: () => void | Promise<void>;
    title?: string;
  }

  const openTable = async (r: ExplorerResult): Promise<void> => {
    if (r.source === "grid") {
      if (r.grid) host.showGrid(r.grid, String(r.dataset ?? r.name));
      return;
    }
    if (!r.connection || !r.place) return;
    try {
      const got = await api<{ dataset?: string }>(`/connections/${encodeURIComponent(r.connection)}/open`, "POST", r.place);
      toast(`${got.dataset ?? r.name} is open as a grid.`);
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  const preview = async (r: ExplorerResult, under: HTMLElement): Promise<void> => {
    if (under.childElementCount) return clear(under);
    clear(under, h("p", { class: "hint" }, "Loading…"));
    try {
      const got =
        r.source === "grid" && r.grid
          ? await api<{ columns: string[]; rows: unknown[][]; row_count: number }>(`/grids/${encodeURIComponent(r.grid)}/rows?start=0&end=20`).then((g) => ({ columns: g.columns, rows: g.rows, total: g.row_count }))
          : await api<{ columns: string[]; rows: unknown[][] }>(`/connections/${encodeURIComponent(r.connection ?? "")}/preview`, "POST", r.place).then((g) => ({ ...g, total: null }));
      clear(under, ...tablePreview({ table: r.name, schema: r.place?.schema ?? "", columns: got.columns, rows: got.rows, total: got.total }));
    } catch (e) {
      clear(under, h("p", { class: "status-error" }, errorText(e)));
    }
  };

  const insert = async (r: ExplorerResult): Promise<void> => {
    if (!host.insert) return;
    try {
      toast(`${r.name} is in ${await host.insert(r)}.`);
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  const loadCatalog = async (connection: string): Promise<void> => {
    try {
      await api(`/connections/${encodeURIComponent(connection)}/catalog`, "POST");
      toast(`Loading ${connection}'s catalog…`);
      void search(true);
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  function actions(r: ExplorerResult, under: HTMLElement): Action[] {
    const into = host.insert && (host.canInsert?.() ?? true) ? [{ label: "Insert", icon: "plus", title: `Insert into ${host.target()}`, run: () => insert(r) }] : [];
    switch (r.kind) {
      case "connections":
        return [
          { label: "Show its tables", icon: "table", run: () => {
            state = { ...state, connection: r.name, kinds: ["tables"], column: "" };
            drawPicker();
            drawChips();
            searchNow();
          } },
          ...(r.loaded === false ? [{ label: "Load its catalog", icon: "import", run: () => loadCatalog(r.name) }] : []),
          { label: "Copy name", icon: "copy", run: () => copyText(r.name, r.name) },
        ];
      case "tables": {
        const sql = r.source === "grid" ? String(r.variable ?? r.name) : (r.sql ?? r.name);
        const opens = r.source === "grid" || (r.connection && r.place);
        const query = r.source === "grid" ? String(r.variable ?? r.name) : (r.sql ?? null);
        return [
          ...(opens ? [{ label: "Open as grid", icon: "rows", run: () => openTable(r) }] : []),
          ...(opens ? [{ label: "Preview", icon: "eye", run: () => preview(r, under) }] : []),
          { label: r.source === "grid" ? "Copy name" : "Copy SQL name", icon: "copy", title: sql, run: () => copyText(sql, sql) },
          ...into,
          ...(query ? [{ label: "Query in a notebook", icon: "notebook", run: () => queryInNotebook(query) }] : []),
        ];
      }
      case "columns":
        return [
          { label: "Copy name", icon: "copy", run: () => copyText(r.name, r.name) },
          ...into,
          { label: "Show tables with this column", icon: "link", run: () => {
            state = { ...state, column: r.name, text: "" };
            input.value = "";
            searchNow();
          } },
        ];
      case "structures": {
        const open = host.openStructure ?? ((x: ExplorerResult) => void openStructureAt(x).catch((e: unknown) => toast(errorText(e), "error")));
        const pointer = String(r.pointer ?? "$");
        return [
          { label: pointer === "$" ? "Open" : "Open at this node", icon: "json", run: () => open(r) },
          { label: "Copy path", icon: "copy", title: pointer, run: () => copyText(pointer, pointer) },
        ];
      }
      case "apis": {
        const sql = r.sql ?? r.name;
        return [
          { label: "Copy SQL name", icon: "copy", title: sql, run: () => copyText(sql, sql) },
          ...into,
          ...(r.sql ? [{ label: "Query in a notebook", icon: "notebook", run: () => queryInNotebook(sql) }] : []),
        ];
      }
      case "variables":
        return [
          { label: "Open in Variables", icon: "variables", run: () => host.openVariable(r.name) },
          { label: "Copy name", icon: "copy", run: () => copyText(r.name, r.name) },
          ...into,
        ];
      case "blades":
        return [...(host.insert && (host.canInsert?.() ?? true) ? [{ label: "Insert its call", icon: "plus", title: `Insert into ${host.target()}`, run: () => insert(r) }] : []), { label: "Copy its call", icon: "copy", run: () => copyText(r.insert.python ?? r.name, "the call") }];
      default:
        return [...into, { label: "Copy name", icon: "copy", run: () => copyText(r.name, r.name) }];
    }
  }

  // ----- the results
  function row(r: ExplorerResult): HTMLElement {
    const under = h("div", { class: "ex-preview" });
    const own = actions(r, under);
    const where = r.path.join(" › ");
    const item = h(
      "li",
      {
        class: `ex-result kind-${r.kind}${r.key === selectedKey ? " selected" : ""}`,
        tabindex: "-1",
        draggable: "true",
        dataset: { key: r.key, kind: r.kind },
        ...(r.connection ? { "data-connections": r.connection } : {}),
        "aria-label": `${r.name}${where ? `, ${where}` : ""}`,
      },
      h(
        "div",
        { class: "ex-line" },
        h("span", { class: "ex-icon", "aria-hidden": "true" }, icon(r.source === "grid" && r.kind === "tables" ? "grids" : KIND_ICONS[r.kind])),
        h("span", { class: "ex-name" }, r.name),
        r.type ? h("span", { class: "ex-type" }, r.type) : null,
        h("span", { class: "ex-actions" }, ...own.map((a) => button(a.label, (e) => {
          e.stopPropagation();
          select(r.key);
          void a.run();
        }, { icon: a.icon, iconOnly: true, class: "ghost small", title: a.title ?? a.label }))),
      ),
      where || r.detail ? h("div", { class: "ex-where" }, where ? h("span", { class: "ex-path" }, where) : null, r.detail ? h("span", { class: "ex-detail" }, r.detail) : null) : null,
      under,
    );
    item.addEventListener("click", () => select(r.key));
    item.addEventListener("dblclick", () => void own[0]?.run());
    item.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      select(r.key);
      showMenu(e.clientX, e.clientY, r.name, own.map((a): MenuItem => [a.icon, a.label, () => void a.run()]));
    });
    item.addEventListener("dragstart", (e) => dragData(r, e));
    return item;
  }

  function drawOffers(answer: Answer): void {
    clear(
      offers,
      ...answer.offers.map((o) =>
        h(
          "div",
          { class: "ex-offer", "data-connections": o.connection },
          h("span", {}, icon("plug"), o.state === "loading" ? `${o.connection}: loading its catalog…` : o.state === "failed" ? `${o.connection}: its catalog did not load${o.error ? ` (${o.error})` : ""}` : `${o.connection}: its tables are not searched yet`),
          o.state === "loading" ? null : button("Load its catalog", () => void loadCatalog(o.connection), { icon: "import", class: "small line" }),
        ),
      ),
    );
  }

  function draw(): void {
    const answer = last;
    if (!answer) return;
    drawOffers(answer);
    clear(
      results,
      ...answer.groups.map((g) =>
        h(
          "section",
          { class: "ex-group", dataset: { kind: g.kind }, "aria-label": g.label },
          h("h3", {}, icon(KIND_ICONS[g.kind]), h("span", {}, g.label), h("span", { class: "ex-count" }, g.count.toLocaleString())),
          h("ul", { class: "ex-list", "aria-label": g.label }, ...g.results.map(row)),
          g.count > g.results.length ? h("p", { class: "ex-more" }, `${(g.count - g.results.length).toLocaleString()} more: type more of the name`) : null,
        ),
      ),
      answer.groups.length ? null : h("p", { class: "empty-note" }, state.text.trim() || state.column ? "Nothing matches" : "No data yet"),
    );
  }

  const flat = (): ExplorerResult[] => (last?.groups ?? []).flatMap((g) => g.results);

  function select(key: string | null): void {
    selectedKey = key;
    for (const li of results.querySelectorAll<HTMLElement>(".ex-result")) li.classList.toggle("selected", li.dataset.key === key);
    results.querySelector<HTMLElement>(".ex-result.selected")?.scrollIntoView({ block: "nearest" });
  }

  // Keys: the arrows move through the results, Enter runs the selected one's first action.
  element.addEventListener("keydown", (e) => {
    if ((e.target as HTMLElement).closest("select, button")) return;
    if (browse) {
      // The Data page's tree has its own keys (dataBrowse.ts); from the search box, Down goes into it.
      if (e.target === input && e.key === "ArrowDown") {
        e.preventDefault();
        browse.focus();
      }
      if (e.target === input && e.key === "Enter") keepRecent(state.text);
      return;
    }
    const list = flat();
    if (!list.length) return;
    const at = list.findIndex((r) => r.key === selectedKey);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next = e.key === "ArrowDown" ? Math.min(list.length - 1, at + 1) : Math.max(0, at - 1);
      select(list[next]!.key);
    } else if (e.key === "Enter") {
      e.preventDefault();
      keepRecent(state.text);
      const r = list[at < 0 ? 0 : at]!;
      const li = results.querySelector<HTMLElement>(`.ex-result[data-key="${CSS.escape(r.key)}"]`);
      void actions(r, li?.querySelector<HTMLElement>(".ex-preview") ?? h("div"))[0]?.run();
    }
  });

  onNotice((notice) => {
    if (!element.isConnected) return;
    const watched = ["catalogs_changed", "blades_changed", "dataset_updated", "dataset_closed", "dataset_renamed", "grid_shown", "grid_closed", "variables_changed"];
    // The Data page also follows a catalog's loading (its status) and Structures.
    if (browse) watched.push("catalog_loading", "structures_changed");
    if (watched.includes(notice.type)) {
      if (browse) browsed = null; // the tree read again
      if (notice.type === "blades_changed") void loadConnections();
      void search(true);
    }
  });

  drawChips();
  drawPicker();
  drawColumnChip();
  drawRecent();
  void loadConnections();
  void search();

  return {
    element,
    focus: () => {
      input.focus();
      input.select();
    },
    state: () => ({ ...state, kinds: [...state.kinds], scroll: results.scrollTop }),
    setState: (next) => {
      state = { ...EMPTY_STATE, ...next, kinds: [...(next.kinds ?? [])] };
      input.value = state.text;
      drawChips();
      drawPicker();
      const scroll = state.scroll;
      void search(true).then(() => {
        results.scrollTop = scroll;
      });
    },
    refresh: () => {
      browse?.actionsChanged();
      void search(true);
    },
    answer: () => last,
  };
}
