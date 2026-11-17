/**
 * panes.ts: every open grid in one page: the tab bar, a pane per grid, and the split. [STATE + WIRE]
 *
 * Each open grid has a context: its PageState and, once its tab is first opened, a pane with its
 * own grid view (kept while hidden, so switching back is instant). One grid is active at a time,
 * and the panels (Table Transformations, the analysis panel, the ribbon, the status bar, the SQL
 * box) always show the active one: activateGrid() points the API at it (useGrid), hands the
 * panels its view (setActiveView) and its state (activate), and they redraw.
 *
 * The split shows two panes side by side. Make one by dropping a tab on another tab, or by
 * dragging a tab down onto the grid (its left or right half says which side it goes). Click into
 * a pane to make it active; "Close this side" leaves the other grid alone.
 *
 * Visualizations tab comes first, always, and can't be closed: it shows Visualizations full
 * width (with a table picker) in place of the grids. Any grid tab goes back to the grids.
 *
 * The "+" after the last tab opens a draft tab: a new table from a query over the open tables
 * (queryTab.ts draws it). The draft's first Run builds the table, and its grid takes the draft's
 * place as an ordinary tab.
 *
 * ROUTING: [AGENT TAB]      click -> showAgentView()
 *          [TAB]            click -> activateGrid(id) + showGridView(); arrows, Home/End move; Delete closes
 *          [TAB CLOSE ×]    -> closeGrid(id)  (closes the grid on the server; the dataset stays)
 *          [TAB RIGHT-CLICK] -> tabMenu(): Compare with… -> compareWith(id), Rename -> renameInPlace(), Close -> closeGrid(id)
 *          [DRAG TAB]       onto a tab's edge -> moveTab();  onto a tab's middle or the grid -> splitWith()
 *          [DRAFT TAB]      click -> showQueryView(); × -> closeDraft(); label -> renameDraft()
 *          [NEW TAB +]      -> newQueryTab()  (opens the draft, or brings the open one forward)
 *          [OPEN BUTTON]    -> openMenu.showOpenDialog()  (the tables in your running Python sessions)
 *          [PANE]           pointer down -> activateGrid(id)
 *          [CLOSE THIS SIDE]-> unsplit(keep)
 *          [PREVIEW BANNER] per pane -> state.setPreview(null)
 *          [EMPTY STATE]    -> read-only, when no grid is open
 */
import { api, onNotice, token, useGrid } from "./api";
import { button, clear, h, icon, recall, remember, showMenu, toast, type MenuItem } from "./dom";
import { createGridView, setActiveView, type GridView } from "./gridView";
import { openFileButton } from "./openFile";
import { openMenuButton } from "./openMenu";
import { go, LAYER_PARAMS, layerShown, type Move, setTitle } from "./nav";
import { renameInPlace } from "./renameTable";
import { connectionColour, onConnectionColours } from "./connectionColours";
import { PageState, activate } from "./state";

export interface Context {
  id: string;
  dataset: string;
  state: PageState;
  view: GridView | null;
  pane: HTMLElement | null;
}

const contexts = new Map<string, Context>();
// What the page shows: the grids, or an app-level tab (Agent, ERD, the "+" draft) in their place.
type AppView = "grid" | "agent" | "erd" | "query" | "start" | "grids";
let view: AppView = "grid";
const agentViewListeners: (() => void)[] = [];
// The "+" tab's draft: the name of the table its query will build. `serial` tells queryTab.ts a
// new draft from the one it last drew (a closed draft's query is not carried into the next).
let draft: { serial: number; name: string } | null = null;
let draftSerial = 0;

/** Visualizations tab: Visualizations full width, in place of the grids. */
export function showAgentView(how: Move = "auto"): void {
  setView("agent", how);
}

/** The ERD tab: the relationship diagram of the open tables, in place of the grids. */
export function showErdView(how: Move = "auto"): void {
  setView("erd", how);
}

export function showGridView(how: Move = "auto"): void {
  setView("grid", how);
}

/** The Start view (startView.ts): new and recent projects, in place of the grids. Home brings it. */
export function showStartView(how: Move = "auto"): void {
  setView("start", how);
}

/** Grids with no table open (startView.ts): the ways to bring data in. */
export function showGridsLanding(how: Move = "auto"): void {
  setView("grids", how);
}

/** The Start view or the Grids landing: a table that arrives takes their place. */
export function viewingStart(): boolean {
  return view === "start" || view === "grids";
}

export function viewingLanding(): boolean {
  return view === "grids";
}

// With no table open: the Grids landing while a project is open, else the Start view (startView.ts says).
let emptyView: () => "start" | "grids" = () => "start";

export function setEmptyView(choose: () => "start" | "grids"): void {
  emptyView = choose;
}

