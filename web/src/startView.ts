/**
 * startView.ts: the home page's Start view, its project group in the Application row, and the strip of
 * tables that need a fix. [WIRE] (The owner, 2026-11-16: "The home page should show recent projects and
 * have a open option for projects.")
 *
 * ROUTING: [START]    /workspace?view=start: New project, Open project…, the recent projects (a click
 *                     opens one; a missing one says so, with Remove from the list), the recent notebooks
 *                     and scripts (each opens in the Workbench window). Shown when nothing is open; the
 *                     mark (Home) brings it back
 *          [PROJECT]  the Application row's first group: the project's name (● with unsaved changes),
 *                     Save (Ctrl+S), Save as…, Close
 *          [FIXES]    a strip under the tabs, only while a table did not come back: its one click
 *          [ASKED]    a double-click on a .sab with unsaved work open: the page asks
 */
import { api, token } from "./api";
import { button, clear, h, icon, toast } from "./dom";
import { visit, withParams } from "./nav";
import { answerAsked, baseName, closeProject, fixTable, folderOf, loadProject, mountProject, newProject, onBeforeSave, onProject, openProject, type Problem, projectLabel, projectState, type ProjectState, reportLayout, saveProject, when } from "./projectFile";

const WORKBENCH = "swissarmybench-workbench";
let host: HTMLElement;
let group: HTMLElement;
let strip: HTMLElement;
let recentFiles: { path: string; exists: boolean }[] = [];
let shownSerial = -1;

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

/** The project's documents show in the Workbench: its window opened (a click's, so no pop-up is
 *  blocked), or told already (it follows the project_changed notice). */
function showDocuments(state: ProjectState | null): void {
  if (!state?.project) return;
  void api("/workbench/window", "POST", { command: "documents", args: {} }).catch(() => openInWorkbench());
}

/** `home`: the page's tabs as a project keeps them (the order, the one in front), and putting them back
 *  when a project opens. */
export function mountStart(element: HTMLElement, appGroup: HTMLElement, fixes: HTMLElement, home: { layout: () => Record<string, unknown>; restore: (layout: Record<string, unknown>) => void }): void {
  host = element;
  group = appGroup;
  strip = fixes;
  mountProject();
  onProject((state) => {
    drawGroup(state);
    drawFixes(state);
    draw(state);
    if (state.asked) void answerAsked().catch((e: Error) => toast(e.message, "error"));
    // A project opened (here, by the agent, a double-click): its tables arrived as tabs; the one in front
    // as it was saved.
    if (state.project && state.project.serial !== shownSerial) {
      shownSerial = state.project.serial;
      const saved = state.project.layout.home;
      if (saved && typeof saved === "object" && Object.keys(saved).length) home.restore(saved as Record<string, unknown>);
    }
    if (!state.project) shownSerial = -1;
  });
  onBeforeSave(() => reportLayout("home", home.layout()));
  void api<{ recent: { path: string; exists: boolean }[] }>("/workbench/home").then(
    (home) => {
      recentFiles = home.recent;
      draw(projectState());
    },
    () => undefined,
  );
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "s") {
      if ((e.target as Element | null)?.closest?.(".monaco-editor")) return;
      e.preventDefault();
      guard(() => saveProject(e.shiftKey))();
    }
  });
}

// ===== the Start view =====

function draw(state: ProjectState): void {
  if (!host) return;
  const projects = state.recent;
  const code = recentFiles.filter((r) => /\.(ipynb|py)$/i.test(r.path) && !/[\\/]sab-project-[^\\/]+[\\/]/.test(r.path)).slice(0, 8);
  clear(
    host,
    h(
      "div",
      { class: "start-page" },
      h(
        "section",
        { class: "start-section", "aria-label": "Start" },
        h("h2", {}, "Start"),
        h(
          "div",
          { class: "start-actions" },
          button("New project", guard(() => newProject().then((s) => showDocuments(s))), { icon: "plus", class: "start-action" }),
          button("Open project…", guard(() => openProject().then((s) => showDocuments(s))), { icon: "folder", class: "start-action" }),
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
                      onclick: guard(() => openProject(r.path).then((s) => showDocuments(s))),
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
      code.length
        ? h(
            "section",
            { class: "start-section", "aria-label": "Recent notebooks and scripts" },
            h("h2", {}, "Notebooks and scripts"),
            h(
              "ul",
              { class: "start-list" },
              ...code.map((r) =>
                h(
                  "li",
                  { class: `start-item ${r.exists ? "" : "missing"}` },
                  h(
                    "button",
                    { type: "button", class: "start-open", title: r.path, disabled: !r.exists, onclick: guard(() => openInWorkbench(r.path)) },
                    icon(/\.ipynb$/i.test(r.path) ? "notebook" : "code"),
                    h("span", { class: "start-name" }, baseName(r.path)),
                    h("span", { class: "start-folder" }, folderOf(r.path)),
                  ),
                  r.exists ? null : h("span", { class: "start-missing" }, "Missing"),
                ),
              ),
            ),
          )
        : null,
    ),
  );
}

// ===== the Application row's project group =====

function drawGroup(state: ProjectState): void {
  const project = state.project;
  group.hidden = !project;
  if (!project) return clear(group);
  clear(
    group,
    h("div", { class: "ribbon-caption" }, h("strong", { class: "project-name", title: project.path ?? project.name }, projectLabel(project))),
    h(
      "div",
      { class: "ribbon-tools" },
      button("Save", guard(() => saveProject()), { icon: "save", class: "ribbon-btn", title: project.read_only ?? "Save (Ctrl+S)" }),
      button("Save as…", guard(() => saveProject(true)), { icon: "folder", class: "ribbon-btn", title: "Save as (Ctrl+Shift+S)" }),
      button("Close", guard(() => closeProject()), { icon: "close", class: "ribbon-btn", title: "Close the project" }),
    ),
  );
}

// ===== tables that did not come back: each with its fix =====

function drawFixes(state: ProjectState): void {
  const problems = state.project?.problems ?? [];
  strip.hidden = problems.length === 0;
  clear(strip, ...problems.map((p) => fixRow(p)));
}

function fixRow(problem: Problem): HTMLElement {
  const how = {
    addConnection: () => visit(withParams({ open: "connections", at: "types", type: null, name: null })),
    openNotebook: (path: string) => void openInWorkbench(path),
  };
  const retry = problem.fix.kind === "add_connection" || problem.fix.kind === "open_notebook";
  return h(
    "div",
    { class: "project-fix", role: "status", "data-table": problem.table },
    icon("exclude"),
    h("strong", {}, problem.table),
    h("span", { class: "project-fix-message" }, problem.message),
    button(problem.fix.label, guard(() => fixTable(problem, how)), { class: "primary" }),
    retry ? button("Try again", guard(() => fixTable(problem, { ...how, retry: true })), { class: "ghost" }) : null,
    problem.fix.kind === "remove" ? null : button(`Remove ${problem.table}`, guard(() => api("/project/fix", "POST", { table: problem.table, remove: true }).then(() => loadProject())), { icon: "close", iconOnly: true, class: "ghost" }),
  );
}
