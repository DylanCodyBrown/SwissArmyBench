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
import { api, onNotice } from "./api";
import { openAreaPage, type PageElement } from "./areaPage";
import { append, button, h, icon, openDialog, plural, recall, remember, toast } from "./dom";
import { errorHere, errorNote, showError } from "./errorNote";
import { busyButton, loadingBlock } from "./loading";
import { promptInstall, type Missing } from "./missingPackages";
import { dismissDialog, go, layerOpened, registerLayer, setOverTitle, visit, watchLayerDialog, withParams } from "./nav";
import { openMenu, type MenuEntry } from "./workbenchMenu";

export type Kind = "table" | "variable" | "structure" | "setting" | "library";
const KINDS: readonly Kind[] = ["table", "variable", "structure", "setting", "library"];
const TAB_WORDS: Record<Kind, string> = { table: "Tables", variable: "Variables", structure: "Structures", setting: "Settings and secrets", library: "Libraries" };
const USED_WORDS: Record<string, string> = { grid: "Grid", cell: "Code", widget: "Canvas", endpoint: "API", analysis: "Analyze", table: "Table", erd: "ERD", connection: "Connection", settings: "Run settings" };

export interface Used {
  kind: string;
  words: string;
  link: { to?: string; grid?: string; path?: string; cell?: number; line?: number; name?: string; canvas?: string; page?: string };
}
export interface Item {
  id: string;
  kind: Kind;
  name: string;
  type: string;
  size: string;
  value: string;
  from: string;
  sub: string | null;
  tags: string[];
  grids: { id: string; name: string; steps: number }[];
  used: Used[];
  kids: [string, string, string][];
  more_kids: number;
  match?: { own: boolean; kids: number[] };
  // A table's
  open?: boolean | string | null;
  in_python?: boolean;
  // A structure's
  path?: string | null;
  saved?: boolean;
  // A setting's
  secret?: boolean;
  set?: boolean;
  editable?: boolean;
  renamable?: boolean;
  showable?: boolean;
  // A library's
  version?: string;
  installed?: boolean;
  pinned?: boolean;
  latest?: string | null;
}
interface Listing {
  items: Item[];
  counts: Record<Kind, number>;
  python: { python: string; version: string; own: boolean };
  project: { name: string; folder: string } | null;
  memory: string;
  checked: boolean;
}

export interface EnvironmentOptions {
  /** The Workbench's pane: fewer columns, the viewer under the list. */
  compact?: boolean;
  /** Insert into code: the host's editor takes it (the Workbench); none: it is copied. */
  insert?: (code: { python?: string; sql?: string; text?: string }) => boolean;
  /** The tab and the row to start on. */
  tab?: Kind;
  name?: string;
  /** Told when the tab or the selected row changes (the page keeps them in its address). */
  moved?: (tab: Kind, name: string | null) => void;
  /** The page's heading actions (Clear… goes there); none: in the find row. */
  actions?: HTMLElement;
}
export interface EnvironmentView {
  element: HTMLElement;
  refresh: () => Promise<void>;
  /** What the list last read (the agent's workbench_window reads it). */
  snapshot: () => Listing | null;
  show: (tab: Kind, name?: string) => void;
  dispose: () => void;
}

interface Column {
  head: string;
  width: string;
  /** Kept in the Workbench's pane. */
  compact?: boolean;
  cell: (item: Item) => Node;
}

// ===== marking a match =====

/** `text` with the search's words marked: the shortest stretch whose letters and digits spell a word (so cust
 *  marks the start of customer_id and of CustomerKey), as the server matched it. */
export function marked(text: string, query: string): DocumentFragment {
  const out = document.createDocumentFragment();
  const words = query.toLowerCase().split(/\s+/).map((w) => w.replace(/[^a-z0-9]/g, "")).filter(Boolean);
  const low = text.toLowerCase();
  const spans: [number, number][] = [];
  for (const word of words) {
    for (let i = 0; i < text.length; i++) {
      if (!/[a-z0-9]/.test(low[i] ?? "")) continue;
      let j = i;
      let k = 0;
      while (j < text.length && k < word.length) {
        const c = low[j] ?? "";
        if (/[a-z0-9]/.test(c)) {
          if (c !== word[k]) break;
          k++;
        }
        j++;
      }
      if (k === word.length) {
        spans.push([i, j]);
        break;
      }
    }
  }
  spans.sort((a, b) => a[0] - b[0]);
  let at = 0;
  for (const [start, end] of spans) {
    if (start < at) continue;
    out.append(text.slice(at, start), h("mark", {}, text.slice(start, end)));
    at = end;
  }
  out.append(text.slice(at));
  return out;
}

// ===== the list, for the page and for the Workbench's pane =====