// ===== the address (nav.ts): the tab in front is in it, so Back and Forward move between tabs and a
// reload keeps the one in front. /g/<id> for a table, /workspace?view=visualizations | erd | query for the
// others (the old sandbox and diagram still land, and the address takes the new word); a dialog's own words (open=connections&at=types) stay after them.

const VIEW_WORDS: Record<Exclude<AppView, "grid">, string> = { agent: "visualizations", erd: "erd", query: "query", start: "start", grids: "grids" };
let activating = 0;
let syncing: Move | null = null;

/** The address of what is in front now. */
function addressOf(): string {
  const now = new URLSearchParams(location.search);
  const out = new URLSearchParams();
  if (view !== "grid") out.set("view", VIEW_WORDS[view]);
  // A dialog's own words, while it is on screen (one closed a moment ago leaves them behind).
  if (now.get("open") && layerShown() === now.get("open")) {
    for (const key of LAYER_PARAMS) {
      const value = now.get(key);
      if (value !== null) out.set(key, value);
    }
  }
  const path = view === "grid" && activeId ? `/g/${encodeURIComponent(activeId)}` : "/workspace";
  const query = out.toString();
  return `${path}${query ? `?${query}` : ""}`;
}

/** The window's title: the place in front (the table's name, Visualizations, ERD, New query). */
export function placeName(): string {
  if (view === "agent") return "Visualizations";
  if (view === "erd") return "ERD";
  if (view === "start") return "Start";
  if (view === "grids") return "Grids";
  if (view === "query") return draft?.name || "New query";
  return activeId && contexts.has(activeId) ? label(activeId) : "";
}

export function drawTitle(): void {
  setTitle("", placeName());
}

/** The address and the title follow what is in front, once per change: a tab click that shows the
 *  grids and then a table makes one entry, the table's (an activation still loading writes its own). */
function syncSoon(how: Move): void {
  const first = syncing === null;
  syncing = how;
  if (!first) return;
  queueMicrotask(() => {
    const next = syncing ?? "auto";
    syncing = null;
    if (activating) return;
    drawTitle();
    void go(addressOf(), next);
  });
}

/** Show what `url` names (Back, Forward, a reload, the agent): the history is not written again. */
export async function showPlace(url: URL): Promise<void> {
  const named = url.searchParams.get("view");
  if (named === "visualizations" || named === "sandbox") setView("agent", "replace");
  else if (named === "erd" || named === "diagram") setView("erd", "replace");
  else if (named === "query") await newQueryTab("replace");
  else if (named === "start") setView("start", "replace");
  else if (named === "grids" || (!order.length && url.pathname === "/workspace")) setView(order.length ? "grid" : emptyView(), "replace");
  else {
    const id = url.pathname.startsWith("/g/") ? decodeURIComponent(url.pathname.slice(3)) : "";
    setView("grid", "replace");
    // A table closed since: the one in front stays, and the address says so.
    if (id && contexts.has(id) && id !== activeId) await activateGrid(id, "replace");
  }
}

export function viewingErd(): boolean {
  return view === "erd";
}

export function viewingQuery(): boolean {
  return view === "query";
}

/** The draft tab: its query tray over a blank grid, in place of the grids. */
export function showQueryView(how: Move = "auto"): void {
  setView("query", how);
}

export function currentDraft(): { serial: number; name: string } | null {
  return draft;
}

/** The "+": open a draft named query_<n> (the first n no dataset uses), or show the open one. */
export async function newQueryTab(how: Move = "auto"): Promise<void> {
  if (!draft) {
    const { datasets } = await api<{ datasets: { name: string }[] }>("/datasets");
    const taken = new Set(datasets.map((d) => d.name));
    let n = 1;
    while (taken.has(`query_${n}`)) n += 1;
    draftSerial += 1;
    draft = { serial: draftSerial, name: `query_${n}` };
  }
  showQueryView(how);
}

/** The draft's tab label follows the name typed in its tray. */
export function renameDraft(name: string): void {
  if (!draft) return;
  draft.name = name;
  render();
  if (view === "query") drawTitle();
}

/** Discard the draft (nothing was built) and go back to the grids, in the draft's place in the history. */
export function closeDraft(): void {
  draft = null;
  if (view === "query") showGridView("replace");
  else render();
}

/** The draft's first Run built `dataset`: its grid takes the draft's place as an ordinary tab. */
export async function finishDraft(id: string, dataset: string): Promise<void> {
  draft = null;
  addGrid(id, dataset); // usually already added by the server's grid_shown notice
  showGridView("replace");
  await activateGrid(id, "replace");
}

/** Called whenever the view changes (grids, Agent or ERD). */
export function onAgentView(listener: () => void): void {
  agentViewListeners.push(listener);
}

