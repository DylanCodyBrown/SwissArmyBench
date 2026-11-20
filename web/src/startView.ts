/**
 * startView.ts: the grid page's Grids landing, its project group in the Application row, and the strip of
 * tables that need a fix. [WIRE] (The owner, 2026-11-16: "start a new project … have the user save a project
 * file … ask about autosave … we start in grids"; 2026-11-18: "give this button its own page for projects
 * dont share the grid as the home page": the Start view left for the Projects page, projectsPage.ts.)
 *
 * ROUTING: [NEW QUERY]  /workspace?view=grids (no grid open) or view=new (the "+" over grids): the New query
 *                     page (the owner, 2026-11-20: "get rid of all of this this should just be a new query page, with the active connections and you can click
 *                     one to start a new grid sql"): the grid page with no table open, and the "+" (Ctrl+T,
 *                     Ctrl+N). Open tables (DuckDB) first while a grid is open, then each connection that runs
 *                     SQL (queryTab.ts queryConnections: Query from's own list), its kind in words, its colour,
 *                     a password missing here; a click (or Enter) opens the draft with Query from set
 *                     (panes.ts openQueryDraft); arrows move between them; a search past 8. No connection: the
 *                     empty state (Add connection, Try it with sample data). The project's tables that did not
 *                     come back, each with its fix, below. Open a file and Paste are the tab row's and Ctrl+V.
 *          [PROJECT]  in the Application row, before Zoom: the project's name (● with unsaved changes),
 *                     Save (Ctrl+S), Copy to…, Close, the Autosave switch
 *          [FIXES]    a strip under the tabs, only while a table did not come back: its one click
 *          [ASKED]    `swissarmybench open <folder>` with unsaved work open: the page asks
 */
import { api, onNotice, token } from "./api";
import { button, clear, h, icon } from "./dom";
import { visit, withParams } from "./nav";
import { gridList, onAgentView, openQueryDraft, viewingLanding } from "./panes";
import { answerAsked, autosaveSwitch, closeProject, copyProject, exportOutline, fixTable, loadProject, mountProject, onBeforeSave, onProject, type Problem, privateSwitch, projectLabel, projectState, type ProjectState, reportLayout, saveProject, setAutosave, setPrivate } from "./projectFile";
import { queryConnections, type QueryConnection } from "./queryTab";
import { openConnectionTypes } from "./connectionsWindow";
import { emptyState } from "./emptyState";
import { forgetSwap, onConnectionChange, openMoveChooser, recentSwaps, undoSwap } from "./swapConnection";
import { errorHere } from "./errorNote";

const WORKBENCH = "swissarmybench-workbench";
let host: HTMLElement;
let group: HTMLElement;
let strip: HTMLElement;
let shownSerial = -1;
let connections: QueryConnection[] = [];
let loaded = false;
let search = "";

const guard = (act: () => Promise<unknown>) => (): void => void act().catch((e: Error) => errorHere(e));

/** Open the Workbench window on `path` (a notebook or script), or bring it forward with that file. */
export async function openInWorkbench(path?: string): Promise<void> {
  if (path) {
    try {
      await api("/workbench/window", "POST", { command: "file.open", args: { path } });
      window.open("", WORKBENCH)?.focus();
      return;
    } catch {
      /* no Workbench window yet: one, opened on the file */
    }
  }
  const words = new URLSearchParams({ token, ...(path ? { open: path } : {}) });
  window.open(`/workbench#${words.toString()}`, WORKBENCH)?.focus();
}

/** `home`: the page's tabs as a project keeps them (the order, the one in front), and putting them back
 *  when a project opens. */
export function mountStart(element: HTMLElement, appGroup: HTMLElement, fixes: HTMLElement, home: { layout: () => Record<string, unknown>; restore: (layout: Record<string, unknown>) => void }): void {
  host = element;
  group = appGroup;
  strip = fixes;
  mountProject();
  void loadConnections(); // the New query page's connections, a project open or not
  onConnectionChange(() => {
    if (lastState) drawFixes(lastState);
  });
  onProject((state) => {
    drawGroup(state);
    drawFixes(state);
    draw(state);
    if (state.asked) void answerAsked().catch((e: Error) => errorHere(e));
    // A project opened (here, by the agent, a double-click): its tables arrived as tabs; the one in front
    // as it was saved.
    if (state.project && state.project.serial !== shownSerial) {
      shownSerial = state.project.serial;
      void loadConnections();
      const saved = state.project.layout.home;
      if (saved && typeof saved === "object" && Object.keys(saved).length) home.restore(saved as Record<string, unknown>);
    }
    if (!state.project) shownSerial = -1;
  });
  onAgentView(() => {
    draw(projectState());
    if (lastState) drawFixes(lastState);
    if (viewingLanding()) focusFirst();
  });
  onNotice((notice) => {
    if (notice.type === "blades_changed") void loadConnections();
  });
  onBeforeSave(() => reportLayout("home", home.layout()));
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "s") {
      if ((e.target as Element | null)?.closest?.(".monaco-editor")) return;
      e.preventDefault();
      guard(() => (e.shiftKey ? copyProject() : saveProject()))();
    }
  });
}

