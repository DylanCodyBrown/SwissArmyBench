/**
 * dataBrowse.ts: the Data page's tree and its detail side (the owner, 2026-11-17: "yea I said a long time
 * ago we needed a standalone DATA rail icon and page"; "we dont even need catalog if its just tables"): the
 * Data Explorer (dataExplorer.ts) on its fourth host, where browsing is first-class. [SHARED: a view of
 * dataExplorer.ts, never a page of its own]
 *
 *   [BROWSE]  nothing typed: each connection a group with its colour and status, its tables under it by
 *             database and schema (a Power BI workspace's datasets), each table's columns and types when it
 *             opens; a connection whose catalog is not loaded offers Load (catalog_loading). Then the open
 *             tables (and their columns), Structures (documents and paths), the APIs' tables, the blades
 *             whose result is a table (GET /explorer/browse)
 *   [SEARCH]  typed: the same tree, narrowed to what matches (GET /explorer/search): a matched column under
 *             its table, a table under its connection and schema; the other kinds as their own groups
 *   [ACTIONS] a table's are the Explorer's own (Open as grid, Preview, Copy SQL name, Insert, Query in a
 *             notebook); a connection's Load, Show only this; a dataset's or schema's Import its
 *             relationships (Power BI, SQL Server)
 *   [DETAIL]  the selected table: its columns (name, type, nulls), where it comes from, its SQL name, the
 *             code that reads it (a SQL cell's, a Python cell's), and its actions (GET /explorer/table)
 *   [KEYS]    the arrows move through the tree (Right opens, Left closes or goes up), Enter runs a table's
 *             first action (Open as grid), a group's Enter opens it; / focuses the search (the page's)
 *   [DRAG]    a table or a column into a Workbench cell (EXPLORER_DRAG, as every Explorer result)
 *
 * ROUTING: GET /explorer/browse  GET /explorer/table  POST /connections/{name}/relationships {dataset}
 */
import { api, errorText } from "./api";
import { button, clear, h, icon, recall, remember, showMenu, toast, type MenuItem } from "./dom";
import { busyClick, loadingBlock } from "./loading";
import { errorHere, errorMark, errorNote } from "./errorNote";

/** A result as the Explorer has it (dataExplorer.ts's ExplorerResult, kept loose here to avoid a cycle). */
export interface BrowseResult {
  key: string;
  kind: string;
  name: string;
  path: string[];
  connection: string | null;
  detail: string;
  icon: string;
  insert: { sql?: string; python?: string };
  sql?: string;
  type?: string;
  source?: string;
  place?: { database: string; schema: string; table: string };
  children?: BrowseResult[];
  [more: string]: unknown;
}

interface BrowseGroup {
  database: string;
  schema: string;
  count: number;
  tables: BrowseResult[];
}

export interface BrowseConnection {
  name: string;
  type: string;
  tables_kind: string;
  group_icon?: string;
  group: string;
  state: { state: string; error?: string };
  loaded: boolean;
  count: number;
  relationships: boolean;
  needs_password: boolean;
  groups: BrowseGroup[];
}

export interface BrowseAnswer {
  connections: BrowseConnection[];
  sections: { kind: string; label: string; count: number; items: BrowseResult[] }[];
}

interface SearchAnswer {
  groups: { kind: string; label: string; count: number; results: BrowseResult[] }[];
  offers: { connection: string; state: string; error?: string }[];
}

interface TableDetail {
  connection: string;
  place: { database: string; schema: string; table: string };
  where: string[];
  sql: string;
  columns: { name: string; type: string | null; nullable: string | boolean | null }[];
  code: { sql: string; python: string };
  relationships: boolean;
}

export interface BrowseAction {
  label: string;
  icon: string;
  run: () => void | Promise<void>;
  title?: string;
}