function setView(next: AppView, how: Move = "auto"): void {
  const changed = view !== next;
  view = next;
  const workspace = panesHost?.closest<HTMLElement>(".workspace");
  if (workspace) workspace.dataset.view = next;
  // The ribbon and the title act on a grid, so the app-level tabs hide them.
  document.body.classList.toggle("agent-view", next !== "grid");
  render();
  if (changed) for (const listener of agentViewListeners) listener();
  syncSoon(how);
}

/** Every open grid, in tab order, with its tab label (for the Agent tab's table picker). */
export function gridList(): { id: string; label: string }[] {
  return order.map((id) => ({ id, label: label(id) }));
}
let order: string[] = [];
let activeId: string | null = null;
// Counts activateGrid calls, so a slow first load can't take the front from a later click.
let activations = 0;
let split: [string, string] | null = null; // [left, right]
let dragging: string | null = null;
let tabRow: HTMLElement;
let panesHost: HTMLElement;
let onActivate: (state: PageState) => void = () => {};
// compare.ts listens: a new split opens the key picker; any change to the split re-checks the compare.
const splitCreated: ((left: Context, right: Context) => void)[] = [];
const splitChanged: (() => void)[] = [];
// queryTab.ts listens: a built table's pane gets its query tray, freed when the pane goes.
const paneCreated: ((ctx: Context) => void)[] = [];
const paneDropped: ((ctx: Context) => void)[] = [];

export function onPaneCreated(listener: (ctx: Context) => void): void {
  paneCreated.push(listener);
}

export function onPaneDropped(listener: (ctx: Context) => void): void {
  paneDropped.push(listener);
}

export function onSplitCreated(listener: (left: Context, right: Context) => void): void {
  splitCreated.push(listener);
}

export function onSplitChange(listener: () => void): void {
  splitChanged.push(listener);
}

/** The two grids side by side, left then right, or null when not split. */
export function splitPair(): [Context, Context] | null {
  const [left, right] = (split ?? []).map((id) => contexts.get(id));
  return left && right ? [left, right] : null;
}

export function mountPanes(tabs: HTMLElement, panes: HTMLElement, activated: (state: PageState) => void): void {
  tabRow = tabs;
  panesHost = panes;
  onActivate = activated;
  // Dragging a tab down onto the grid splits: the drop's half picks the side.
  panes.addEventListener("dragover", (e) => {
    if (!dragging || dragging === activeId || split) return;
    e.preventDefault();
    const right = e.clientX > panes.getBoundingClientRect().left + panes.clientWidth / 2;
    panes.dataset.drop = right ? "right" : "left";
  });
  panes.addEventListener("dragleave", (e) => { if (e.target === panes) delete panes.dataset.drop; });
  panes.addEventListener("drop", (e) => {
    const side = panes.dataset.drop as "left" | "right" | undefined;
    delete panes.dataset.drop;
    if (!dragging || !side || !activeId) return;
    e.preventDefault();
    void splitWith(dragging, activeId, side);
  });
}

export function contextOf(id: string): Context | undefined {
  return contexts.get(id);
}

export function contextsOf(dataset: string): Context[] {
  return [...contexts.values()].filter((c) => c.dataset === dataset);
}

export function activeContext(): Context | undefined {
  return activeId ? contexts.get(activeId) : undefined;
}

/** Load the open grids as tabs (remembered order first) and open `focus`, or the last active. */
export async function openGrids(focus: string | null): Promise<void> {
  const { grids } = await api<{ grids: { grid: string; dataset: string }[] }>("/grids");
  let saved: string[] = [];
  try {
    saved = JSON.parse(recall("workspace.order") ?? "[]") as string[];
  } catch {
    saved = [];
  }
  const open = new Map(grids.map((g) => [g.grid, g.dataset]));
  for (const id of saved) if (open.has(id)) addGrid(id, open.get(id)!);
  for (const g of grids) addGrid(g.grid, g.dataset);
  const remembered = recall("workspace.active");
  const first = (focus && contexts.has(focus) && focus) || (remembered && contexts.has(remembered) && remembered) || order[0];
  if (first) await activateGrid(first);
  else render();
}

/** After the live connection came back: notices sent while it was down never arrived, so match
 * the tabs to the server's grids and reload the ones already drawn. */
export async function resyncGrids(): Promise<void> {
  const { grids } = await api<{ grids: { grid: string; dataset: string }[] }>("/grids");
  const open = new Set(grids.map((g) => g.grid));
  for (const id of [...contexts.keys()]) if (!open.has(id)) dropGrid(id);
  for (const g of grids) addGrid(g.grid, g.dataset);
  for (const ctx of contexts.values()) {
    if (ctx.state.info) void ctx.state.load().then(() => ctx.view?.refresh()).catch(() => undefined);
  }
  if (!activeId && order[0]) await activateGrid(order[0]);
}

