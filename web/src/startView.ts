/**
 * startView.ts: the grid page's Grids landing, its project group in the Application row, and the strip of
 * tables that need a fix. [WIRE] (The owner, 2026-11-16: "start a new project … have the user save a project
 * file … ask about autosave … we start in grids"; 2026-11-18: "give this button its own page for projects
 * dont share the grid as the home page": the Start view left for the Projects page, projectsPage.ts.)
 *
 * ROUTING: [GRIDS]    /workspace?view=grids: the grid page with no table open, a project open or not: Open a
 *                     file, Paste, Query (the "+" tab), the connections (each its tables) and the catalog, the
 *                     project's tables that did not come back, each with its fix; with no project, a link to
 *                     Projects
 *          [PROJECT]  in the Application row, before Zoom: the project's name (● with unsaved changes),
 *                     Save (Ctrl+S), Copy to…, Close, the Autosave switch
 *          [FIXES]    a strip under the tabs, only while a table did not come back: its one click
 *          [ASKED]    `swissarmybench open <folder>` with unsaved work open: the page asks
 */
import { api, onNotice, token } from "./api";
import { button, clear, h, icon, toast } from "./dom";
import { openLayer, PROJECTS_URL, visit, withParams } from "./nav";
import { newQueryTab, onAgentView, viewingLanding } from "./panes";
import { answerAsked, autosaveSwitch, closeProject, copyProject, exportOutline, fixTable, loadProject, mountProject, onBeforeSave, onProject, type Problem, privateSwitch, projectLabel, projectState, type ProjectState, reportLayout, saveProject, setAutosave, setPrivate } from "./projectFile";
import { PROJECTS } from "./projectsPage";
import { openFile } from "./openFile";
import { forgetSwap, onConnectionChange, openMoveChooser, recentSwaps, undoSwap } from "./swapConnection";

const WORKBENCH = "swissarmybench-workbench";
let host: HTMLElement;
let group: HTMLElement;
let strip: HTMLElement;
let shownSerial = -1;
let paste: () => void = () => undefined;
let connections: { name: string; connection: string; needs_password: unknown; tables_kind?: string | null }[] = [];

const guard = (act: () => Promise<unknown>) => (): void => void act().catch((e: Error) => toast(e.message, "error"));

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
 *  when a project opens; `paste`: the clipboard's table, as Ctrl+V would. */
export function mountStart(element: HTMLElement, appGroup: HTMLElement, fixes: HTMLElement, home: { layout: () => Record<string, unknown>; restore: (layout: Record<string, unknown>) => void; paste: () => void }): void {
  host = element;
  group = appGroup;
  strip = fixes;
  paste = home.paste;
  mountProject();
  void loadConnections(); // the landing's connections, a project open or not
  onConnectionChange(() => {
    if (lastState) drawFixes(lastState);
  });
  onProject((state) => {
    drawGroup(state);
    drawFixes(state);
    draw(state);
    if (state.asked) void answerAsked().catch((e: Error) => toast(e.message, "error"));
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
  onAgentView(() => draw(projectState()));
  onNotice((notice) => {
    if (notice.type === "blades_changed" && projectState().project) void loadConnections();
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
    connections = (await api<{ connections: typeof connections }>("/connections")).connections.filter((c) => c.connection !== "vault" && c.tables_kind !== "api");
  } catch {
    connections = [];
  }
  draw(projectState());
}

// ===== the Grids landing =====

function draw(state: ProjectState): void {
  if (host && viewingLanding()) drawLanding(state);
}

/** The catalog page, on one connection's catalog (or all of them). */
function openCatalog(name?: string): void {
  const hash = new URLSearchParams({ ...(token ? { token } : {}), ...(name ? { catalog: name } : {}) }).toString();
  location.assign(`/catalog${hash ? `#${hash}` : ""}`);
}

function drawLanding(state: ProjectState): void {
  const problems = state.project?.problems ?? [];
  clear(
    host,
    h(
      "div",
      { class: "start-page landing-page" },
      h(
        "section",
        { class: "start-section", "aria-label": "Bring data in" },
        h("h2", {}, "Grids"),
        h(
          "div",
          { class: "start-actions" },
          button("Open a file…", () => void openFile(), { icon: "folder", class: "start-action" }),
          button("Paste", () => paste(), { icon: "copy", class: "start-action", title: "Ctrl+V" }),
          button("Query", guard(() => newQueryTab("push")), { icon: "sql", class: "start-action" }),
        ),
        // No project open: the way to one (the Projects page, the rail's mark).
        state.project
          ? null
          : h("p", { class: "landing-projects" }, "No project is open. ", h(
              "a",
              {
                href: PROJECTS_URL,
                class: "landing-projects-link",
                onclick: (e: MouseEvent) => {
                  if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
                  e.preventDefault();
                  openLayer("projects");
                },
              },
              PROJECTS,
            )),
      ),
      h(
        "section",
        { class: "start-section", "aria-label": "From a connection" },
        h("h2", {}, "From a connection"),
        h(
          "div",
          { class: "landing-connections" },
          ...connections.map((c) =>
            // Its tables as a tree (connectionTree.ts, on the Connections page): Open, Open all, Copy name.
            button(c.name, () => visit(withParams({ open: "connections", at: "detail", type: null, name: c.name })), { icon: "plug", class: "start-action", title: c.needs_password ? `${c.name}: needs a password on this computer` : c.name }),
          ),
          button("Catalog", () => openCatalog(), { icon: "folder", class: "start-action" }),
          button("Add connection", () => visit(withParams({ open: "connections", at: "types", type: null, name: null })), { icon: "plus", class: "start-action" }),
        ),
      ),
      problems.length
        ? h("section", { class: "start-section landing-fixes", "aria-label": "Tables to bring back" }, h("h2", {}, "Tables"), ...problems.map((p) => fixRow(p)))
        : null,
    ),
  );
}

// ===== the Application row's project group =====

function drawGroup(state: ProjectState): void {
  const project = state.project;
  group.hidden = !project;
  if (!project) return clear(group);
  const autosave = autosaveSwitch(project.autosave, (on) => void setAutosave(on).catch((e: Error) => toast(e.message, "error")));
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
    privateSwitch(project.private === true, (on) => void setPrivate(on).catch((e: Error) => toast(e.message, "error"))),
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