export interface BrowseContext {
  /** A result's actions (dataExplorer.ts's own); `under` is where Preview draws. */
  actions: (r: BrowseResult, under: HTMLElement) => BrowseAction[];
  /** A drag's data (dataExplorer.ts's dragData). */
  drag: (r: BrowseResult, e: DragEvent) => void;
  /** The connection picker set to `name` (Show only this). */
  only: (name: string) => void;
  loadCatalog: (name: string) => Promise<void>;
  /** The search box (/ focuses it). */
  search: HTMLInputElement;
}

interface Node {
  key: string;
  label: string;
  icon: string;
  kind: "connection" | "group" | "table" | "column" | "section" | "item";
  result?: BrowseResult;
  connection?: BrowseConnection;
  group?: BrowseGroup;
  type?: string;
  note?: string;
  status?: string;
  children: Node[] | null; // null: none; [] with `lazy`: loaded when it opens
  lazy?: () => Promise<Node[]>;
  open: boolean;
  draggable?: boolean;
}

const plain = /^[A-Za-z_][A-Za-z0-9_]*$/;
const columnInsert = (name: string): { sql: string; python: string } => ({ sql: plain.test(name) ? name : `"${name.replace(/"/g, '""')}"`, python: JSON.stringify(name) });

const copy = (text: string): void =>
  void navigator.clipboard.writeText(text).then(
    () => toast(`Copied ${text.length > 60 ? "the code" : text}`),
    () => errorHere("The browser did not allow copying."),
  );

function stateWords(c: BrowseConnection): string {
  if (c.needs_password) return "Needs a password";
  switch (c.state.state) {
    case "loading":
    case "waiting":
      return "Loading its tables…";
    case "failed":
      return "Its tables did not load";
    default:
      return c.loaded ? `${c.count.toLocaleString()} table${c.count === 1 ? "" : "s"}` : "Not loaded";
  }
}

export interface Browse {
  /** The tree and the detail side, side by side. */
  element: HTMLElement;
  showBrowse: (answer: BrowseAnswer) => void;
  showSearch: (answer: SearchAnswer, browsed: BrowseAnswer | null) => void;
  /** A table's detail shown, by its result (the agent's and the tests' way in). */
  select: (key: string) => void;
  /** Focus the tree: the selected item, else the first. */
  focus: () => void;
  /** The open detail's buttons drawn again: what they offer changed (the Workbench's document in front came
   *  or went, so Insert shows or goes) while the detail was open. */
  actionsChanged: () => void;
}