/** A table was renamed (anywhere: this page, another window, the agent): its tabs, pane heads and
 * grids follow; each grid reloads its info, which redraws the title and the panels. */
export function renameContexts(from: string, to: string): void {
  for (const ctx of contextsOf(from)) {
    ctx.dataset = to;
    const head = ctx.pane?.querySelector(".pane-head strong");
    if (head) head.textContent = to;
    ctx.pane?.querySelector(".grid-host")?.setAttribute("aria-label", `Data grid: ${to}`);
    if (ctx.state.info) void ctx.state.load().catch(() => undefined);
  }
  refreshSources();
  render();
}

// ===== tab groups by connection (the owner, 2026-11-16: "tab groups from the grid based on connections") =====
// Where each table came from (GET /grids' origin). A table read from a connection is in that connection's
// group (its colour and name as the head); pasted, pushed, file and query tables are in a group of their own
// kind. The heads show only when a connection's table is open: with none, the row is as it always was.
// The order is kept: `order` is normalized so each group's tabs sit together where its first tab was, and
// the keys and drags walk `order`, so they keep working within and across groups.
interface Source {
  kind: string;
  connection: string | null;
}
const sources = new Map<string, Source>();
let sourcesAsked = false;

function groupKey(id: string): string {
  const s = sources.get(contexts.get(id)?.dataset ?? "");
  if (s?.connection) return `c:${s.connection.toLocaleLowerCase()}`;
  const kind = s?.kind ?? "unknown";
  return `k:${kind === "dropped" ? "file" : kind}`;
}

const KIND_WORDS: Record<string, string> = { file: "Files", python: "Python", paste: "Pasted", query: "Queries", unknown: "Other" };

function groupName(key: string, first: string): string {
  if (key.startsWith("c:")) {
    const named = sources.get(contexts.get(first)?.dataset ?? "")?.connection ?? key.slice(2);
    return connectionColour(named)?.name ?? named;
  }
  return KIND_WORDS[key.slice(2)] ?? "Other";
}

function grouped(): boolean {
  return order.some((id) => groupKey(id).startsWith("c:"));
}

/** `order` with each group's tabs together, the groups in the order of their first tab. */
function normalize(): void {
  if (!grouped()) return;
  const keys: string[] = [];
  const members = new Map<string, string[]>();
  for (const id of order) {
    const key = groupKey(id);
    if (!members.has(key)) {
      keys.push(key);
      members.set(key, []);
    }
    members.get(key)!.push(id);
  }
  order = keys.flatMap((k) => members.get(k)!);
}

/** Ask the server where the open tables came from (after tabs open, or a table's connection swaps). */
export function refreshSources(): void {
  if (sourcesAsked) return;
  sourcesAsked = true;
  setTimeout(() => {
    void api<{ grids: { dataset: string; origin?: Source }[] }>("/grids")
      .then(({ grids }) => {
        sources.clear();
        for (const g of grids) if (g.origin) sources.set(g.dataset, g.origin);
        normalize();
        render();
      })
      .catch(() => undefined)
      .finally(() => (sourcesAsked = false));
  }, 30);
}
onConnectionColours(() => render());
onNotice((notice) => {
  if (notice.type === "table_connection" || notice.type === "dataset_updated" || notice.type === "dataset_renamed" || notice.type === "project_changed") refreshSources();
});

const collapsedGroups = new Set<string>(((): string[] => {
  try {
    return JSON.parse(recall("workspace.collapsedGroups") ?? "[]") as string[];
  } catch {
    return [];
  }
})());

function toggleGroup(key: string): void {
  if (collapsedGroups.has(key)) collapsedGroups.delete(key);
  else collapsedGroups.add(key);
  remember("workspace.collapsedGroups", JSON.stringify([...collapsedGroups]));
  render();
}

/** Move a whole group's tabs before `before` (a tab of another group; null: to the end). */
function moveGroup(key: string, before: string | null): void {
  const mine = order.filter((id) => groupKey(id) === key);
  if (before && mine.includes(before)) return;
  order = order.filter((id) => !mine.includes(id));
  const at = before ? order.indexOf(before) : -1;
  order.splice(at < 0 ? order.length : at, 0, ...mine);
  remember("workspace.order", JSON.stringify(order));
  render();
}

let draggingGroup: string | null = null;

