/**
 * startView.ts: the home page's Start view and Grids landing, its project group in the Application row,
 * and the strip of tables that need a fix. [WIRE] (The owner, 2026-11-16: "The home page should show
 * recent projects and have a open option for projects"; "start a new project … have the user save a
 * project file … ask about autosave … we start in grids"; "new here take a tour should be on the project
 * page and no where else".)
 *
 * ROUTING: [START]    /workspace?view=start: New project, Open project…, the recent projects (a click
 *                     opens one; a missing one says so, with Remove from the list), and the tour (only
 *                     here). Shown with no project open; the mark (Home) brings it back
 *          [GRIDS]    /workspace?view=grids: Grids with no table open while a project is: Open a file,
 *                     Paste, Query (the "+" tab), the project's connections (each its catalog) and the
 *                     catalog, and the project's tables that did not come back, each with its fix
 *          [PROJECT]  in the Application row, before Zoom: the project's name (● with unsaved changes),
 *                     Save (Ctrl+S), Save as…, Close, the Autosave switch
 *          [FIXES]    a strip under the tabs, only while a table did not come back: its one click
 *          [ASKED]    a double-click on a .sab with unsaved work open: the page asks
 */
import { api, onNotice, token } from "./api";
import { button, clear, h, icon, toast } from "./dom";
import { visit, withParams } from "./nav";
import { gridList, newQueryTab, onAgentView, setEmptyView, showGridsLanding, showStartView, viewingLanding, viewingStart } from "./panes";
import { answerAsked, autosaveSwitch, baseName, closeProject, fixTable, folderOf, loadProject, mountProject, newProject, onBeforeSave, onProject, openProject, type Problem, projectLabel, projectState, type ProjectState, reportLayout, saveProject, setAutosave, when } from "./projectFile";
import { openFile } from "./openFile";
import { tourButton } from "./tour";
import { forgetSwap, onConnectionChange, openMoveChooser, recentSwaps, undoSwap } from "./swapConnection";

const WORKBENCH = "swissarmybench-workbench";
let host: HTMLElement;
let group: HTMLElement;
let strip: HTMLElement;
let shownSerial = -1;
let paste: () => void = () => undefined;
let connections: { name: string; connection: string; needs_password: unknown }[] = [];

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

/** A project opened or started here: its Grids (its tables arrive as tabs; with none, the landing). */
function showGrids(state: ProjectState | null): void {
  if (!state?.project) return;
  if (!gridList().length) showGridsLanding("push");
}

/** `home`: the page's tabs as a project keeps them (the order, the one in front), and putting them back
 *  when a project opens; `paste`: the clipboard's table, as Ctrl+V would. */
export function mountStart(element: HTMLElement, appGroup: HTMLElement, fixes: HTMLElement, home: { layout: () => Record<string, unknown>; restore: (layout: Record<string, unknown>) => void; paste: () => void }): void {
  host = element;
  group = appGroup;
  strip = fixes;
  paste = home.paste;
  // With no table open: the Grids landing while a project is open, else the Start view.
  setEmptyView(() => (projectState().project ? "grids" : "start"));
  mountProject();
  onConnectionChange(() => {
    if (lastState) drawFixes(lastState);
  });
  onProject((state) => {
    drawGroup(state);
    drawFixes(state);
    // The landing follows the project: Start with none, Grids with one (unless Start was asked for).
    const asked = new URLSearchParams(location.search).get("view");
    if (state.project && viewingStart() && !viewingLanding() && asked !== "start" && !gridList().length) showGridsLanding("replace");
    else if (!state.project && viewingLanding()) showStartView("replace");
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
      guard(() => saveProject(e.shiftKey))();
    }
  });
}

async function loadConnections(): Promise<void> {
  try {
    connections = (await api<{ connections: typeof connections }>("/connections")).connections.filter((c) => c.connection !== "vault");
  } catch {
    connections = [];
  }
  draw(projectState());
}

// ===== the Start view and the Grids landing (one host: the view in front says which) =====

function draw(state: ProjectState): void {
  if (!host) return;
  if (viewingLanding()) return drawLanding(state);
  const projects = state.recent;
  clear(
    host,
    h(
      "div",
      { class: "start-page" },
      h(
        "section",
        { class: "start-section", "aria-label": "Start" },
        h("div", { class: "start-head" }, h("h2", {}, "Start"), tourButton()),
        h(
          "div",
          { class: "start-actions" },
          button("New project", guard(() => newProject().then((s) => showGrids(s))), { icon: "plus", class: "start-action" }),
          button("Open project…", guard(() => openProject().then((s) => showGrids(s))), { icon: "folder", class: "start-action" }),
        ),
      ),
      projects.length
        ? h(
            "section",
            { class: "start-section", "aria-label": "Recent projects" },
            h("h2", {}, "Recent"),
            h(
              "ul",
              { class: "start-list" },
              ...projects.map((r) =>
                h(
                  "li",
                  { class: `start-item ${r.exists ? "" : "missing"}`, "data-path": r.path },
                  h(
                    "button",
                    {
                      type: "button",
                      class: "start-open",
                      title: r.path,
                      disabled: !r.exists,
                      onclick: guard(() => openProject(r.path).then((s) => showGrids(s))),
                    },
                    icon("project"),
                    h("span", { class: "start-name" }, baseName(r.path).replace(/\.sab$/i, "")),
                    h("span", { class: "start-folder" }, folderOf(r.path)),
                  ),
                  r.exists ? h("span", { class: "start-when" }, when(r.opened)) : h("span", { class: "start-missing" }, "Missing"),
                  r.exists
                    ? null
                    : button("Remove from the list", guard(() => api("/project/recent/remove", "POST", { path: r.path }).then(() => loadProject())), { icon: "close", iconOnly: true, class: "ghost" }),
                ),
              ),
            ),
          )
        : null,
    ),
  );
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
      ),
      h(
        "section",
        { class: "start-section", "aria-label": "From a connection" },
        h("h2", {}, "From a connection"),
        h(
          "div",
          { class: "landing-connections" },
          ...connections.map((c) =>
            button(c.name, () => openCatalog(c.name), { icon: "plug", class: "start-action", title: c.needs_password ? `${c.name}: needs a password on this computer` : c.name }),
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
    h("strong", { class: "project-name", title: project.path ?? project.name }, projectLabel(project)),
    button("Save", guard(() => saveProject()), { icon: "save", class: "ribbon-btn", title: project.read_only ?? "Save (Ctrl+S)" }),
    button("Save as…", guard(() => saveProject(true)), { icon: "folder", class: "ribbon-btn", title: "Save as (Ctrl+Shift+S)" }),
    button("Close", guard(() => closeProject()), { icon: "close", class: "ribbon-btn", title: "Close the project" }),
    autosave.element,
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