async function loadConnections(): Promise<void> {
  try {
    connections = await queryConnections();
  } catch {
    connections = [];
  }
  loaded = true;
  draw(projectState());
}

// ===== the New query page =====

function draw(state: ProjectState): void {
  // Drawn whether or not it is in front (hidden behind the grids), so it never keeps a fix that is gone.
  if (host) drawLanding(state);
}

/** A choice: the draft, Query from set ("" the open tables). */
function choice(from: string, name: string, words: string, extra: { connection?: boolean; needs?: string | null } = {}): HTMLElement {
  const item = h(
    "button",
    {
      type: "button",
      class: "new-query-choice",
      "data-from": from,
      ...(extra.connection ? { "data-connections": name } : {}),
      onclick: () => void openQueryDraft(from).catch((e: Error) => errorHere(e)),
    },
    h("span", { class: "new-query-icon", "aria-hidden": "true" }, icon(extra.connection ? "plug" : "grids")),
    h("span", { class: "new-query-text" }, h("strong", {}, name), h("span", { class: "new-query-kind" }, words)),
    extra.needs ? h("span", { class: "new-query-needs", title: extra.needs }, icon("warning"), extra.needs) : null,
  );
  return h("li", {}, item);
}

/** Arrows move between the choices (and from the search into them); Enter is the button's own. */
function onListKey(e: KeyboardEvent): void {
  const items = [...host.querySelectorAll<HTMLButtonElement>(".new-query-choice")].filter((b) => !b.closest("li")?.hidden);
  if (!items.length) return;
  const at = items.indexOf(document.activeElement as HTMLButtonElement);
  const move: Record<string, number> = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 };
  if (at < 0 && (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "Home" || e.key === "End")) return; // the search box's caret
  let next: number | null = null;
  if (e.key in move) next = at < 0 ? 0 : (at + move[e.key]! + items.length) % items.length;
  else if (e.key === "Home") next = 0;
  else if (e.key === "End") next = items.length - 1;
  if (next === null) return;
  e.preventDefault();
  items[next]!.focus();
}

/** On show: the search (past 8 connections), else the first choice, takes the keys. */
function focusFirst(): void {
  requestAnimationFrame(() => {
    // Only when nothing else has the keys (a page over it, the rail, a box being typed in keep them).
    const now = document.activeElement;
    if (!viewingLanding() || (now && now !== document.body && !now.classList.contains("tab-new"))) return;
    host.querySelector<HTMLElement>(".new-query-search, .new-query-choice")?.focus({ preventScroll: true });
  });
}

function drawLanding(state: ProjectState): void {
  const problems = state.project?.problems ?? [];
  const gridsOpen = gridList().length > 0;
  const many = connections.length > 8;
  const list = h(
    "ul",
    { class: "new-query-list", "aria-label": "Query from" },
    gridsOpen ? choice("", "Open tables (DuckDB)", "The grids open here, as they show them") : null,
    ...connections.map((c) => choice(c.name, c.name, c.type, { connection: true, needs: c.needsPassword })),
  );
  const filter = (): void => {
    const words = search.trim().toLocaleLowerCase();
    for (const li of list.querySelectorAll<HTMLElement>("li")) li.hidden = !!words && !(li.textContent ?? "").toLocaleLowerCase().includes(words);
  };
  const searchBox = many
    ? h("input", {
        type: "search",
        class: "new-query-search",
        placeholder: "Search connections",
        "aria-label": "Search connections",
        "data-no-variables": "",
        value: search,
        oninput: (e: Event) => {
          search = (e.target as HTMLInputElement).value;
          filter();
        },
        onkeydown: (e: KeyboardEvent) => {
          if (e.key !== "Enter") return;
          e.preventDefault();
          list.querySelector<HTMLButtonElement>("li:not([hidden]) .new-query-choice")?.click();
        },
      })
    : null;
  if (many) filter();
  const none = loaded && !connections.length
    ? emptyState({ icon: "plug", line: "Add a connection to query its tables in its own SQL.", action: { label: "Add connection", icon: "plus", run: () => openConnectionTypes() } })
    : null;
  const hadFocus = host.contains(document.activeElement) ? (document.activeElement as HTMLElement).dataset.from : undefined;
  clear(
    host,
    h(
      "div",
      { class: "start-page new-query-page", onkeydown: onListKey },
      h("h1", { class: "new-query-title" }, "New query"),
      searchBox,
      gridsOpen || connections.length ? list : null,
      none,
      problems.length
        ? h("section", { class: "start-section landing-fixes", "aria-label": "Tables to bring back" }, h("h2", {}, "Tables"), ...problems.map((p) => fixRow(p)))
        : null,
    ),
  );
  // A redraw (a connection saved, the list read) keeps the choice that had the keys.
  if (hadFocus !== undefined) host.querySelector<HTMLElement>(`.new-query-choice[data-from="${CSS.escape(hadFocus)}"]`)?.focus();
  else if (viewingLanding()) focusFirst();
}