/** The tabs as the row shows them: in groups with heads when a connection's table is open. */
function arrange(tabs: Map<string, HTMLElement>): HTMLElement[] {
  if (!grouped()) return order.map((id) => tabs.get(id)!);
  const out: HTMLElement[] = [];
  let i = 0;
  while (i < order.length) {
    const key = groupKey(order[i]!);
    const members: string[] = [];
    while (i < order.length && groupKey(order[i]!) === key) members.push(order[i++]!);
    const name = groupName(key, members[0]!);
    const collapsed = collapsedGroups.has(key);
    const connection = key.startsWith("c:") ? name : null;
    const head = h(
      "button",
      {
        type: "button",
        class: "tab-group-head",
        draggable: "true",
        "aria-expanded": String(!collapsed),
        title: collapsed ? `Show ${name}'s tables` : `Fold ${name}'s tables`,
        onclick: () => toggleGroup(key),
        ondragstart: (e: DragEvent) => { draggingGroup = key; e.dataTransfer?.setData("text/plain", key); },
        ondragend: () => { draggingGroup = null; },
        ondragover: (e: DragEvent) => { if (draggingGroup || dragging) e.preventDefault(); },
        ondrop: (e: DragEvent) => {
          e.preventDefault();
          if (draggingGroup) moveGroup(draggingGroup, members[0]!);
          else if (dragging) moveTab(dragging, members[0]!);
        },
      },
      connection ? h("span", { class: "conn-dot", "data-connections": connection, "aria-hidden": "true" }) : null,
      h("span", { class: "tab-group-name" }, name),
      collapsed ? h("span", { class: "tab-group-count" }, String(members.length)) : null,
    );
    const shown = members.filter((id) => !collapsed || (id === activeId && view === "grid"));
    out.push(
      h(
        "div",
        { class: `tab-group ${collapsed ? "collapsed" : ""}`, role: "group", "aria-label": name, "data-group": key, ...(connection ? { "data-connections": connection } : {}) },
        head,
        ...shown.map((id) => tabs.get(id)!),
      ),
    );
  }
  return out;
}

export function addGrid(id: string, dataset: string): void {
  if (contexts.has(id)) return;
  if (!sources.has(dataset)) refreshSources();
  contexts.set(id, { id, dataset, state: new PageState(id), view: null, pane: null });
  order.push(id);
  render();
}

function label(id: string): string {
  const ctx = contexts.get(id)!;
  // Two grids on one dataset read "orders" and "orders · 2", in tab order.
  const same = order.filter((o) => contexts.get(o)?.dataset === ctx.dataset);
  return same.length > 1 ? `${ctx.dataset} · ${same.indexOf(id) + 1}` : ctx.dataset;
}

/** This grid's pane: its banner slot and its grid view, built the first time it is shown. */
function ensurePane(ctx: Context): HTMLElement {
  if (ctx.pane) return ctx.pane;
  const host = h("div", { class: "grid-host", "aria-label": `Data grid: ${ctx.dataset}` });
  const head = h(
    "header",
    { class: "pane-head" },
    h("strong", {}, ctx.dataset),
    h("span", { class: "spacer" }),
    button("Close this side", () => unsplit(split?.find((g) => g !== ctx.id) ?? ctx.id), { icon: "close", class: "ghost small" }),
  );
  // queryTab.ts draws a built table's query tray here: its base data, above everything else.
  const querySlot = h("div", { class: "query-slot" });
  const slot = h("div", { class: "preview-slot" });
  // compare.ts draws the cross-compare banner ("Showing 2 rows with key 42 · Clear") here.
  const compareSlot = h("div", { class: "compare-slot" });
  ctx.pane = h("section", { class: "pane", "data-grid": ctx.id, hidden: true }, head, querySlot, slot, compareSlot, host);
  ctx.pane.addEventListener("pointerdown", () => { if (activeId !== ctx.id) void activateGrid(ctx.id); }, true);
  panesHost.append(ctx.pane);
  const view = createGridView(host, ctx.state);
  ctx.view = view;
  ctx.state.onOwn("view", () => view.refresh());
  ctx.state.onOwn("preview", () => { previewBanner(ctx, slot); view.refresh(); });
  ctx.state.onOwn("preview-marks", () => {
    const marks = slot.querySelector<HTMLElement>(".preview-marks");
    if (marks && ctx.state.changedCells) marks.textContent = `${marks.textContent?.split(" · ")[0]} · ${ctx.state.changedCells.toLocaleString()} cells changed by this step in the loaded rows are marked ✎.`;
  });
  for (const listener of paneCreated) listener(ctx);
  return ctx.pane;
}