export function mountEnvironment(options: EnvironmentOptions = {}): EnvironmentView {
  const compact = Boolean(options.compact);
  let tab: Kind = options.tab ?? "table";
  let query = "";
  let listing: Listing | null = null;
  let failed: unknown = null;
  let selected: string | null = options.name ? `${tab}:${options.name}` : null;
  const opened = new Set<string>();
  const columnsOf = new Map<string, [string, string, string][]>(); // a table's columns with their ranges, once asked
  const revealed = new Map<string, string>(); // a secret shown on the user's click, until hidden or the page goes
  let checking = false;
  let disposed = false;
  let asked = 0;

  const search = h("input", { type: "search", class: "env-search", placeholder: compact ? "Search every tab" : "Search every tab: names, columns, keys, variables, where used…", "aria-label": "Search the environment", autocomplete: "off", spellcheck: false, "data-no-variables": "" }) as HTMLInputElement;
  const hint = h("span", { class: "env-hint", role: "status" });
  const tools = h("span", { class: "env-tools" });
  const tabs = h("div", { class: "env-tabs", role: "tablist", "aria-label": "Kinds" });
  const session = h("div", { class: "env-session" });
  const list = h("div", { class: "env-list", role: "tree", "aria-label": "Everything the project holds", tabindex: -1 });
  const viewer = h("aside", { class: "env-side", "aria-label": "Viewer" });
  const main = h("div", { class: "env-main" }, h("section", { class: "env-page", "aria-label": "Environment list" }, session, tabs, h("div", { class: "env-find" }, search, hint, tools), list), viewer);
  const element = h("div", { class: `env${compact ? " env-compact" : ""}` }, main);
  const foldKey = compact ? "env.viewer.pane" : "env.viewer.page";
  let folded = recall(foldKey) === "1";

  const hiddenKey = (kind: Kind): string => `env.hidden.${kind}`;
  const hidden = (kind: Kind): Set<string> => new Set((recall(hiddenKey(kind)) ?? "").split("|").filter(Boolean));

  // ----- the columns of each tab -----

  const text = (cls: string, words: string): HTMLElement => h("span", { class: cls }, marked(words, query));
  const usedCell = (item: Item, none: string): HTMLElement =>
    item.used.length
      ? h("span", { class: "env-from" }, h("button", { type: "button", class: "env-link", "data-used": item.id, onclick: (e: MouseEvent) => (e.stopPropagation(), select(item.id, true)) }, plural(item.used.length, "place")))
      : h("span", { class: "env-from env-none" }, none);
  const COLUMNS: Record<Kind, Column[]> = {
    table: [
      { head: "Rows by columns", width: "130px", compact: true, cell: (it) => h("span", { class: "env-size" }, it.size) },
      { head: "Columns", width: "minmax(160px,2fr)", cell: (it) => text("env-val", it.value) },
      { head: "Grids", width: "110px", cell: (it) => h("span", { class: "env-from" }, it.grids.length ? h("span", { class: "env-tag env-tag-grid", title: "A grid is a view of this table, never a copy" }, `In ${plural(it.grids.length, "grid")}`) : h("span", { class: "env-none" }, "no grid")) },
      { head: "Used in", width: "110px", compact: true, cell: (it) => usedCell(it, "not used yet") },
      { head: "From", width: "minmax(130px,1fr)", cell: (it) => text("env-from", it.from) },
    ],
    variable: [
      { head: "Type", width: "110px", compact: true, cell: (it) => text("env-type", it.type) },
      { head: "Value", width: "minmax(200px,2.4fr)", compact: true, cell: (it) => text("env-val", it.value) },
      { head: "Used in", width: "110px", cell: (it) => usedCell(it, "not used yet") },
      { head: "From", width: "minmax(130px,1fr)", cell: (it) => text("env-from", it.from) },
    ],
    structure: [
      { head: "Format", width: "110px", compact: true, cell: (it) => text("env-type", it.type) },
      { head: "Size", width: "130px", compact: true, cell: (it) => h("span", { class: "env-size" }, it.size) },
      { head: "Paths", width: "minmax(180px,2fr)", cell: (it) => text("env-val", it.value) },
      { head: "Used in", width: "110px", cell: (it) => usedCell(it, "not used yet") },
      { head: "File", width: "minmax(150px,1fr)", cell: (it) => text("env-from", it.from) },
    ],
    setting: [
      { head: "Kind", width: "80px", compact: true, cell: (it) => h("span", { class: "env-type" }, it.type) },
      { head: "Value", width: "minmax(160px,1.4fr)", compact: true, cell: (it) => (revealed.has(it.id) ? h("span", { class: "env-val env-shown" }, revealed.get(it.id) ?? "") : text("env-val", it.value)) },
      { head: "Comes from", width: "minmax(180px,1.6fr)", cell: (it) => text("env-from", it.from) },
      { head: "Used in", width: "110px", cell: (it) => usedCell(it, "not used yet") },
    ],
    library: [
      {
        head: "Pinned",
        width: "86px",
        cell: (it) =>
          it.installed
            ? h("button", { type: "button", class: `env-pin${it.pinned ? " on" : ""}`, "data-pin": it.name, "aria-pressed": String(Boolean(it.pinned)), title: it.pinned ? `Pinned to ${it.version} in requirements.txt: click to let it update` : `Not pinned: click to keep it at ${it.version}`, onclick: (e: MouseEvent) => (e.stopPropagation(), void pin(it, !it.pinned)) }, it.pinned ? icon("pin") : null, it.pinned ? "Pinned" : "Pin")
            : h("span", { class: "env-none" }, ""),
      },
      {
        head: "Version",
        width: "170px",
        compact: true,
        cell: (it) =>
          h(
            "span",
            { class: "env-type" },
            it.version || "not installed",
            it.latest
              ? h("button", { type: "button", class: "env-update", "data-update": it.name, title: `Update to ${it.latest}`, onclick: (e: MouseEvent) => (e.stopPropagation(), update(it)) }, `→ ${it.latest}`)
              : it.installed && listing?.checked
                ? h("span", { class: "env-latest" }, "latest")
                : null,
          ),
      },
      { head: "What it is for", width: "minmax(140px,1.4fr)", cell: (it) => text("env-from", it.value) },
      { head: "Imported in", width: "110px", compact: true, cell: (it) => usedCell(it, "not imported yet") },
    ],
  };
  const shownColumns = (kind: Kind): Column[] => {
    const off = hidden(kind);
    return COLUMNS[kind].filter((c) => (!compact || c.compact) && !off.has(c.head));
  };

  // ----- reading -----

  const load = async (): Promise<void> => {
    const mine = ++asked;
    try {
      const got = await api<Listing>(`/environment${query ? `?search=${encodeURIComponent(query)}` : ""}`);
      if (mine !== asked || disposed) return;
      listing = got;
      failed = null;
    } catch (e) {
      if (mine !== asked || disposed) return;
      failed = e;
    }
    draw();
  };

  /** The Libraries tab asks the index for newer versions when it opens (never in the background). */
  const check = async (): Promise<void> => {
    if (checking || listing?.checked) return;
    checking = true;
    try {
      await api("/environment/libraries?check=1");
      await load();
    } catch {
      // The index cannot be reached: the libraries show without a newer version.
    } finally {
      checking = false;
    }
  };

  const items = (kind: Kind = tab): Item[] => (listing?.items ?? []).filter((i) => i.kind === kind);
  const find = (id: string | null): Item | undefined => (id ? listing?.items.find((i) => i.id === id) : undefined);

  // ----- drawing -----

  const kindMark = (item: Item): HTMLElement => h("span", { class: `env-kind env-k-${item.sub === "secret" || item.sub === "sandbox" ? item.sub : item.kind}`, title: TAB_WORDS[item.kind], "aria-hidden": "true" });

  const kidsOf = (item: Item): [string, string, string][] => columnsOf.get(item.id) ?? item.kids;

  const isOpen = (item: Item): boolean => opened.has(item.id) || Boolean(query && item.match && !item.match.own && item.match.kids.length);

  const drawTabs = (): void => {
    tabs.replaceChildren(
      ...KINDS.map((kind) => {
        const count = listing?.counts[kind] ?? 0;
        return h(
          "button",
          { type: "button", class: "env-tab", role: "tab", "data-kind": kind, "aria-selected": String(kind === tab), tabindex: kind === tab ? 0 : -1, onclick: () => setTab(kind) },
          TAB_WORDS[kind],
          h("i", { class: query && count ? "hot" : "", "data-count": kind }, String(count)),
        );
      }),
    );
  };

  const drawSession = (): void => {
    if (!listing || compact) {
      session.replaceChildren();
      return;
    }
    const python = listing.python;
    session.replaceChildren(
      h("span", { class: "env-python", title: python.python }, `Python ${python.version} · ${python.own ? "the project's environment" : listing.project ? "this app's own (the project has no .venv yet)" : "this app's own"}`),
      h("span", {}, `tables in memory ${listing.memory} · nothing is saved unless you tick Keep`),
      h("span", { class: "env-grow" }),
      h("span", {}, "Updates by itself as your code runs · tables are added on the ", h("button", { type: "button", class: "env-link", onclick: () => visit(withParams({ open: "connections", at: null, type: null, name: null })) }, "Connections"), " page"),
    );
  };

  const drawTools = (): void => {
    const made: HTMLElement[] = [];
    if (tab === "library") {
      const outdated = items("library").filter((i) => i.latest && !i.pinned);
      if (outdated.length) made.push(button(`Update all not pinned (${outdated.length})`, () => updateAll(outdated), { class: "env-update-all" }));
      made.push(button("Install a library…", () => installDialog(), { icon: "import", class: "primary env-install", title: "Installs into the project's environment and adds it to requirements.txt" }));
    }
    if (tab === "structure") {
      // New, Open and Paste are the Structures viewer's own (the page a structure's row opens into).
      made.push(button("New, open or paste…", () => void import("./structuresPage").then((m) => m.openStructures()), { icon: "plus", class: "env-structures" }));
    }
    if (tab === "setting") {
      made.push(button("Add a setting…", () => void import("./variableLinks").then((m) => m.addVariable("", () => void load())), { icon: "plus", class: "primary env-add-setting" }));
      // The key vaults (added, listed, read again) and every setting by its source: their own page.
      made.push(button("Key vaults and more…", () => visit(withParams({ open: "variables", at: null, type: null, name: null })), { icon: "key", class: "env-vaults" }));
    }
    if (!options.actions) made.push(button("Clear…", () => void clearDialog(), { class: "ghost env-clear", title: "Clear what is not kept…" }));
    tools.replaceChildren(...made);
  };

  const row = (item: Item, columns: Column[]): HTMLElement[] => {
    const open = isOpen(item);
    const kids = kidsOf(item);
    const unfolds = kids.length > 0;
    const inside = Boolean(query && item.match && !item.match.own);
    const name = h(
      "span",
      { class: "env-name" },
      kindMark(item),
      h("span", {}, marked(item.name, query)),
      ...item.tags.map((t) => h("span", { class: `env-tag${t === "Keep" ? " env-tag-keep" : ""}` }, t)),
      inside ? h("span", { class: "env-why" }, "matched inside") : null,
    );
    const twist = h("span", { class: "env-twist", "data-twist": item.id, "aria-hidden": "true", onclick: (e: MouseEvent) => (e.stopPropagation(), toggle(item)) }, unfolds ? (open ? "▾" : "▸") : "");
    const more = h("button", { type: "button", class: "env-more", "aria-label": `Actions for ${item.name}`, title: "Actions", onclick: (e: MouseEvent) => (e.stopPropagation(), select(item.id), menu(item, e.currentTarget as HTMLElement)) }, icon("more"));
    const main = h(
      "div",
      { class: `env-row${selected === item.id ? " sel" : ""}`, role: "treeitem", tabindex: selected === item.id ? 0 : -1, "aria-selected": String(selected === item.id), "aria-level": "1", "data-id": item.id, "data-name": item.name, onclick: () => select(item.id), ondblclick: () => void openItem(item) },
      twist,
      name,
      ...columns.map((c) => c.cell(item)),
      more,
    );
    if (unfolds) main.setAttribute("aria-expanded", String(open));
    const out = [main];
    if (open) {
      const wanted = query && item.match && !item.match.own ? new Set(item.match.kids) : null;
      kids.forEach((kid, i) => {
        if (wanted && !wanted.has(i)) return;
        out.push(
          h(
            "div",
            { class: "env-row env-child", role: "treeitem", "aria-level": "2", "data-parent": item.id },
            h("span", {}),
            h("span", { class: "env-name" }, h("span", {}, marked(kid[0], query))),
            h("span", { class: "env-type" }, marked(kid[1], query)),
            h("span", { class: "env-val", style: { gridColumn: `span ${Math.max(1, columns.length - 1)}` } }, marked(kid[2], query)),
            h("span", {}),
          ),
        );
      });
      if (item.more_kids) out.push(h("div", { class: "env-row env-child env-more-kids" }, h("span", {}), h("span", { class: "env-none", style: { gridColumn: `span ${columns.length + 1}` } }, `and ${plural(item.more_kids, "more", "more")}`), h("span", {})));
    }
    return out;
  };

  const emptyWords = (): string => {
    if (query) return `Nothing in ${TAB_WORDS[tab]} matches “${query}”.`;
    if (tab === "table") return "No tables yet. Add one on the Connections page, or make one in code.";
    if (tab === "variable") return "No variables yet: they show here as your code makes them.";
    if (tab === "structure") return "No structures yet: open a JSON, YAML, XML or TOML file, or send one from code.";
    if (tab === "setting") return "No settings yet.";
    return "No libraries yet: Install a library… adds one to the project.";
  };

  const draw = (): void => {
    if (disposed) return;
    drawTabs();
    drawSession();
    drawTools();
    if (failed && !listing) {
      list.replaceChildren(errorNote(failed));
      viewer.replaceChildren();
      return;
    }
    if (!listing) {
      list.replaceChildren(loadingBlock("Loading the environment…"));
      return;
    }
    const columns = shownColumns(tab);
    list.style.setProperty("--env-cols", ["18px", compact ? "minmax(120px,1.2fr)" : "minmax(170px,1.3fr)", ...columns.map((c) => (compact ? "minmax(70px,1fr)" : c.width)), "30px"].join(" "));
    const shown = items();
    if (!find(selected) || find(selected)?.kind !== tab) selected = shown[0]?.id ?? null;
    const top = list.scrollTop;
    const focused = list.contains(document.activeElement);
    const head = h(
      "div",
      { class: "env-head", role: "presentation", oncontextmenu: (e: MouseEvent) => (e.preventDefault(), columnsMenu(e.currentTarget as HTMLElement)) },
      h("span", {}),
      h("span", {}, "Name"),
      ...columns.map((c) => h("span", {}, c.head)),
      compact ? h("span", {}) : h("button", { type: "button", class: "env-columns", "aria-label": "Columns", title: "Show or hide columns", onclick: (e: MouseEvent) => columnsMenu(e.currentTarget as HTMLElement) }, icon("more")),
    );
    const rows = shown.flatMap((item) => row(item, columns));
    list.replaceChildren(head, ...(rows.length ? rows : [h("div", { class: "env-empty" }, emptyWords())]));
    list.scrollTop = top;
    if (focused) list.querySelector<HTMLElement>(".env-row.sel")?.focus({ preventScroll: true });
    const others = KINDS.filter((k) => k !== tab && (listing?.counts[k] ?? 0) > 0);
    hint.replaceChildren(
      ...(query && others.length
        ? ["Also matches in ", ...others.flatMap((k, i) => [i ? ", " : "", h("button", { type: "button", class: "env-link", "data-go": k, onclick: () => setTab(k) }, `${TAB_WORDS[k]} (${listing?.counts[k] ?? 0})`)])]
        : []),
    );
    drawViewer();
    element.classList.toggle("env-folded", folded);
  };

  // ----- the viewer -----

  /** The page makes way for one of the home page's own views (a grid, Analyze, the ERD): its layer leaves
   *  the address, pushed, so Back brings the Environment again. */
  const leave = (): void => {
    if (!compact && new URLSearchParams(location.search).get("open") === "environment") visit(withParams({ open: null, at: null, type: null, name: null }));
  };

  const follow = (used: Used): void => {
    const link = used.link;
    if (link.to === "table" && link.name) {
      select(`table:${link.name}`, true);
      return;
    }
    void import("./sessionPage").then(({ goToTarget }) => {
      if (link.to === "grid" && link.grid) (leave(), goToTarget({ place: "grid", grid: link.grid }));
      else if (link.to === "document" && link.path) goToTarget({ place: "cell", path: link.path, cell: link.cell ?? null });
      else if (link.to === "connection" && link.name) goToTarget({ place: "connection", name: link.name });
      else if (link.to === "analyze" || link.to === "erd") (leave(), goToTarget({ place: "area", area: link.to }));
      else if (link.to === "canvas") goToTarget({ place: "area", area: "canvas" });
    });
  };

  const actionsOf = (item: Item): { label: string; run: () => void; primary?: boolean; icon?: string }[] => {
    const insert = { label: item.kind === "library" ? "Insert import" : item.kind === "setting" ? `Insert \${${item.name}}` : "Insert into code", run: () => void insertCode(item) };
    const copy = { label: "Copy name", run: () => void copyText(item.name, "Copied its name.") };
    const rename = { label: "Rename…", run: () => renameDialog(item) };
    const remove = { label: "Remove…", run: () => removeDialog(item), icon: "trash" };
    const agent = { label: "Send to the agent", run: () => sendToAgent(item), icon: "agent" };
    if (item.kind === "table") {
      const kept = item.tags.includes("Keep");
      return [
        { label: "Open in Grids", run: () => void openItem(item), primary: true },
        insert,
        copy,
        ...(item.open ? [rename, { label: kept ? "Stop keeping with the project" : "Keep with the project", run: () => void keep(item, !kept) }] : []),
        ...(item.open && item.grids[0] ? [{ label: "Make a sandbox variant…", run: () => void import("./dataSandbox").then((m) => m.makeVariant("grid", item.name, () => void load())) }] : []),
        agent,
        remove,
      ];
    }
    if (item.kind === "structure") return [{ label: "Open in Structures", run: () => void openItem(item), primary: true }, insert, copy, ...(item.open ? [rename] : []), agent, remove];
    if (item.kind === "library") {
      return [
        ...(item.latest ? [{ label: `Update to ${item.latest}`, run: () => update(item), primary: true }] : []),
        ...(item.installed ? [{ label: item.pinned ? "Unpin" : `Pin at ${item.version}`, run: () => void pin(item, !item.pinned) }] : [{ label: "Install", run: () => install(item.name), primary: true }]),
        insert,
        remove,
      ];
    }
    if (item.kind === "setting") {
      return [
        ...(item.editable ? [{ label: "Change…", run: () => void import("./variableLinks").then((m) => m.addVariable(item.name, () => void load())), primary: true }] : []),
        ...(item.showable ? [{ label: revealed.has(item.id) ? "Hide" : "Show", run: () => void reveal(item), icon: "eye" }] : []),
        insert,
        copy,
        ...(item.renamable ? [rename, remove] : []),
      ];
    }
    return [insert, copy, rename, agent, remove];
  };

  const drawViewer = (): void => {
    const item = find(selected);
    const fold = button(folded ? "Show the viewer" : "Hide the viewer", () => setFolded(!folded), { icon: "panel", iconOnly: true, class: "ghost env-fold", title: folded ? "Show the viewer (Ctrl+B)" : "Hide the viewer (Ctrl+B)" });
    if (folded) {
      viewer.replaceChildren(fold);
      return;
    }
    if (!item) {
      viewer.replaceChildren(h("h2", { class: "env-side-title" }, h("span", {}, "Select a row"), fold), h("div", { class: "env-side-part env-keys" }, "Click a row, or use the keys below."), keysHelp());
      return;
    }
    const actions = actionsOf(item);
    const used = item.used.length
      ? h(
          "ul",
          { class: "env-used", "aria-label": "Used in" },
          ...item.used.map((u) => h("li", {}, h("span", { class: "env-tag" }, USED_WORDS[u.kind] ?? u.kind), h("button", { type: "button", class: "env-link", "data-used-kind": u.kind, title: "Go there", onclick: () => follow(u) }, u.words))),
        )
      : h("span", { class: "env-keys" }, item.kind === "library" ? "Not imported yet." : "Not used anywhere yet.");
    const python = item.kind === "table" && item.in_python ? (h("input", { type: "checkbox", class: "env-python-too" }) as HTMLInputElement) : null;
    pythonTick = python;
    viewer.replaceChildren(
      h("h2", { class: "env-side-title" }, h("span", { class: "env-side-name" }, item.name), h("span", { class: "env-tag" }, item.type), fold),
      h(
        "div",
        { class: "env-side-part" },
        h("div", { class: "env-kv" }, h("span", {}, item.kind === "library" ? "Version" : "Size"), h("span", {}, item.size || "—"), h("span", {}, item.kind === "setting" ? "Comes from" : item.kind === "structure" ? "File" : "From"), h("span", {}, item.from || "—")),
        h("b", {}, `${item.kind === "library" ? "Imported in" : "Used in"} ${plural(item.used.length, "place")}`),
        used,
        item.kind === "table" ? h("span", { class: "env-keys" }, item.grids.length ? "Its grids are views of this one table: no copies." : item.open ? "Not shown in a grid yet: Open in Grids makes a view, not a copy." : "It is in Python only: no grid shows it yet.") : null,
        h("div", { class: "env-actions" }, ...actions.map((a) => button(a.label, a.run, { class: a.primary ? "primary small" : "small", icon: a.icon }))),
        python ? h("label", { class: "env-keys env-python-label" }, python, " Also delete it in Python (Remove)") : null,
      ),
      keysHelp(),
    );
  };
  let pythonTick: HTMLInputElement | null = null;

  const keysHelp = (): HTMLElement =>
    h("div", { class: "env-side-part env-keys" }, h("kbd", {}, "↑"), " ", h("kbd", {}, "↓"), " move · ", h("kbd", {}, "→"), " open a level · ", h("kbd", {}, "←"), " close · ", h("kbd", {}, "Enter"), " open it · ", h("kbd", {}, "F2"), " rename · ", h("kbd", {}, "Del"), " remove · ", h("kbd", {}, "/"), " search");

  const menu = (item: Item, anchor: HTMLElement): void => {
    const entries: MenuEntry[] = actionsOf(item).map((a) => ({ label: a.label, run: a.run, icon: a.icon }));
    openMenu(anchor, `Actions for ${item.name}`, entries, { align: "right" });
  };

  const columnsMenu = (anchor: HTMLElement): void => {
    if (compact) return;
    const off = hidden(tab);
    const entries: MenuEntry[] = COLUMNS[tab].map((c) => ({
      label: c.head,
      icon: off.has(c.head) ? undefined : "check",
      run: () => {
        if (off.has(c.head)) off.delete(c.head);
        else off.add(c.head);
        remember(hiddenKey(tab), [...off].join("|"));
        draw();
      },
    }));
    openMenu(anchor, "Columns", [{ label: "Columns", heading: true }, ...entries], { align: "right" });
  };

  // ----- moving -----

  const setFolded = (to: boolean): void => {
    folded = to;
    remember(foldKey, to ? "1" : "0");
    draw();
  };

  const setTab = (kind: Kind, name?: string): void => {
    tab = kind;
    selected = name ? `${kind}:${name}` : (items(kind)[0]?.id ?? null);
    options.moved?.(tab, name ?? null);
    draw();
    if (kind === "library") void check();
  };

  const select = (id: string, reveal = false): void => {
    const item = find(id);
    if (item && item.kind !== tab) tab = item.kind;
    selected = id;
    if (reveal && folded) folded = false;
    options.moved?.(tab, item?.name ?? null);
    draw();
    const made = list.querySelector<HTMLElement>(`.env-row[data-id="${CSS.escape(id)}"]`);
    made?.scrollIntoView({ block: "nearest" });
  };

  const toggle = (item: Item, to?: boolean): void => {
    const open = to ?? !opened.has(item.id);
    if (open) opened.add(item.id);
    else opened.delete(item.id);
    selected = item.id;
    draw();
    // A table's columns with their ranges and blanks: asked once, when the row first opens.
    if (open && item.kind === "table" && item.open && !columnsOf.has(item.id)) {
      void api<{ columns: [string, string, string][] }>(`/environment/columns?name=${encodeURIComponent(item.name)}`).then(
        (got) => {
          columnsOf.set(item.id, got.columns);
          draw();
        },
        () => undefined,
      );
    }
  };

  // ----- what a row does -----

  const copyText = async (words: string, said: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(words);
      toast(said);
    } catch {
      errorHere("The clipboard is not available here.");
    }
  };

  const insertCode = async (item: Item): Promise<void> => {
    try {
      const code = await api<{ python?: string; sql?: string; text?: string }>("/environment/insert", "POST", { kind: item.kind, name: item.name });
      if (options.insert?.(code)) return;
      const words = code.text ?? code.python ?? code.sql ?? item.name;
      await copyText(words, `Copied: ${words}`);
    } catch (e) {
      errorHere(e);
    }
  };

  const openItem = async (item: Item): Promise<void> => {
    try {
      if (item.kind === "structure") {
        let id = typeof item.open === "string" ? item.open : null;
        if (!id && item.path) id = (await api<{ id: string }>("/structures/open", "POST", { path: item.path })).id;
        const page = await import("./structuresPage");
        page.openStructures(id);
        return;
      }
      if (item.kind !== "table") {
        select(item.id, true);
        return;
      }
      const got = await api<{ link: { to: string; grid?: string } }>("/environment/open", "POST", { kind: item.kind, name: item.name });
      if (got.link.to === "python") {
        toast(`Opening ${item.name} from Python…`); // its session sends it: the grid arrives by itself
        return;
      }
      const { goToTarget } = await import("./sessionPage");
      if (got.link.grid) {
        leave();
        goToTarget({ place: "grid", grid: got.link.grid });
      }
    } catch (e) {
      errorHere(e);
    }
  };

  const sendToAgent = (item: Item): void => {
    const lines = [`${TAB_WORDS[item.kind]}: ${item.name} (${item.type}${item.size ? `, ${item.size}` : ""})`, item.from ? `From: ${item.from}` : "", ...item.used.map((u) => `Used in: ${u.words}`), ...kidsOf(item).map((k) => `  ${k[0]}: ${k[1]}`)];
    void import("./workbenchAgent").then((m) => m.sendToAgent({ kind: "code", title: `Environment · ${item.name}`, text: lines.filter(Boolean).join("\n") }));
  };

  const keep = async (item: Item, to: boolean): Promise<void> => {
    try {
      await api("/environment/keep", "POST", { name: item.name, keep: to });
      toast(to ? `${item.name} is kept with the project.` : `${item.name} is no longer kept with the project.`);
      await load();
    } catch (e) {
      errorHere(e);
    }
  };

  const reveal = async (item: Item): Promise<void> => {
    if (revealed.has(item.id)) {
      revealed.delete(item.id);
      draw();
      return;
    }
    try {
      revealed.set(item.id, (await api<{ value: string }>("/variables/reveal", "POST", { name: item.name })).value);
      draw();
    } catch (e) {
      errorHere(e);
    }
  };

  const renameDialog = (item: Item): void => {
    const { dialog, body, foot, close } = openDialog(`Rename ${item.name}`);
    dialog.classList.add("env-dialog");
    const to = h("input", { type: "text", class: "mono", "aria-label": "New name", value: item.name, spellcheck: false, "data-no-variables": "" }) as HTMLInputElement;
    const said = h("div", {});
    const run = async (): Promise<void> => {
      try {
        await api("/environment/rename", "POST", { kind: item.kind, name: item.name, to: to.value.trim() });
        close();
        selected = `${item.kind}:${to.value.trim()}`;
        await load();
      } catch (e) {
        showError(said, e);
      }
    };
    body.append(h("label", { class: "field" }, h("span", {}, "New name"), to), said);
    const rename = button("Rename", () => void busyButton(rename, run(), "Renaming…"), { class: "primary" });
    to.addEventListener("keydown", (e) => {
      if (e.key === "Enter") rename.click();
    });
    foot.append(button("Cancel", close, { class: "ghost" }), rename);
    to.select();
  };

  const removeDialog = (item: Item): void => {
    const { dialog, body, foot, close } = openDialog(`Remove ${item.name}`);
    dialog.classList.add("env-dialog");
    const python = item.kind === "table" && item.in_python ? (h("input", { type: "checkbox", class: "env-python-too" }) as HTMLInputElement) : null;
    if (python) python.checked = Boolean(pythonTick?.checked) || !item.open;
    const words =
      item.kind === "table"
        ? item.open
          ? `The table closes with ${item.grids.length ? plural(item.grids.length, "grid") : "no grid"}; its source is not touched.`
          : "It is a table in Python only."
        : item.kind === "variable"
          ? "The variable is deleted in Python."
          : item.kind === "structure"
            ? item.saved
              ? `Its file ${item.from} is deleted from the project.`
              : "The open structure closes; it was never saved."
            : item.kind === "setting"
              ? "The setting goes from this computer; what uses it will ask for it."
              : "The library is taken out of the project's environment and of requirements.txt.";
    const said = h("div", {});
    append(body, h("p", {}, words), item.used.length ? h("p", { class: "env-keys" }, `Used in ${plural(item.used.length, "place")}: ${item.used.slice(0, 4).map((u) => u.words).join("; ")}${item.used.length > 4 ? "…" : ""}`) : null, python ? h("label", { class: "env-python-label" }, python, " Also delete it in Python") : null, said);
    const run = async (): Promise<void> => {
      try {
        await api("/environment/remove", "POST", { kind: item.kind, name: item.name, python: Boolean(python?.checked) });
        close();
        await load();
      } catch (e) {
        showError(said, e);
      }
    };
    const remove = button("Remove", () => void busyButton(remove, run(), "Removing…"), { class: "danger" });
    foot.append(button("Cancel", close, { class: "ghost" }), remove);
    remove.focus();
  };

  const clearDialog = async (): Promise<void> => {
    let would: Record<string, string[]>;
    let choices: Record<string, string>;
    try {
      ({ would, choices } = await api<{ would: Record<string, string[]>; choices: Record<string, string> }>("/environment/clear", "POST", { dry_run: true }));
    } catch (e) {
      errorHere(e);
      return;
    }
    const { dialog, body, foot, close } = openDialog("Clear the environment");
    dialog.classList.add("env-dialog");
    const ticks = Object.entries(choices).map(([key, label]) => {
      const names = would[key] ?? [];
      const box = h("input", { type: "checkbox", "data-clear": key }) as HTMLInputElement;
      box.disabled = names.length === 0;
      return { key, box, row: h("label", { class: "env-clear-row" }, box, h("span", {}, `${label} (${names.length})`), names.length ? h("span", { class: "env-keys" }, names.slice(0, 6).join(", ") + (names.length > 6 ? "…" : "")) : null) };
    });
    const said = h("div", {});
    body.append(h("p", {}, "Kept tables, settings and libraries stay."), ...ticks.map((t) => t.row), said);
    const run = async (): Promise<void> => {
      try {
        await api("/environment/clear", "POST", Object.fromEntries(ticks.map((t) => [t.key, t.box.checked])));
        close();
        await load();
      } catch (e) {
        showError(said, e);
      }
    };
    const clear = button("Clear", () => void busyButton(clear, run(), "Clearing…"), { class: "danger" });
    foot.append(button("Cancel", close, { class: "ghost" }), clear);
  };

  // ----- libraries: through the one install prompt (missingPackages.ts) -----

  const missing = (names: string[], feature: string): Missing => ({ feature, packages: names, python: listing?.python.python ?? "app", command: `uv pip install --python ${listing?.python.python ?? "python"} ${names.join(" ")}` });

  const install = (name: string): void => {
    void promptInstall(missing([name], "The project"), { force: true, install: async () => void (await api("/environment/libraries/install", "POST", { name })), then: () => load() });
  };

  const installDialog = (): void => {
    const { dialog, body, foot, close } = openDialog("Install a library");
    dialog.classList.add("env-dialog");
    const name = h("input", { type: "text", class: "mono", "aria-label": "Library", placeholder: "polars", spellcheck: false, "data-no-variables": "" }) as HTMLInputElement;
    body.append(h("label", { class: "field" }, h("span", {}, "Library"), name), h("p", { class: "env-keys" }, "Into the project's environment, and into requirements.txt so a teammate gets it."));
    const next = button("Install…", () => {
      const wanted = name.value.trim();
      if (!wanted) return;
      close();
      install(wanted);
    }, { class: "primary" });
    name.addEventListener("keydown", (e) => {
      if (e.key === "Enter") next.click();
    });
    foot.append(button("Cancel", close, { class: "ghost" }), next);
    name.focus();
  };

  const update = (item: Item): void => {
    void promptInstall(missing([`${item.name}==${item.latest ?? ""}`], `Update ${item.name}`), { force: true, install: async () => void (await api("/environment/libraries/update", "POST", { name: item.name })), then: () => load() });
  };

  const updateAll = (outdated: Item[]): void => {
    void promptInstall(missing(outdated.map((i) => `${i.name}==${i.latest ?? ""}`), "Update all not pinned"), { force: true, install: async () => void (await api("/environment/libraries/update", "POST", { all: true })), then: () => load() });
  };

  const pin = async (item: Item, to: boolean): Promise<void> => {
    try {
      await api("/environment/libraries/pin", "POST", { name: item.name, pinned: to });
      await load();
    } catch (e) {
      errorHere(e);
    }
  };

  // ----- the keys -----

  const onKey = (e: KeyboardEvent): void => {
    const target = e.target as HTMLElement;
    const typing = target.matches("input, textarea, select, [contenteditable='true']");
    if (target.closest("dialog") || (!element.contains(target) && target !== document.body)) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b" && !compact) {
      e.preventDefault();
      setFolded(!folded);
      return;
    }
    if (e.key === "/" && !typing) {
      e.preventDefault();
      search.focus();
      return;
    }
    if (typing && !(target === search && e.key === "ArrowDown")) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const shown = items();
    const at = shown.findIndex((i) => i.id === selected);
    const item = shown[at];
    if (e.key === "ArrowDown") selected = (shown[Math.min(shown.length - 1, at + 1)] ?? shown[0])?.id ?? null;
    else if (e.key === "ArrowUp") selected = shown[Math.max(0, at - 1)]?.id ?? null;
    else if (e.key === "ArrowRight" && item) return void (e.preventDefault(), toggle(item, true), focusRow());
    else if (e.key === "ArrowLeft" && item) return void (e.preventDefault(), toggle(item, false), focusRow());
    else if (e.key === "Enter" && item && target.closest(".env-row")) return void (e.preventDefault(), openItem(item));
    else if (e.key === "F2" && item) return void (e.preventDefault(), renameDialog(item));
    else if (e.key === "Delete" && item) return void (e.preventDefault(), removeDialog(item));
    else return;
    e.preventDefault();
    options.moved?.(tab, find(selected)?.name ?? null);
    draw();
    focusRow();
  };
  const focusRow = (): void => {
    const made = list.querySelector<HTMLElement>(".env-row.sel");
    made?.focus();
    made?.scrollIntoView({ block: "nearest" });
  };
  document.addEventListener("keydown", onKey);

  let typed = 0;
  search.addEventListener("input", () => {
    window.clearTimeout(typed);
    typed = window.setTimeout(() => {
      query = search.value.trim();
      void load();
    }, 120);
  });

  const unheard = onNotice((n) => {
    if (n.type === "environment_changed") void load();
  });

  if (options.actions) options.actions.append(button("Clear…", () => void clearDialog(), { class: "ghost env-clear", title: "Clear what is not kept…" }));
  draw();
  void load().then(() => {
    if (tab === "library") void check();
  });

  return {
    element,
    refresh: load,
    snapshot: () => listing,
    show: (kind, name) => setTab(kind, name),
    dispose: () => {
      disposed = true;
      unheard();
      document.removeEventListener("keydown", onKey);
      element.remove();
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

registerLayer("environment", {
  isOpen: () => Boolean(shownPage?.open),
  open: (url) => drawPage(url?.searchParams.get("at"), url?.searchParams.get("name")),
  show: (url) => {
    const at = url.searchParams.get("at");
    if (isKind(at)) view?.show(at, url.searchParams.get("name") ?? undefined);
  },
  dismiss: () => {
    if (shownPage) dismissDialog(shownPage);
  },
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
    tab: isKind(at) ? at : undefined,
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