// ===== the Application row's project group =====

function drawGroup(state: ProjectState): void {
  const project = state.project;
  group.hidden = !project;
  if (!project) return clear(group);
  const autosave = autosaveSwitch(project.autosave, (on) => void setAutosave(on).catch((e: Error) => errorHere(e)));
  if (project.autosave_error) autosave.element.title = project.autosave_error;
  // In the Application row (the owner, 2026-11-16): the project's name, then its tools, before Zoom.
  clear(
    group,
    h("strong", { class: "project-name", title: project.folder }, projectLabel(project)),
    button("Save", guard(() => saveProject()), { icon: "save", class: "ribbon-btn", title: project.read_only ?? "Save (Ctrl+S)" }),
    button("Copy to…", guard(() => copyProject()), { icon: "copy", class: "ribbon-btn", title: "Copy project to another folder (Ctrl+Shift+S)" }),
    button("Export outline", guard(() => exportOutline()), { icon: "outline", class: "ribbon-btn", title: "ARCHITECTURE.md: the project for someone joining it" }),
    button("Close", guard(() => closeProject()), { icon: "close", class: "ribbon-btn", title: "Close the project" }),
    autosave.element,
    privateSwitch(project.private === true, (on) => void setPrivate(on).catch((e: Error) => errorHere(e))),
  );
}

// ===== tables that did not come back: each with its fix =====

let lastState: ProjectState | null = null;

function drawFixes(state: ProjectState): void {
  lastState = state;
  const problems = state.project?.problems ?? [];
  const swaps = recentSwaps();
  strip.hidden = (problems.length === 0 && swaps.length === 0) || viewingLanding();
  clear(strip, ...problems.map((p) => fixRow(p)), ...swaps.map((s) => swapRow(s)));
}

/** A table moved to another connection from this page: its Undo stays here until used or put away. */
function swapRow(done: { table: string; from: string | null; to: string }): HTMLElement {
  return h(
    "div",
    { class: "project-fix swap-done", role: "status", "data-table": done.table },
    icon("plug"),
    h("strong", {}, done.table),
    h("span", { class: "project-fix-message" }, done.from ? `${done.from} → ${done.to}` : done.to),
    button("Undo", guard(() => undoSwap(done.table)), { icon: "undo", class: "ghost" }),
    button(`Put away ${done.table}`, () => forgetSwap(done.table), { icon: "close", iconOnly: true, class: "ghost" }),
  );
}

function fixRow(problem: Problem): HTMLElement {
  const how = {
    addConnection: () => visit(withParams({ open: "connections", at: "types", type: null, name: null })),
    setPassword: (name: string) => visit(withParams({ open: "connections", at: "edit", type: null, name })),
    openNotebook: (path: string) => void openInWorkbench(path),
  };
  const retry = problem.fix.kind === "add_connection" || problem.fix.kind === "open_notebook" || problem.fix.kind === "password";
  return h(
    "div",
    { class: "project-fix", role: "status", "data-table": problem.table },
    icon("exclude"),
    h("strong", {}, problem.table),
    h("span", { class: "project-fix-message" }, problem.message),
    button(problem.fix.label, guard(() => fixTable(problem, how)), { class: "primary" }),
    // A deleted connection (the owner, 2026-11-16): every table that used it moves to another at once.
    problem.fix.kind === "add_connection" && problem.fix.connection ? button("Use another connection…", guard(() => openMoveChooser(problem.fix.connection!)), { icon: "plug" }) : null,
    retry ? button("Try again", guard(() => fixTable(problem, { ...how, retry: true })), { class: "ghost" }) : null,
    problem.fix.kind === "remove" ? null : button(`Remove ${problem.table}`, guard(() => api("/project/fix", "POST", { table: problem.table, remove: true }).then(() => loadProject())), { icon: "close", iconOnly: true, class: "ghost" }),
  );
}