function previewBanner(ctx: Context, slot: HTMLElement): void {
  const upto = ctx.state.previewUpto;
  if (upto === null) {
    clear(slot);
    return;
  }
  const step = upto === 0 ? "the source" : `step ${upto}: ${ctx.state.info?.steps[upto - 1]?.description ?? ""}`;
  clear(
    slot,
    h(
      "div",
      { class: "preview-banner", id: "preview-banner", role: "status" },
      h("strong", {}, "Previewing"),
      h("span", { class: "preview-marks", id: "preview-marks" }, `the data after ${step}.`),
      h("span", { class: "spacer" }),
      button("Back to the full view", () => ctx.state.setPreview(null), { class: "primary" }),
    ),
  );
}

/** Make `id` the active grid: its pane shows (or takes the active side of the split), and every
 * panel redraws for it. */
export async function activateGrid(id: string, how: Move = "auto"): Promise<void> {
  const ctx = contexts.get(id);
  if (!ctx) return;
  const mine = ++activations;
  // Until it is in front, the address waits for it (a tab click's "show the grids" writes no entry).
  activating += 1;
  try {
    await bringForward(ctx, id, mine);
  } finally {
    activating -= 1;
    if (mine === activations) syncSoon(how);
  }
}

async function bringForward(ctx: Context, id: string, mine: number): Promise<void> {
  // Tell the server which table is in front, so an agent's prompt can say so (routes_context.py).
  void api("/workspace/active", "POST", { grid: id }).catch(() => undefined);
  if (!ctx.state.info) {
    try {
      await ctx.state.load();
    } catch (e) {
      if (mine === activations && contexts.get(id) === ctx) toast((e as Error).message, "error");
      return;
    }
    // Another tab was clicked (or this one closed) while this one loaded: the last click wins.
    if (mine !== activations || contexts.get(id) !== ctx) return;
  }
  if (split && !split.includes(id) && activeId) {
    // Opening another tab while split: it replaces the active side.
    split = split.map((g) => (g === activeId ? id : g)) as [string, string];
  }
  ensurePane(ctx);
  activeId = id;
  useGrid(id);
  setActiveView(ctx.view!);
  activate(ctx.state);
  onActivate(ctx.state);
  layout();
  remember("workspace.active", id);
  render();
}

function layout(): void {
  const shown = new Set(split ?? (activeId ? [activeId] : []));
  for (const ctx of contexts.values()) {
    if (!ctx.pane) continue;
    ctx.pane.hidden = !shown.has(ctx.id);
    ctx.pane.classList.toggle("active", ctx.id === activeId);
  }
  // Side by side, the page order is the screen order (screen readers read left to right too).
  const [left, right] = (split ?? []).map((id) => contexts.get(id)?.pane);
  if (left && right && left.compareDocumentPosition(right) & Node.DOCUMENT_POSITION_PRECEDING) {
    panesHost.insertBefore(left, right);
  }
  const was = panesHost.dataset.split === "on" ? panesHost.dataset.pair : "";
  panesHost.dataset.split = split ? "on" : "off";
  panesHost.dataset.pair = split ? split.join("|") : "";
  if (was !== panesHost.dataset.pair) for (const listener of splitChanged) listener();
}

/** Put `dragged` beside `beside`, on `side`. `quiet`: a split put back after a reload, whose compare
 * is already running, so the key picker does not open. */
export async function splitWith(dragged: string, beside: string, side: "left" | "right", quiet = false): Promise<void> {
  if (dragged === beside || !contexts.has(dragged) || !contexts.has(beside)) return;
  const besideCtx = contexts.get(beside)!;
  if (!besideCtx.state.info) await besideCtx.state.load();
  ensurePane(besideCtx);
  split = side === "left" ? [dragged, beside] : [beside, dragged];
  showGridView();
  await activateGrid(dragged);
  const pair = splitPair();
  if (pair && !quiet) for (const listener of splitCreated) listener(pair[0], pair[1]);
}

/** Compare with…: put another open table beside `id` (which stays on the left) and pick the keys,
 * as dragging its tab onto this one does. One other table: that one, at once. Several: a list of
 * them at (x, y), or at the tab. */
export function compareWith(id: string, x?: number, y?: number): void {
  const others = order.filter((o) => o !== id);
  const go = (other: string): void => void splitWith(other, id, "right");
  if (others.length === 1) {
    go(others[0]!);
    return;
  }
  if (!others.length) return;
  const box = tabRow.querySelector<HTMLElement>(`.tab-item[data-grid="${CSS.escape(id)}"]`)?.getBoundingClientRect();
  showMenu(x ?? box?.left ?? 8, y ?? box?.bottom ?? 40, `Compare ${label(id)} with`, others.map((o): MenuItem => ["columns", label(o), () => go(o)]));
}

/** Rename the table in front, in its tab (the palette's Rename; F2 on the tab). */
export function renameActive(): void {
  const ctx = activeContext();
  const name = ctx ? tabRow.querySelector<HTMLElement>(`.tab-item[data-grid="${CSS.escape(ctx.id)}"] .tab-label`) : null;
  if (ctx && name) renameInPlace(name, ctx.dataset);
}