export function mountBrowse(ctx: BrowseContext): Browse {
  const tree = h("ul", { class: "db-tree", role: "tree", "aria-label": "Data" });
  const empty = h("p", { class: "empty-note", hidden: true });
  const detail = h("aside", { class: "db-detail", "aria-label": "Table", hidden: true });
  const element = h("div", { class: "db-body" }, h("div", { class: "db-main" }, tree, empty), detail);
  const opened = new Set<string>(); // the keys open, kept across redraws (a search, a notice)
  const columnsOf = new Map<string, Promise<TableDetail>>();
  let roots: Node[] = [];
  let selectedKey: string | null = null;
  /** The open detail's buttons, drawn again (actionsChanged). */
  let redrawActions: (() => void) | null = null;
  let searching = false;

  // ----- the nodes
  const tableDetail = (r: BrowseResult): Promise<TableDetail> => {
    const place = r.place ?? { database: "", schema: "", table: r.name };
    const key = `${r.connection}\u0000${place.database}\u0000${place.schema}\u0000${place.table}`;
    let found = columnsOf.get(key);
    if (!found) {
      found = api<TableDetail>(`/explorer/table?${new URLSearchParams({ connection: r.connection ?? "", ...place }).toString()}`);
      found.catch(() => columnsOf.delete(key));
      columnsOf.set(key, found);
    }
    return found;
  };

  const columnNode = (parent: string, name: string, type: string | null | undefined, r?: BrowseResult): Node => ({
    key: `${parent}/${name}`,
    label: name,
    icon: "columns",
    kind: "column",
    type: type ?? undefined,
    result: r ?? { key: `${parent}/${name}`, kind: "columns", name, path: [], connection: null, detail: "", icon: "columns", insert: columnInsert(name) },
    children: null,
    open: false,
    draggable: true,
  });

  const tableNode = (r: BrowseResult, matched: BrowseResult[] = []): Node => {
    const catalog = r.source === "catalog";
    const kids = r.children ?? [];
    const node: Node = {
      key: r.key,
      label: r.name,
      icon: r.source === "grid" ? "grids" : r.kind === "structures" ? "json" : r.kind === "apis" ? "link" : r.kind === "blades" ? "blade" : "rows",
      kind: r.kind === "tables" || r.kind === "apis" ? "table" : "item",
      result: r,
      note: r.kind === "structures" ? (r.pointer === "$" ? r.detail : String(r.pointer ?? "")) : r.detail,
      children: matched.length ? matched.map((c) => columnNode(r.key, c.name, c.type, c)) : kids.length ? kids.map((c) => (c.kind === "columns" ? columnNode(r.key, c.name, c.type, c) : tableNode(c))) : catalog ? [] : null,
      open: matched.length > 0,
      draggable: Boolean(r.insert.sql || r.insert.python),
    };
    if (catalog && !matched.length) node.lazy = async () => (await tableDetail(r)).columns.map((c) => columnNode(r.key, c.name, c.type));
    return node;
  };

  const groupNode = (c: BrowseConnection, g: BrowseGroup, tables: Node[], open: boolean): Node => ({
    key: `group/${c.name}/${g.database}/${g.schema}`,
    label: g.schema || g.database || c.name,
    icon: c.group_icon ?? "folder", // the server's, by its kind (datasets, or schemas)
    kind: "group",
    connection: c,
    group: g,
    note: String(g.count),
    children: tables,
    open,
  });

  const connectionNode = (c: BrowseConnection, groups: Node[], open: boolean): Node => ({
    key: `connection/${c.name}`,
    label: c.name,
    icon: "plug",
    kind: "connection",
    connection: c,
    note: c.type,
    status: stateWords(c),
    children: groups,
    open,
  });

  /** A connection's groups as the tree draws them: one unnamed group's tables straight under it. */
  const groupsOf = (c: BrowseConnection, groups: BrowseGroup[], tablesOf: (g: BrowseGroup) => Node[], open: boolean): Node[] => {
    if (groups.length === 1 && !groups[0]!.schema && !groups[0]!.database) return tablesOf(groups[0]!);
    return groups.map((g) => groupNode(c, g, tablesOf(g), open || groups.length === 1));
  };

  const sectionNode = (kind: string, label: string, items: Node[]): Node => ({ key: `section/${kind}`, label, icon: { open: "grids", structures: "structures", apis: "apis", blades: "blade", variables: "variables", connections: "plug", shared: "folder" }[kind] ?? "rows", kind: "section", note: String(items.length), children: items, open: true });

  // ----- drawing
  /** The Sandbox section's tables in the order this browser chose (the sandbox list's own sort: name, rows,
   *  source, created, last changed), its columns kept under each. */
  const SANDBOX_SORTS: [string, string][] = [["name", "Name"], ["rows", "Rows"], ["source", "Source"], ["created", "Created"], ["changed", "Last changed"]];
  function sandboxOrder<T extends { kind: string; name: string; [more: string]: unknown }>(items: T[]): T[] {
    const [by, order] = (recall("sandbox.sort") ?? "name asc").split(" ");
    const value = (r: T): string | number =>
      by === "rows" ? Number(r.rows ?? 0) : by === "source" ? String(r.source_words ?? "").toLowerCase() : by === "created" ? String(r.added_at ?? "") : by === "changed" ? String(r.changed_at || r.added_at || "") : r.name.toLowerCase();
    const tables = items.filter((r) => r.kind === "tables").sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
    tables.sort((a, b) => {
      const x = value(a), y = value(b);
      const c = x < y ? -1 : x > y ? 1 : 0;
      return order === "desc" ? -c : c;
    });
    return [...tables, ...items.filter((r) => r.kind !== "tables")];
  }
  function sortSandbox(x: number, y: number): void {
    const [by, order] = (recall("sandbox.sort") ?? "name asc").split(" ");
    showMenu(x, y, "Sort the sandbox's tables", SANDBOX_SORTS.map(([key, words]): MenuItem => [key === by ? (order === "desc" ? "sortdown" : "sortup") : "rows", words, () => {
      remember("sandbox.sort", `${key} ${key === by && order === "asc" ? "desc" : "asc"}`);
      resort();
    }]));
  }
  let resort: () => void = () => undefined;

  function visible(): HTMLElement[] {
    return [...tree.querySelectorAll<HTMLElement>("[role=treeitem]")].filter((li) => !li.closest("[role=group][hidden]"));
  }

  function rowOf(node: Node, depth: number): HTMLElement {
    const isOpen = node.children !== null && (opened.has(node.key) || (node.open && !opened.has(`!${node.key}`)));
    const under = h("div", { class: "ex-preview" });
    const own: BrowseAction[] = [];
    if (node.result && (node.kind === "table" || node.kind === "item" || node.kind === "column")) own.push(...ctx.actions(node.result, under));
    const c = node.connection;
    if (node.kind === "connection" && c) {
      if (!c.loaded && c.state.state !== "loading" && c.state.state !== "waiting") own.push({ label: "Load", icon: "import", title: `Load ${c.name}'s tables`, run: () => ctx.loadCatalog(c.name) });
      own.push({ label: "Show only this", icon: "filter", run: () => ctx.only(c.name) });
      own.push({ label: "Copy name", icon: "copy", run: () => copy(c.name) });
    }
    if (node.kind === "section" && node.key === "section/sandbox") {
      own.push({ label: "Sort", icon: "sortup", title: "Sort the sandbox's tables", run: () => {
        const at = item.getBoundingClientRect();
        sortSandbox(at.left + 24, at.top + 24);
      } });
    }
    if (node.kind === "group" && c && node.group && c.relationships) {
      const g = node.group;
      own.push({ label: "Import its relationships", icon: "diagram", run: () => importRelationships(c.name, g.schema) });
    }
    const caret =
      node.children !== null
        ? h("span", { class: "db-caret", "aria-hidden": "true" }, icon(isOpen ? "down" : "expand"))
        : h("span", { class: "db-caret", "aria-hidden": "true" });
    const line = h(
      "div",
      { class: "db-line", style: `--depth:${depth}`, ...(node.kind === "connection" && c ? { "data-connections": c.name } : {}) },
      caret,
      h("span", { class: "db-icon", "aria-hidden": "true" }, icon(node.icon)),
      h("span", { class: "db-name" }, node.label),
      node.type ? h("span", { class: "db-type" }, node.type) : null,
      node.note ? h("span", { class: "db-note" }, node.note) : null,
      node.status ? h("span", { class: `db-status state-${c?.needs_password ? "password" : (c?.state.state ?? "none")}`, title: c?.state.error ?? "" }, node.status) : null,
      own.length
        ? h("span", { class: "db-actions" }, ...own.map((a) => button(a.label, (e) => {
            e.stopPropagation();
            select(node);
            void a.run();
          }, { icon: a.icon, iconOnly: node.kind !== "connection" || a.label !== "Load", class: node.kind === "connection" && a.label === "Load" ? "small line" : "ghost small", title: a.title ?? a.label })))
        : null,
    );
    const item = h(
      "li",
      {
        role: "treeitem",
        class: `db-node kind-${node.kind}${node.key === selectedKey ? " selected" : ""}`,
        tabindex: "-1",
        "aria-label": node.label,
        "aria-selected": String(node.key === selectedKey),
        ...(node.children !== null ? { "aria-expanded": String(isOpen) } : {}),
        dataset: { key: node.key, kind: node.kind, ...(node.result?.kind ? { result: node.result.kind } : {}) },
        ...(c || node.result?.connection ? { "data-connections": c?.name ?? node.result?.connection ?? "" } : {}),
        draggable: node.draggable ? "true" : undefined,
      },
      line,
      under,
    );
    (item as HTMLElement & { node?: Node }).node = node;
    line.addEventListener("click", () => {
      select(node);
      if (node.children !== null && node.kind !== "table") toggle(node, item);
    });
    caret.addEventListener("click", (e) => {
      e.stopPropagation();
      toggle(node, item);
    });
    line.addEventListener("dblclick", () => void own[0]?.run());
    line.addEventListener("contextmenu", (e) => {
      if (!own.length) return;
      e.preventDefault();
      select(node);
      showMenu(e.clientX, e.clientY, node.label, own.map((a): MenuItem => [a.icon, a.label, () => void a.run()]));
    });
    if (node.draggable && node.result) item.addEventListener("dragstart", (e) => {
      e.stopPropagation();
      ctx.drag(node.result!, e);
    });
    if (node.children !== null) {
      const kids = h("ul", { role: "group", class: "db-kids", hidden: !isOpen });
      item.append(kids);
      if (isOpen) fill(node, kids, depth + 1);
    }
    return item;
  }

  function fill(node: Node, kids: HTMLElement, depth: number): void {
    if (node.lazy && !node.children?.length) {
      clear(kids, h("li", { class: "db-loading", role: "none" }, loadingBlock(`Loading ${node.label}…`, { inline: true })));
      const lazy = node.lazy;
      node.lazy = undefined;
      void lazy().then(
        (found) => {
          node.children = found;
          clear(kids, ...found.map((n) => rowOf(n, depth)), found.length ? null : h("li", { class: "db-loading", role: "none" }, "No columns"));
        },
        (e: unknown) => {
          node.lazy = lazy;
          clear(kids, h("li", { class: "db-loading", role: "none" }, errorMark(errorText(e))));
        },
      );
      return;
    }
    clear(kids, ...(node.children ?? []).map((n) => rowOf(n, depth)));
  }

  function toggle(node: Node, item: HTMLElement, to?: boolean): void {
    if (node.children === null) return;
    const now = item.getAttribute("aria-expanded") === "true";
    const next = to ?? !now;
    if (next === now) return;
    opened.delete(next ? `!${node.key}` : node.key);
    opened.add(next ? node.key : `!${node.key}`);
    item.setAttribute("aria-expanded", String(next));
    const caret = item.querySelector(":scope > .db-line > .db-caret");
    caret?.replaceChildren(icon(next ? "down" : "expand"));
    const kids = item.querySelector<HTMLElement>(":scope > .db-kids")!;
    kids.hidden = !next;
    if (next && !kids.childElementCount) fill(node, kids, Number(getComputedStyle(item.querySelector(".db-line")!).getPropertyValue("--depth") || 0) + 1);
  }

  function draw(): void {
    clear(tree, ...roots.map((n) => rowOf(n, 0)));
    empty.hidden = roots.length > 0;
    empty.textContent = searching ? "Nothing matches" : "No data yet";
    const first = tree.querySelector<HTMLElement>(selectedKey ? `[data-key="${CSS.escape(selectedKey)}"]` : "[role=treeitem]");
    if (first) first.tabIndex = 0;
  }

  // ----- the detail side
  function select(node: Node): void {
    selectedKey = node.key;
    for (const li of tree.querySelectorAll<HTMLElement>("[role=treeitem]")) {
      const here = li.dataset.key === node.key;
      li.classList.toggle("selected", here);
      li.setAttribute("aria-selected", String(here));
      li.tabIndex = here ? 0 : -1;
    }
    if (node.kind === "table" && node.result) void showDetail(node.result, node);
  }

  async function showDetail(r: BrowseResult, node: Node): Promise<void> {
    detail.hidden = false;
    const under = h("div", { class: "ex-preview" });
    const own = ctx.actions(r, under);
    const head = h("header", { class: "db-detail-head" }, h("h2", {}, icon(node.icon), r.name), h("p", { class: "db-where" }, r.path.join(" › ")));
    const actions = h("div", { class: "db-detail-actions" });
    const drawActions = (list: typeof own): void =>
      clear(actions, ...list.map((a, i) => button(a.label, () => void a.run(), { icon: a.icon, class: i === 0 ? "small primary" : "small line", title: a.title ?? a.label })));
    drawActions(own);
    // A detail opened before the Workbench said what is in front (Insert's target) gets its buttons again then.
    redrawActions = () => drawActions(ctx.actions(r, under));
    const body = h("div", { class: "db-detail-body" }, loadingBlock("Loading…"));
    clear(detail, head, actions, under, body);
    const columnsTable = (rows: { name: string; type?: string | null; nullable?: unknown }[]): HTMLElement =>
      h(
        "table",
        { class: "small db-columns", "aria-label": "Columns" },
        h("thead", {}, h("tr", {}, h("th", {}, "Column"), h("th", {}, "Type"), h("th", {}, "Nulls"))),
        h("tbody", {}, ...rows.map((c) => h("tr", {}, h("td", {}, c.name), h("td", { class: "mono" }, c.type ?? ""), h("td", {}, c.nullable === undefined || c.nullable === null || c.nullable === "" ? "" : ["YES", "Y", "true", true, 1, "1"].includes(c.nullable as string) ? "Yes" : "No")))),
      );
    const codeBlock = (label: string, text: string): HTMLElement =>
      h("div", { class: "db-code" }, h("div", { class: "db-code-head" }, h("span", {}, label), button("Copy", () => copy(text), { icon: "copy", iconOnly: true, class: "ghost small", title: `Copy the ${label}` })), h("pre", { class: "mono" }, text));
    if (r.source !== "catalog") {
      const cols = (r.children ?? []).filter((c) => c.kind === "columns").map((c) => ({ name: c.name, type: c.type ?? null }));
      clear(
        body,
        r.source === "shared"
          ? h("p", { class: "hint db-shared" }, r.here ? "From the shared catalog" : "From the shared catalog: not connected here", Array.isArray(r.used_by) && r.used_by.length ? ` · used by ${(r.used_by as string[]).join(", ")}` : "")
          : null,
        r.sql ? h("section", {}, h("h3", {}, "SQL name"), h("code", { class: "db-sql" }, r.sql)) : null,
        cols.length ? h("section", {}, h("h3", {}, `Columns`, h("span", { class: "count" }, String(cols.length))), columnsTable(cols)) : null,
        r.insert.sql ? codeBlock("SQL cell", r.insert.sql) : null,
        r.insert.python ? codeBlock("Python cell", r.insert.python) : null,
      );
      return;
    }
    try {
      const d = await tableDetail(r);
      if (selectedKey !== node.key) return;
      if (d.relationships && r.connection && r.place)
        actions.append(button("Import its relationships", busyClick("Reading…", () => importRelationships(d.connection, d.place.schema)), { icon: "diagram", class: "small line" }));
      clear(
        body,
        h("section", {}, h("h3", {}, "SQL name"), h("div", { class: "db-sql-row" }, h("code", { class: "db-sql" }, d.sql), button("Copy SQL name", () => copy(d.sql), { icon: "copy", iconOnly: true, class: "ghost small" }))),
        h("section", {}, h("h3", {}, "From"), h("p", { class: "db-where" }, d.where.join(" › "))),
        h("section", {}, h("h3", {}, "Columns", h("span", { class: "count" }, String(d.columns.length))), columnsTable(d.columns)),
        codeBlock("SQL cell", d.code.sql),
        codeBlock("Python cell", d.code.python),
      );
    } catch (e) {
      clear(body, errorNote(e));
    }
  }

  async function importRelationships(connection: string, dataset: string): Promise<void> {
    toast(`Reading ${dataset || connection}'s relationships…`);
    try {
      const got = await api<{ imported: unknown[] }>(`/connections/${encodeURIComponent(connection)}/relationships`, "POST", dataset ? { dataset } : {});
      toast(`${got.imported.length} relationships from ${dataset || connection} are in the model.`);
    } catch (e) {
      errorHere(e);
    }
  }

  // ----- keys: the arrows through the tree, Enter, /
  tree.addEventListener("keydown", (e) => {
    const at = (e.target as HTMLElement).closest<HTMLElement>("[role=treeitem]");
    if (!at || (e.target as HTMLElement).closest("button")) return;
    const node = (at as HTMLElement & { node?: Node }).node;
    const list = visible();
    const i = list.indexOf(at);
    const go = (to: HTMLElement | undefined): void => {
      if (!to) return;
      e.preventDefault();
      const n = (to as HTMLElement & { node?: Node }).node;
      if (n) select(n);
      to.focus();
      to.scrollIntoView({ block: "nearest" });
    };
    if (e.key === "ArrowDown") go(list[i + 1]);
    else if (e.key === "ArrowUp") go(list[i - 1]);
    else if (e.key === "Home") go(list[0]);
    else if (e.key === "End") go(list[list.length - 1]);
    else if (e.key === "ArrowRight" && node) {
      e.preventDefault();
      if (at.getAttribute("aria-expanded") === "false") toggle(node, at, true);
      else if (at.getAttribute("aria-expanded") === "true") go(at.querySelector<HTMLElement>(":scope > .db-kids > [role=treeitem]") ?? undefined);
    } else if (e.key === "ArrowLeft" && node) {
      e.preventDefault();
      if (at.getAttribute("aria-expanded") === "true") toggle(node, at, false);
      else go(at.parentElement?.closest<HTMLElement>("[role=treeitem]") ?? undefined);
    } else if (e.key === "Enter" && node) {
      e.preventDefault();
      if (node.kind === "table" || node.kind === "item" || node.kind === "column") {
        const under = at.querySelector<HTMLElement>(":scope > .ex-preview") ?? h("div");
        if (node.result) void ctx.actions(node.result, under)[0]?.run();
      } else toggle(node, at);
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "/" || !element.isConnected || e.ctrlKey || e.metaKey || e.altKey) return;
    const at = e.target as HTMLElement | null;
    if (at?.closest("input, textarea, select, [contenteditable=true], .monaco-editor")) return;
    e.preventDefault();
    ctx.search.focus();
    ctx.search.select();
  });

  // ----- the two views
  function showBrowse(answer: BrowseAnswer): void {
    searching = false;
    roots = [
      ...answer.connections.map((c) => connectionNode(c, groupsOf(c, c.groups, (g) => g.tables.map((t) => tableNode(t)), false), answer.connections.length === 1)),
      ...answer.sections.map((s) => sectionNode(s.kind, s.label, (s.kind === "sandbox" ? sandboxOrder(s.items) : s.items).map((r) => tableNode(r)))),
    ];
    resort = () => showBrowse(answer);
    draw();
  }

  function showSearch(answer: SearchAnswer, browsed: BrowseAnswer | null): void {
    searching = true;
    resort = () => showSearch(answer, browsed);
    const known = new Map((browsed?.connections ?? []).map((c) => [c.name.toLowerCase(), c]));
    const of = (kind: string): BrowseResult[] => answer.groups.find((g) => g.kind === kind)?.results ?? [];
    // A connection's tables and columns, under it by schema; a matched column under its table.
    const byConnection = new Map<string, Map<string, { db: string; schema: string; tables: Map<string, { r: BrowseResult; cols: BrowseResult[] }> }>>();
    const at = (r: BrowseResult): { r: BrowseResult; cols: BrowseResult[] } | null => {
      if (r.source !== "catalog" || !r.connection || !r.place) return null;
      const groups = byConnection.get(r.connection) ?? new Map();
      byConnection.set(r.connection, groups);
      const gk = `${r.place.database}\u0000${r.place.schema}`;
      const g = groups.get(gk) ?? { db: r.place.database, schema: r.place.schema, tables: new Map() };
      groups.set(gk, g);
      const t = g.tables.get(r.place.table);
      if (t) return t;
      const sql = r.sql ?? r.place.table;
      const table: BrowseResult = r.kind === "tables" ? r : { key: `tables/${r.connection}/${[...r.path.slice(0, -1)].join("/")}/${r.place.table}`, kind: "tables", name: r.place.table, path: r.path.slice(0, -1), connection: r.connection, detail: "", icon: "rows", insert: { sql: `SELECT * FROM ${sql}`, python: `sab.sql(${JSON.stringify(`SELECT * FROM ${sql}`)})` }, sql, source: "catalog", place: r.place };
      const made = { r: table, cols: [] as BrowseResult[] };
      g.tables.set(r.place.table, made);
      return made;
    };
    const others: Record<string, BrowseResult[]> = {};
    const home = (r: BrowseResult, other = "open"): string => (r.source === "shared" ? "shared" : r.source === "sandbox" ? "sandbox" : other);
    for (const r of of("tables")) if (!at(r)) (others[home(r)] ??= []).push(r);
    for (const r of of("columns")) {
      const t = at(r);
      if (t) t.cols.push(r);
      else (others[r.source === "api" ? "apis" : home(r)] ??= []).push(r);
    }
    const names = new Set([...byConnection.keys(), ...of("connections").map((r) => r.name)]);
    const connectionRoots: Node[] = [];
    for (const name of names) {
      const c: BrowseConnection = known.get(name.toLowerCase()) ?? { name, type: "", tables_kind: "", group: "schema", state: { state: "loaded" }, loaded: true, count: 0, relationships: false, needs_password: false, groups: [] };
      const groups = byConnection.get(name);
      if (!groups) {
        // Matched by its name: all of its tables, as the browse has them (closed).
        connectionRoots.push(connectionNode(c, groupsOf(c, c.groups, (g) => g.tables.map((t) => tableNode(t)), false), false));
        continue;
      }
      const shown: BrowseGroup[] = [...groups.values()].map((g) => ({ database: g.db, schema: g.schema, count: g.tables.size, tables: [...g.tables.values()].map((t) => t.r) }));
      const tablesOf = (g: BrowseGroup): Node[] => g.tables.map((t) => tableNode(t, groups.get(`${g.database}\u0000${g.schema}`)!.tables.get(t.name)!.cols));
      connectionRoots.push(connectionNode(c, groupsOf(c, shown, tablesOf, true), true));
    }
    const sections: [string, string, BrowseResult[]][] = [
      ["open", "Open tables", others.open ?? []],
      ["sandbox", "Sandbox", sandboxOrder(others.sandbox ?? [])],
      ["structures", "Structures", of("structures")],
      ["apis", "APIs", [...of("apis"), ...(others.apis ?? [])]],
      ["variables", "Variables", of("variables")],
      ["blades", "Blades", of("blades")],
      ["shared", "From the shared catalog", others.shared ?? []],
    ];
    roots = [
      ...connectionRoots,
      ...sections.filter(([, , items]) => items.length).map(([kind, label, items]) =>
        sectionNode(kind, label, items.map((r) => (r.kind === "columns" ? { ...columnNode(r.key, r.name, r.type, r), key: r.key, note: r.path.join(" › ") } : { ...tableNode(r), note: r.kind === "structures" && r.path.length ? r.path.join(" › ") : r.detail })))),
    ];
    draw();
  }

  return {
    element,
    showBrowse,
    showSearch,
    actionsChanged: () => {
      if (!detail.hidden) redrawActions?.();
    },
    focus: () => {
      const li = tree.querySelector<HTMLElement>("[role=treeitem].selected") ?? visible()[0];
      if (!li) return;
      const node = (li as HTMLElement & { node?: Node }).node;
      if (node) select(node);
      li.focus();
    },
    select: (key) => {
      const li = tree.querySelector<HTMLElement>(`[data-key="${CSS.escape(key)}"]`);
      const node = li ? (li as HTMLElement & { node?: Node }).node : undefined;
      if (node) select(node);
    },
  };
}