/** A tab's right-click menu: what can be done with that table's tab. */
function tabMenu(id: string, event: MouseEvent): void {
  event.preventDefault();
  const tab = event.currentTarget as HTMLElement;
  // From the keyboard (the menu key, Shift+F10) the event has no place: open under the tab.
  const box = tab.getBoundingClientRect();
  const x = event.clientX || box.left;
  const y = event.clientY || box.bottom;
  showMenu(x, y, label(id), [
    ["columns", "Compare with…", () => compareWith(id, x, y), order.length < 2 ? "Open another table to compare with" : undefined],
    ["rename", "Rename", () => {
      const name = tabRow.querySelector<HTMLElement>(`.tab-item[data-grid="${CSS.escape(id)}"] .tab-label`);
      if (name) renameInPlace(name, contexts.get(id)!.dataset);
    }],
    "-",
    ["close", "Close", () => void closeGrid(id)],
  ]);
}

/** Back to one grid: `keep` stays on screen; the other remains open as a tab. */
export function unsplit(keep: string): void {
  split = null;
  void activateGrid(keep);
}

export async function closeGrid(id: string): Promise<void> {
  try {
    await api(`/grids/${encodeURIComponent(id)}`, "DELETE");
  } catch (e) {
    // Already closed on the server (a restart, an agent): just drop the tab.
    if ((e as { status?: number }).status !== 404) toast((e as Error).message, "error");
  }
  dropGrid(id);
}

/** Forget a grid that is gone, and show the one beside it. */
export function dropGrid(id: string): void {
  const ctx = contexts.get(id);
  if (!ctx) return;
  const at = order.indexOf(id);
  if (ctx.pane) for (const listener of paneDropped) listener(ctx);
  ctx.view?.destroy();
  ctx.pane?.remove();
  contexts.delete(id);
  order = order.filter((o) => o !== id);
  // Closing one side of a split leaves the other grid on screen.
  const other = split?.includes(id) ? split.find((g) => g !== id) : undefined;
  if (split?.includes(id)) split = null;
  remember("workspace.order", JSON.stringify(order));
  if (activeId === id || other) {
    activeId = null;
    const next = other ?? order[Math.min(at, order.length - 1)];
    if (next) {
      // In the closed table's place in the history: Back never goes to a table that is gone.
      void activateGrid(next, "replace");
      return;
    }
  }
  layout();
  // The last table closed: the Grids landing (the Start view with no project), in its place in the history.
  if (!order.length && view === "grid") return setView(emptyView(), "replace");
  render();
  syncSoon("replace");
}

function moveTab(from: string, before: string | null): void {
  if (from === before) return;
  order = order.filter((o) => o !== from);
  const at = before ? order.indexOf(before) : -1;
  order.splice(at < 0 ? order.length : at, 0, from);
  normalize();
  remember("workspace.order", JSON.stringify(order));
  render();
}

function render(): void {
  if (!tabRow) return;
  remember("workspace.order", JSON.stringify(order));
  const tabs = new Map<string, HTMLElement>();
  for (const id of order) tabs.set(id, tabFor(id));
  clear(
    tabRow,
    // Visualizations, the ERD and the Workbench are the rail's (rail.ts, the owner, 2026-11-16): only grids here.
    ...arrange(tabs),
    draft ? draftTab(draft.name) : null,
    button("New table from a query", () => void newQueryTab(), { icon: "plus", iconOnly: true, class: "ghost tab-new" }),
    openFileButton(),
    openMenuButton(),
    h("div", {
      class: "tab-end",
      ondragover: (e: DragEvent) => e.preventDefault(),
      ondrop: (e: DragEvent) => {
        e.preventDefault();
        if (draggingGroup) moveGroup(draggingGroup, null);
        else if (dragging) moveTab(dragging, null);
      },
    }),
  );
  panesHost.querySelector(".workspace-empty")?.remove();
  if (!order.length) {
    panesHost.append(
      h(
        "div",
        { class: "workspace-empty", role: "status" },
        h("strong", {}, "No grids open"),
      ),
    );
  }
}

/** One grid's tab (it wears its table's connection's colour). */
function tabFor(id: string): HTMLElement {
  const selected = id === activeId && view === "grid";
  const inSplit = split?.includes(id) ?? false;
  const el = h(
    "div",
    {
      class: `tab-item ${selected ? "active" : ""} ${inSplit ? "in-split" : ""}`,
      "data-grid": id,
      role: "tab",
      tabindex: selected ? "0" : "-1",
      "aria-selected": String(selected),
      draggable: "true",
      title: contexts.get(id)!.dataset,
      onclick: (e: MouseEvent) => {
        // The second click of a double-click renames: the first one's redraw replaced this tab,
        // so the browser sends no dblclick to the new one.
        const name = (e.currentTarget as HTMLElement).querySelector<HTMLElement>(".tab-label");
        if (e.detail === 2 && name && (e.target as HTMLElement).closest(".tab-label")) {
          renameInPlace(name, contexts.get(id)!.dataset);
          return;
        }
        if (id === activeId && view === "grid") {
          activations += 1; // already in front: nothing to redraw, but a tab still loading loses
          return;
        }
        showGridView();
        void activateGrid(id);
      },
      onauxclick: (e: MouseEvent) => { if (e.button === 1) void closeGrid(id); },
      oncontextmenu: (e: MouseEvent) => tabMenu(id, e),
      onkeydown: (e: KeyboardEvent) => onTabKey(e, id),
      ondragstart: (e: DragEvent) => { dragging = id; e.dataTransfer?.setData("text/plain", id); },
      ondragend: () => { dragging = null; delete panesHost.dataset.drop; },
      ondragover: (e: DragEvent) => {
        e.preventDefault();
        el.classList.toggle("drop-before", edge(e, el));
        el.classList.toggle("drop-split", !edge(e, el));
      },
      ondragleave: () => el.classList.remove("drop-before", "drop-split"),
      ondrop: (e: DragEvent) => {
        e.preventDefault();
        el.classList.remove("drop-before", "drop-split");
        if (!dragging) return;
        if (edge(e, el)) moveTab(dragging, id);
        else void splitWith(dragging, id, "right");
      },
    },
    inSplit ? h("span", { class: "split-mark", "aria-label": "side by side" }, "◫") : null,
    h("span", { class: "tab-label", title: "Double-click to rename the table" }, label(id)),
    closeButton(id, selected),
  );
  const connection = sources.get(contexts.get(id)!.dataset)?.connection;
  if (connection) el.dataset.connections = connection;
  return el;
}

/** The draft tab: after the grid tabs, named for the table its query will build. */
function draftTab(name: string): HTMLElement {
  const selected = view === "query";
  const close = button(`Close ${name || "the new query"}`, (e) => { e.stopPropagation(); closeDraft(); }, { icon: "close", iconOnly: true, class: "ghost tab-close" });
  if (!selected) close.tabIndex = -1;
  return h(
    "div",
    {
      class: `tab-item tab-draft ${selected ? "active" : ""}`,
      role: "tab",
      tabindex: selected ? "0" : "-1",
      "aria-selected": String(selected),
      title: "Not built yet",
      onclick: () => showQueryView(),
      onauxclick: (e: MouseEvent) => { if (e.button === 1) closeDraft(); },
    },
    icon("sql"),
    h("span", { class: "tab-label" }, name || "New query"),
    close,
  );
}

/** A tab's ×. Only the active tab's takes a Tab stop: the bar is one stop (arrows move between
 * tabs, Delete closes one), so Tab doesn't walk through every tab's button. */
function closeButton(id: string, selected: boolean): HTMLButtonElement {
  const b = button(`Close ${label(id)}`, (e) => { e.stopPropagation(); void closeGrid(id); }, { icon: "close", iconOnly: true, class: "ghost tab-close" });
  if (!selected) b.tabIndex = -1;
  return b;
}

/** The left quarter of a tab is "put it before this tab"; the rest is "side by side". */
function edge(e: DragEvent, el: HTMLElement): boolean {
  const box = el.getBoundingClientRect();
  return e.clientX < box.left + box.width / 4;
}

function onTabKey(event: KeyboardEvent, id: string): void {
  const at = order.indexOf(id);
  const go = (to: number): void => {
    const next = order[(to + order.length) % order.length];
    if (next) void activateGrid(next).then(() => (tabRow.querySelector(".tab-item.active") as HTMLElement | null)?.focus());
  };
  if (event.key === "ArrowRight") go(at + 1);
  else if (event.key === "ArrowLeft") go(at - 1);
  else if (event.key === "Home") go(0);
  else if (event.key === "End") go(order.length - 1);
  else if (event.key === "Enter" || event.key === " ") void activateGrid(id);
  else if (event.key === "Delete") void closeGrid(id);
  else if (event.key === "F2") {
    const tab = event.currentTarget as HTMLElement;
    const name = tab.querySelector<HTMLElement>(".tab-label");
    if (name) renameInPlace(name, contexts.get(id)!.dataset);
  }
}

/** Open the Workbench in its own window, or bring it forward (one window, by name). */
export function openWorkbench(): void {
  const opened = window.open(`/workbench#token=${encodeURIComponent(token)}`, "swissarmybench-workbench");
  opened?.focus();
}
