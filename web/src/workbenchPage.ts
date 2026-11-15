/**
 * workbenchPage.ts: the Workbench, in a window of its own (Plans/workbench-and-connections.plan.md;
 * opened from the grid page's Workbench tab). [COMPOSITION]
 *
 *   [PANES]    after RStudio (workbenchLayout.ts): the source, its console under it, Variables on the
 *              right; splitters; a status bar (kernel, environment, cursor). Pictures go to the Sandbox
 *   [AGENT]    right-click an error or selected code: Send to the agent (workbenchAgent.ts)
 *   [LEFT]     the side bar (catalogRail.ts, Ctrl+B folds it): Connections and Blades (drag one into a
 *              cell or the script for its line; Add connection; a new blade), and the data explorer
 *              (each connection's catalog: drag a table or column for its name)
 *   [FILE]     New notebook, New script, Open…, Recent ▾, Save, Save as… (the file chooser: real paths)
 *   [TABS]     the open documents (a dot when changed); closing one stops its kernel
 *   [RUN]      the Python the kernel runs in (this server's own, or a project's environment), the
 *              kernel's state, Run all or Run file, Interrupt, Restart
 *   [DOC]      a notebook (workbenchNotebook.ts) or a script (workbenchScript.ts), each with its own
 *              console (workbenchConsole.ts) on its kernel; a blade being edited; a table from the explorer
 *   [COMMANDS] every action by one name (workbenchCommands.ts): the palette (Ctrl+Shift+P), the keys, and
 *              the agent's workbench_window tool
 *   [KEYS]     F5 runs (the file, or every cell) wherever the focus is, never reloading the window;
 *              Ctrl+S saves, Ctrl+O opens; Ctrl+Z outside an editor undoes a cell's delete or move;
 *              Ctrl+1 to Ctrl+3 (and F6) move between the panes; Ctrl+Alt+Page Up and Page Down switch
 *              documents; F1 on a name shows its help
 *   [RESTORE]  open documents and their unsaved text come back after a reload or a crashed tab (kept in
 *              this window's session storage, in the browser only: nothing is written to disk)
 *   [TABLES]   every table open in the grid has a read-only cell in the document it belongs to
 *              (docs/ideas.md, 2026-11-14): the document whose kernel sent it, else the one that
 *              already holds its cell, else the one in front. The toolbar offers Run tables when a
 *              table's cell is out of date or has not run
 *   [STREAMLIT] there is no Streamlit kind of cell: a Python cell that calls Streamlit shows live in
 *              its cell (workbenchStreamlit.ts). A Streamlit app is a document of its own, a canvas
 *              (workbenchCanvas.ts): New app opens one as a tab; any Python cell is dragged onto it (onto
 *              its tab too) or copied and pasted, as a link; Play shows the page live in place
 *   [PROJECT]  a project is a folder that starts with data.ipynb (its export: data.py): New project,
 *              Open project (its files as tabs, the folder named beside them), Export data.py
 *   [POP OUT]  a saved document moves into a Workbench window of its own (the tab's pop-out button)
 *
 * ROUTING: /workbench/home, /open, /save, /pythons (routes_workbench.py); kernels in workbenchKernel.ts.
 */
import { handleAgentNotice, loadApprovals } from "./agentAccess";
import { api, ApiError, connect, onNotice, openedWith, tellFocus, token } from "./api";
import { type BladeKind, editBlade, showTemplatePicker } from "./bladeEditor";
import { mountRail, schemaDetails, tableDetails, watchTheme } from "./catalogRail";
import { button, clear, h, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { effectiveTheme } from "./theme";
import { allCommands, answerAgent, type Command, openPalette, registerCommands, runCommand } from "./workbenchCommands";
import { consoleView, type ConsoleView } from "./workbenchConsole";
import { forgetCatalogs, listDatasets, pythonCompleter, setDialects } from "./workbenchCompletion";
import { newEnvironment } from "./workbenchEnvironment";
import type { Fix } from "./workbenchErrors";
import { mountLayout } from "./workbenchLayout";
import { setDocumentName } from "./workbenchAgent";
import { fetchTables, type TableInfo } from "./workbenchTables";
import { variablesPanel } from "./workbenchVariables";
import { Kernel, WINDOW_ID } from "./workbenchKernel";
import { type CellData, notebookView, type NotebookView } from "./workbenchNotebook";
import { scriptView, type ScriptView } from "./workbenchScript";
import { canvasView, type CanvasView } from "./workbenchCanvas";
import { CELL_DRAG, draggedLink, problemText, type SavedPage, StreamlitDoc, type StreamlitHost } from "./workbenchStreamlit";

watchTheme();

interface Doc {
  id: number;
  kind: "notebook" | "script" | "app" | "blade" | "table";
  title: string;
  path: string | null;
  modified: number | null;
  dirty: boolean;
  kernel: Kernel | null;
  python: string | null;
  element: HTMLElement;
  notebook?: NotebookView;
  script?: ScriptView;
  /** Its console, on its kernel (notebooks and scripts). */
  console?: ConsoleView;
  /** A notebook's console was used (clicked, focused, run in): shown at its size from then on. */
  consoleUsed?: boolean;
  /** A notebook's or script's own app on the server: its Python cells, the live ones' state. */
  streamlit?: StreamlitDoc;
  /** A Streamlit app's canvas. */
  canvas?: CanvasView;
}

interface PythonChoice {
  python: string;
  version: string;
  ipykernel: boolean;
  swissarmygrid: boolean;
}

const tabs = document.getElementById("wb-tabs") as HTMLElement;
const toolbar = document.getElementById("wb-toolbar") as HTMLElement;
// The four panes; Variables docked top right (the toolbar's Variables shows or hides the right column).
const layout = mountLayout(
  document.getElementById("wb-body") as HTMLElement,
  document.querySelector(".wb-layout > .cat-rail") as HTMLElement,
  document.querySelector(".wb-main") as HTMLElement,
  () => focusSource(),
  () => focusConsole(),
);
const variables = variablesPanel(() => {
  layout.toggle("right", false);
  drawToolbar();
});
layout.variables.append(variables.element);
const docHost = layout.source;
// A click or the focus in the console (a compact title bar too) opens it at its size.
for (const kind of ["pointerdown", "focusin"]) layout.console.addEventListener(kind, () => current && useConsole(current));
let cursor = { line: 1, column: 1 };
const docs: Doc[] = [];
let current: Doc | null = null;
let counter = 0;
let homeFolder = "";
let pythons: PythonChoice[] = [];
let connectionNames: string[] = [];
let workspaceNames: string[] = []; // the Power BI workspaces
let datasetNames: string[] = []; // their datasets, as a DAX cell names them: Finance/Sales model
let bladeNames: string[] = [];
let codeNames: { name: string; connection: string; kind: string }[] = [];
let editingBlade = false;

const baseName = (path: string): string => path.split(/[\\/]/).pop() ?? path;

async function loadConnections(): Promise<void> {
  try {
    const every = (await api<{ blades: { name: string; connection?: string | null; code_name?: string | null; dialect?: string | null }[] }>("/blades")).blades;
    setDialects(every);
    // A SQL cell's sources: every connection but a Power BI workspace, whose datasets are a DAX cell's.
    connectionNames = every.filter((b) => b.connection && b.connection !== "vault" && b.dialect !== "dax").map((b) => b.name);
    workspaceNames = every.filter((b) => b.connection && b.dialect === "dax").map((b) => b.name);
    bladeNames = every.filter((b) => !b.connection).map((b) => b.name);
    codeNames = every.filter((b) => b.code_name).map((b) => ({ name: b.code_name!, connection: b.name, kind: b.connection ?? "" }));
  } catch {
    connectionNames = [];
    workspaceNames = [];
    bladeNames = [];
    codeNames = [];
  }
  await loadDatasets();
}

/** The workspaces' datasets, from their catalogs (asked again when a catalog loads). */
async function loadDatasets(): Promise<void> {
  datasetNames = await listDatasets(workspaceNames);
}

// ===== documents =====

const names = (): { connections: string[]; blades: string[]; codeNames: typeof codeNames; datasets: string[] } => ({ connections: connectionNames, blades: bladeNames, codeNames, datasets: datasetNames });
const hooks = {
  cursor: (line: number, column: number): void => {
    cursor = { line, column };
    drawStatus();
  },
  help: (): void => void showHelp(),
};

// ===== tables: each open table's read-only cell lives in one document =====

let tables: TableInfo[] = [];
const tableOwner = new Map<string, Doc>();
const tablesSent = new Map<Doc, string>();
const tablesHost = h("span", { class: "wb-tables-tool" });
const viewOf = (doc: Doc): NotebookView | ScriptView | undefined => doc.notebook ?? doc.script;
let assignTimer: number | null = null;

/** Which document holds each table's cell: the one whose kernel sent the table to the grid; else one
 *  that already holds its cell (from its file); else, for a table no Python made (a file, a paste, a
 *  connection, a "+" tab's query), the document in front. Once given, it stays. A table sent by a
 *  Python outside the Workbench (Jupyter, a script in another editor) has no cell here: the code that
 *  makes it lives there, where the app cannot write. */
function assignTables(): void {
  const code = docs.filter((d) => d.notebook || d.script);
  for (const [name, doc] of [...tableOwner]) if (!docs.includes(doc) || !tables.some((t) => t.name === name)) tableOwner.delete(name);
  for (const table of tables) {
    if (tableOwner.has(table.name)) continue;
    const noPython = table.origin !== "python" && table.origin !== "unknown";
    // In a project a table's read-only cell lives in data.ipynb (its export data.py is what the
    // other notebooks and the pages import): a table no document made goes there.
    const data = code.find(isData);
    const found = (table.kernel ? code.find((d) => d.kernel?.id === table.kernel) : undefined) ?? code.find((d) => viewOf(d)!.holdsTable(table.name)) ?? data ?? (noPython && current && code.includes(current) ? current : undefined);
    if (found) tableOwner.set(table.name, found);
  }
  for (const doc of code) {
    const mine = tables.filter((t) => tableOwner.get(t.name) === doc);
    const signature = JSON.stringify(mine.map((t) => [t.name, t.code, t.loaded, t.steps, t.grid]));
    if (tablesSent.get(doc) === signature) continue;
    tablesSent.set(doc, signature);
    viewOf(doc)!.setTables(mine);
  }
  drawTablesTool();
}

function assignSoon(): void {
  if (assignTimer !== null) return;
  assignTimer = window.setTimeout(() => {
    assignTimer = null;
    assignTables();
  }, 50);
}

let refreshTimer: number | null = null;
function refreshTablesSoon(): void {
  if (refreshTimer !== null) window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null;
    void fetchTables().then(
      (found) => {
        tables = found;
        assignTables();
      },
      () => undefined, // the server is away: the cells stay as they are
    );
  }, 120);
}

/** The toolbar's word on the front document's tables: Run tables, when one is not up to date. */
function drawTablesTool(): void {
  const view = current ? viewOf(current) : undefined;
  const waiting = view ? view.tables().filter((t) => t.state === "outOfDate" || t.state === "notRun" || t.state === "notRunSinceOpening") : [];
  const stale = waiting.filter((t) => t.state === "outOfDate").length;
  clear(
    tablesHost,
    waiting.length
      ? button(stale ? `Run tables: ${stale} out of date` : `Run tables: ${waiting.length} not run`, () => void view!.runOutOfDate().catch((e: Error) => toast(e.message, "error")), {
          icon: "play",
          class: stale ? "wb-tables-stale" : "",
          title: `Run each table's cell that is not up to date: ${waiting.map((t) => t.name).join(", ")}`,
        })
      : null,
  );
}

// ===== Streamlit: live cells, a Streamlit app's canvas, projects =====

const DATA_NOTEBOOK = "data.ipynb";
const APP_ENDING = ".stapp.json";
const isData = (doc: Doc): boolean => !!doc.notebook && !!doc.path && baseName(doc.path).toLowerCase() === DATA_NOTEBOOK;

/** A notebook's or script's own app: the server hears its Python cells as they are typed, says which
 *  call Streamlit (they show live), and gives them to the canvases that link to them. */
function attachStreamlit(doc: Doc): void {
  doc.streamlit = new StreamlitDoc(
    {
      title: () => doc.title,
      path: () => doc.path,
      python: () => doc.python,
      kernel: () => doc.kernel?.id ?? null,
      window: WINDOW_ID,
      cells: () => viewOf(doc)?.pieces() ?? [],
      unsaved: () => doc.dirty,
      // A project's data.ipynb is exported as data.py: the server needs every cell of it.
      every: () => (isData(doc) ? doc.notebook!.everyCells() : null),
    },
    () => viewOf(doc)?.drawPieces(),
  );
}

/** Every open notebook and script has told the server its cells as they stand (before Play). */
const settleDocuments = async (): Promise<void> => {
  await Promise.all(docs.map((d) => d.streamlit?.sync().catch(() => null)));
};

/** Run or refresh a document's live cells (false: the app did not start; its cells say why). */
async function runApp(doc: Doc): Promise<boolean> {
  if (!doc.streamlit) return false;
  const state = await doc.streamlit.run();
  if (state.problem?.kind === "failed") toast(problemText(state.problem), "error");
  return state.running && !state.problem;
}

async function installStreamlit(doc: Doc): Promise<void> {
  if (!doc.streamlit) return;
  toast("Installing Streamlit into this document's Python…");
  try {
    await doc.streamlit.install();
  } catch (e) {
    toast((e as Error).message, "error");
  }
}

const streamlitHost = (doc: Doc): StreamlitHost => ({
  state: () => doc.streamlit?.state ?? null,
  changed: () => doc.streamlit?.syncSoon(),
  isLive: (cell) => doc.streamlit?.isLive(cell) ?? Promise.resolve(false),
  run: () => runApp(doc),
  install: () => void installStreamlit(doc),
  link: () => ({ document: doc.path, title: doc.title }),
});

/** A Streamlit app: its canvas as a document of its own. */
function openApp(path: string | null, pages: SavedPage[], modified: number | null): Doc {
  const doc = makeDoc("app", path ? baseName(path) : `Untitled app ${counter + 1}`, path, modified);
  doc.canvas = canvasView(pages, {
    title: () => (doc.path ? baseName(doc.path).slice(0, -APP_ENDING.length) : doc.title),
    path: () => doc.path,
    window: WINDOW_ID,
    changed: (dirty) => {
      if (doc.dirty === dirty) return;
      doc.dirty = dirty;
      drawTabs();
      remember();
    },
    settle: settleDocuments,
    chooseFolder: () => chooseFile({ title: "Export: choose the app's folder", mode: "folder", start: folderOf(doc.path) }),
    chooseZip: () => chooseFile({ title: "Save as", mode: "save", start: folderOf(doc.path), name: `${doc.path ? baseName(doc.path).slice(0, -APP_ENDING.length) : "app"}.zip` }),
    save: () => save(doc),
  });
  doc.element.append(doc.canvas.element);
  show(doc);
  return doc;
}

const canvas = (): CanvasView => {
  if (!current?.canvas) throw new Error("No Streamlit app is in front.");
  return current.canvas;
};

// ----- projects: a folder that starts with data.ipynb (docs/ideas.md, 2026-11-15) -----

interface ProjectFiles {
  folder: string;
  name: string;
  data: string | null;
  files: string[];
}
let project: ProjectFiles | null = null;

/** A project's files as tabs: data.ipynb first (and in front), then the app's canvas, then the rest. */
async function showProject(found: ProjectFiles): Promise<ProjectFiles> {
  project = found;
  for (const path of found.files) await open(path);
  const front = docs.find((d) => d.path === found.data) ?? docs.find((d) => d.path === found.files[0]);
  if (front) show(front);
  drawTabs();
  return found;
}

async function openProject(folder?: string): Promise<ProjectFiles | null> {
  const chosen = folder ?? (await chooseFile({ title: "Open project: choose its folder", mode: "folder", start: current?.path ?? homeFolder }));
  if (!chosen) return null;
  return showProject(await api<ProjectFiles>("/projects/open", "POST", { folder: chosen }));
}

async function newProject(folder?: string, name?: string, notebooks: string[] = [], app = true): Promise<ProjectFiles | null> {
  let where = folder;
  let called = name;
  if (!where || !called) {
    // The chooser's save mode names a new folder: where it goes, and what it is called.
    const path = await chooseFile({ title: "New project: its folder", mode: "save", start: current?.path ?? homeFolder, name: "project" });
    if (!path) return null;
    const at = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
    where = path.slice(0, at) || "/";
    called = path.slice(at + 1);
  }
  return showProject(await api<ProjectFiles>("/projects", "POST", { folder: where, name: called, notebooks, app }));
}

/** Export data.py: written again from the project's data.ipynb, as it stands here. */
async function exportData(): Promise<unknown> {
  const data = docs.find(isData);
  const folder = data?.path ? folderOf(data.path) : project?.folder;
  if (!folder) throw new Error("No project is open (a folder with a data.ipynb).");
  await settleDocuments();
  const done = await api<{ path: string; names: string[]; fill_in: string[]; skipped: string[] }>("/projects/export-data", "POST", { folder });
  for (const said of done.skipped) toast(said);
  if (done.fill_in.length) toast(`data.py cannot read ${done.fill_in.join(", ")} again: add the code that reads it to data.ipynb.`, "error");
  return done;
}

function projectMenu(anchor: HTMLElement): void {
  document.querySelector(".menu")?.remove();
  const guarded = (act: () => Promise<unknown>) => (): void => void act().catch((e: Error) => toast(e.message, "error"));
  const item = (text: string, act: () => void, off = false): HTMLElement => h("button", { type: "button", role: "menuitem", disabled: off, onclick: () => { menu.remove(); act(); } }, text);
  const menu = h(
    "div",
    { class: "menu", role: "menu", "aria-label": "Project" },
    item("New project…", guarded(() => newProject())),
    item("Open project…", guarded(() => openProject())),
    item("Export data.py", guarded(exportData), !docs.some(isData) && !project),
  );
  document.body.append(menu);
  const box = anchor.getBoundingClientRect();
  menu.style.top = `${box.bottom + 4}px`;
  menu.style.left = `${Math.max(8, Math.min(box.left, innerWidth - menu.offsetWidth - 8))}px`;
  (menu.querySelector("button:not(:disabled)") as HTMLButtonElement | null)?.focus();
  setTimeout(() => document.addEventListener("mousedown", function away(e) { if (!menu.contains(e.target as Node)) { menu.remove(); document.removeEventListener("mousedown", away); } }));
  menu.addEventListener("keydown", (e) => { if (e.key === "Escape") { menu.remove(); anchor.focus(); } });
}

/** Move a saved document into a Workbench window of its own (so a canvas can sit on another screen). */
async function popOut(doc: Doc): Promise<{ path: string }> {
  if (!doc.path || doc.dirty) {
    if (!(await save(doc)) || !doc.path) throw new Error("Save the document first: its own window opens it from its file.");
  }
  const path = doc.path;
  const hash = new URLSearchParams({ token, open: path, fresh: "1" }).toString();
  const opened = window.open(`/workbench#${hash}`, `swissarmygrid-workbench-${Date.now()}`, "popup,width=1200,height=800");
  if (!opened) throw new Error("The browser blocked the new window. Allow pop-ups for this address.");
  close(doc);
  return { path };
}

const restoreSteps = (grid: string, steps: unknown[]): void => void api(`/grids/${encodeURIComponent(grid)}/steps`, "POST", { steps }).catch((e: Error) => toast(e.message, "error"));

function makeDoc(kind: Doc["kind"], title: string, path: string | null, modified: number | null): Doc {
  const doc: Doc = { id: ++counter, kind, title, path, modified, dirty: false, kernel: null, python: null, element: h("div", { class: `wb-doc-body kind-${kind}` }) };
  if (kind === "notebook" || kind === "script") {
    const kernel = new Kernel(() => doc.path, () => doc.python);
    doc.kernel = kernel;
    kernel.onState(() => {
      if (doc === current) {
        drawToolbar();
        drawStatus();
      }
      assignSoon(); // a started kernel has its id: the tables it sends belong to this document
    });
    doc.console = consoleView(kernel, () => effectiveTheme(), {
      complete: pythonCompleter(kernel, names),
      help: (code, offset) => kernel.help(code, offset),
      f5: () => void runPrimary(doc),
      ran: () => useConsole(doc),
      // A script's runs mark its lines; a line typed in the console has only the panel's own fixes.
      errors: (origin) =>
        doc.script?.errorHooks(origin) ?? {
          fix: (fix) => void (pageFix(doc)(fix) || doc.console?.note("Not applied here.")),
          goTo: () => false,
          openGrid: (name) => void openGrid(doc, name),
          openResult: (n, name) => void openResult(doc, n, name),
        },
    });
  }
  docs.push(doc);
  return doc;
}

/** The fixes only the window can make: install into the document's Python (in its console). */
const pageFix = (doc: Doc) => (fix: Fix): boolean => {
  if (fix.kind === "install" && fix.package && doc.console) {
    if (!/^[A-Za-z0-9._\-[\],=<>!~ ]+$/.test(fix.package)) return false;
    void doc.console.run({ code: `%pip install ${fix.package}` }, `%pip install ${fix.package}`).then(() => doc.console?.note(`Restart if ${fix.package} was already imported.`));
    return true;
  }
  return false;
};

/** A cell's table result as a grid: the kernel still holds it as Out[n]. */
async function openResult(doc: Doc, count: number, name?: string): Promise<void> {
  if (!doc.kernel?.id) return;
  try {
    const opened = await api<{ dataset: string }>(`/workbench/kernels/${doc.kernel.id}/grid`, "POST", name ? { output: count, name } : { output: count });
    toast(`${opened.dataset} is open as a grid.`);
  } catch (e) {
    toast((e as Error).message, "error");
  }
}

async function openGrid(doc: Doc, name: string): Promise<void> {
  if (!doc.kernel?.id) return;
  try {
    await api(`/workbench/kernels/${doc.kernel.id}/grid`, "POST", { name });
    toast(`${name} is open as a grid.`);
  } catch (e) {
    toast((e as Error).message, "error");
  }
}

/** A frame in another file: open it in the Workbench at that line. */
async function openAt(path: string, line: number): Promise<void> {
  await open(path);
  const doc = docs.find((d) => d.path === path);
  if (doc?.script) setTimeout(() => doc.script?.reveal(line), 300);
}

/** F5 and the toolbar's main Run: the file, or every cell. */
async function runPrimary(doc: Doc | null): Promise<void> {
  if (doc?.script) await doc.script.runFile();
  else if (doc?.notebook) await doc.notebook.runAll();
}

function focusSource(): void {
  if (current?.script) current.script.focus();
  else if (current?.notebook) current.notebook.commandMode();
  else (docHost.querySelector("button, input, [tabindex]") as HTMLElement | null)?.focus();
}

function focusConsole(): void {
  current?.console?.focus();
}

async function showHelp(): Promise<void> {
  const text = (await (current?.script?.helpAtCursor() ?? current?.notebook?.helpAtCursor())) ?? "";
  layout.help("Help", text);
}

const markChanged = (doc: Doc) => (): void => {
  if (!doc.dirty) {
    doc.dirty = true;
    drawTabs();
  }
  remember();
};

function openNotebook(path: string | null, cells: CellData[], modified: number | null, nextCell?: number): Doc {
  const doc = makeDoc("notebook", path ? baseName(path) : `Untitled notebook ${counter + 1}`, path, modified);
  attachStreamlit(doc);
  doc.notebook = notebookView(cells, doc.kernel!, () => connectionNames, () => effectiveTheme(), markChanged(doc), () => bladeNames, () => codeNames, {
    ...hooks,
    fix: pageFix(doc),
    openGrid: (name) => void openGrid(doc, name),
    openResult: (n, name) => void openResult(doc, n, name),
    nextCell,
    opened: cells.length > 0, // from a file or a reload: its tables' cells have not run since
    restoreSteps,
    tablesChanged: () => doc === current && drawTablesTool(),
    streamlit: streamlitHost(doc),
    datasets: () => datasetNames,
  });
  doc.element.append(doc.notebook.element);
  show(doc);
  doc.streamlit!.syncSoon(); // the server knows its cells: the live ones say their state
  // A new notebook is for typing: the cursor waits in its first cell.
  if (!path && !cells.length) doc.notebook.select(0, true);
  return doc;
}

function openScript(path: string | null, text: string, modified: number | null): Doc {
  const doc = makeDoc("script", path ? baseName(path) : `Untitled script ${counter + 1}`, path, modified);
  const file = {
    path: () => doc.path,
    // Run file runs what is on disk: a changed file with a path is saved first (an untitled one runs
    // from a private copy).
    saveFirst: async (): Promise<boolean> => (!doc.path || !doc.dirty ? true : save(doc)),
  };
  doc.script = scriptView(text, doc.kernel!, doc.console!, () => effectiveTheme(), markChanged(doc), names, file, { ...hooks, fix: pageFix(doc), openFile: (path, line) => void openAt(path, line), openGrid: (name) => void openGrid(doc, name), openResult: (n, name) => void openResult(doc, n, name), tablesChanged: () => doc === current && drawTablesTool(), streamlit: streamlitHost(doc) });
  attachStreamlit(doc);
  doc.element.append(doc.script.element);
  show(doc);
  doc.streamlit!.syncSoon();
  return doc;
}

/** A notebook's console in use: at its size (and from then on, for this notebook). */
function useConsole(doc: Doc): void {
  doc.consoleUsed = true;
  if (doc === current) layout.compact(false);
}

function show(doc: Doc): void {
  current = doc;
  // A notebook's cells hold their own outputs: its console is a title bar until it is used.
  layout.compact((doc.kind === "notebook" && !doc.consoleUsed) || doc.kind === "app");
  variables.show(doc.kernel);
  docHost.replaceChildren(doc.element);
  layout.console.replaceChildren(doc.console?.element ?? h("p", { class: "hint wb-pane-empty" }, "No console"));
  cursor = { line: 1, column: 1 };
  drawTabs();
  drawToolbar();
  drawStatus();
  document.title = `${doc.title} · Workbench`;
  remember();
  assignSoon(); // a table with no document yet goes to the one in front
}

function close(doc: Doc): void {
  if (doc.dirty && !confirm(`${doc.title} has changes that are not saved. Close it anyway?`)) return;
  doc.kernel?.stop();
  doc.streamlit?.close(); // its Streamlit process and temporary folder go with it
  doc.canvas?.close();
  docs.splice(docs.indexOf(doc), 1);
  tablesSent.delete(doc);
  remember();
  if (doc.kind === "blade") editingBlade = false;
  if (current === doc) {
    const next = docs[docs.length - 1];
    if (next) show(next);
    else showWelcome();
  } else drawTabs();
}

function drawTabs(): void {
  const tab = (doc: Doc): HTMLElement => {
    const item = h(
      "div",
      { class: `tab-item ${doc === current ? "active" : ""}`, role: "tab", "aria-selected": String(doc === current), tabindex: doc === current ? "0" : "-1", title: doc.path ?? doc.title, onclick: () => show(doc) },
      h("span", { class: "tab-label" }, `${doc.dirty ? "● " : ""}${doc.title}`),
      doc === current && (doc.notebook || doc.script || doc.canvas)
        ? button(`Open ${doc.title} in its own window`, (e) => { e.stopPropagation(); void popOut(doc).catch((error: Error) => toast(error.message, "error")); }, { icon: "popout", iconOnly: true, class: "tab-close wb-pop-out" })
        : null,
      button(`Close ${doc.title}`, (e) => { e.stopPropagation(); close(doc); }, { icon: "close", iconOnly: true, class: "tab-close" }),
    );
    if (doc.canvas) {
      // A cell dropped on a Streamlit app's tab goes to the end of its current page.
      item.addEventListener("dragover", (e) => {
        if (!e.dataTransfer?.types.includes(CELL_DRAG)) return;
        e.preventDefault();
        item.classList.add("drop");
      });
      item.addEventListener("dragleave", () => item.classList.remove("drop"));
      item.addEventListener("drop", (e) => {
        item.classList.remove("drop");
        const link = draggedLink(e.dataTransfer);
        if (!link) return;
        e.preventDefault();
        void doc.canvas!.place(link);
      });
    }
    return item;
  };
  clear(tabs, project ? h("span", { class: "wb-project", title: project.folder }, project.name) : null, ...docs.map(tab));
}

// ===== files =====

async function open(path?: string): Promise<void> {
  const chosen = path ?? (await chooseFile({ title: "Open", mode: "file", suffixes: [".ipynb", ".py", APP_ENDING], start: current?.path ?? homeFolder }));
  if (!chosen) return;
  const already = docs.find((d) => d.path === chosen);
  if (already) return show(already);
  try {
    const found = await api<{ path: string; kind: "notebook" | "script" | "app"; modified: number; cells?: CellData[]; text?: string; python: string | null; next_cell?: number; pages?: SavedPage[] }>("/workbench/open", "POST", { path: chosen });
    if (found.kind === "notebook") openNotebook(found.path, found.cells ?? [], found.modified, found.next_cell);
    else if (found.kind === "app") openApp(found.path, found.pages ?? [], found.modified);
    else openScript(found.path, found.text ?? "", found.modified);
    // Its own environment, as remembered (or the .venv beside it): the picker shows it, Run uses it.
    if (found.python && current) {
      current.python = found.python;
      if (!pythons.some((p) => p.python === found.python)) pythons.push({ python: found.python, version: "", ipykernel: true, swissarmygrid: true });
      drawToolbar();
    }
    void refreshHome();
  } catch (e) {
    toast((e as Error).message, "error");
  }
}

/** Save a document (true: it is saved). */
async function save(doc: Doc | null, as = false): Promise<boolean> {
  if (!doc || (doc.kind !== "notebook" && doc.kind !== "script" && doc.kind !== "app")) return false;
  let path = doc.path;
  if (!path || as) {
    const suggested = doc.path ? baseName(doc.path) : doc.kind === "notebook" ? "analysis.ipynb" : doc.kind === "app" ? `app${APP_ENDING}` : "script.py";
    path = await chooseFile({ title: doc.kind === "notebook" ? "Save notebook" : doc.kind === "app" ? "Save Streamlit app" : "Save script", mode: "save", start: doc.path ?? project?.folder ?? homeFolder, name: suggested });
    if (!path) return false;
    const ending = doc.kind === "notebook" ? ".ipynb" : doc.kind === "app" ? APP_ENDING : ".py";
    if (!path.toLowerCase().endsWith(ending)) path = doc.kind === "app" ? path.replace(/(\.stapp)?(\.json)?$/i, "") + ending : path + ending;
  }
  // A notebook keeps the next cell number with it, so a deleted cell's number is never given again.
  // A Streamlit app's file holds its pages: blocks, links and places, no code.
  const body = doc.kind === "notebook" ? { cells: doc.notebook!.cells(), next_cell: doc.notebook!.nextCell() } : doc.kind === "app" ? { pages: doc.canvas!.pages() } : { text: doc.script!.text() };
  const send = async (force: boolean): Promise<void> => {
    const saved = await api<{ path: string; modified: number }>("/workbench/save", "POST", { path, ...body, modified: as ? null : doc.modified, force });
    const first = doc.path === null;
    doc.path = saved.path;
    doc.modified = saved.modified;
    if (first && doc.python) void api("/workbench/environment", "POST", { path: saved.path, python: doc.python }).catch(() => undefined);
    doc.title = baseName(saved.path);
    doc.dirty = false;
    doc.canvas?.saved(saved.path); // the server knows the app's file: its links are relative to it
    doc.streamlit?.syncSoon(); // a canvas can link to a document that has a file
    drawTabs(); // the tab's dot goes: that is the word for "saved"
    remember();
    void refreshHome();
  };
  try {
    await send(false);
    return true;
  } catch (e) {
    if (e instanceof ApiError && e.status === 409 && confirm(`${e.message}\n\nReplace the file on disk with this one?`)) {
      return send(true).then(
        () => true,
        (err: Error) => (toast(err.message, "error"), false),
      );
    }
    toast((e as Error).message, "error");
    return false;
  }
}

let recent: { path: string; exists: boolean }[] = [];
async function refreshHome(): Promise<void> {
  try {
    const home = await api<{ folder: string; recent: { path: string; exists: boolean }[] }>("/workbench/home");
    homeFolder = home.folder;
    recent = home.recent;
  } catch {
    /* the server will say so on the next action */
  }
}

function recentMenu(anchor: HTMLElement): void {
  document.querySelector(".menu")?.remove();
  const box = anchor.getBoundingClientRect();
  const menu = h(
    "div",
    { class: "menu", role: "menu", "aria-label": "Recent files" },
    ...(recent.length
      ? recent.map((r) => h("button", { type: "button", role: "menuitem", disabled: !r.exists, title: r.exists ? r.path : `${r.path} (missing)`, onclick: () => { menu.remove(); void open(r.path); } }, baseName(r.path), h("span", { class: "hint" }, `  ${r.path}`)))
      : [h("div", { class: "menu-label" }, "No recent files")]),
  );
  document.body.append(menu);
  menu.style.top = `${box.bottom + 4}px`;
  menu.style.left = `${Math.min(box.left, innerWidth - menu.offsetWidth - 8)}px`;
  (menu.querySelector("button:not(:disabled)") as HTMLButtonElement | null)?.focus();
  setTimeout(() => document.addEventListener("mousedown", function away(e) { if (!menu.contains(e.target as Node)) { menu.remove(); document.removeEventListener("mousedown", away); } }));
  menu.addEventListener("keydown", (e) => { if (e.key === "Escape") menu.remove(); });
}

// ===== toolbar =====

// A kernel that is ready says nothing (principle 7.9): only the states that explain a wait, or need a click.
const STATE_WORDS: Record<string, string> = { off: "not started", starting: "starting…", busy: "running…" };

function folderOf(path: string | null): string {
  if (!path) return homeFolder;
  const at = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return at > 0 ? path.slice(0, at) : homeFolder;
}

/** Run in another Python from the next Run on (a running kernel is stopped first). */
function useEnvironment(doc: Doc, python: string): void {
  doc.python = python;
  if (!pythons.some((p) => p.python === python)) pythons.push({ python, version: "", ipykernel: true, swissarmygrid: true });
  if (doc.kernel?.id) {
    doc.kernel.stop();
    toast("Kernel stopped");
  }
  if (doc.path) void api("/workbench/environment", "POST", { path: doc.path, python }).catch((e: Error) => toast(e.message, "error"));
  drawToolbar();
}

function pythonPicker(doc: Doc): HTMLElement {
  const select = h("select", { "aria-label": "Environment", title: "Environment" }) as HTMLSelectElement;
  const own = pythons[0];
  const label = (p: PythonChoice): string => {
    // An environment by its last two folders (project/.venv), the whole path in the option's title.
    const folder = p.python.replace(/[\\/](bin[\\/]python[\d.]*|Scripts[\\/]python\.exe)$/i, "").split(/[\\/]/).filter(Boolean);
    const where = p === own ? "This app's Python" : folder.slice(-2).join("/");
    return `${where}${p.version ? ` (${p.version})` : ""}${p.ipykernel ? "" : ", no ipykernel"}`;
  };
  for (const p of pythons) select.append(h("option", { value: p.python, title: p.python, selected: (doc.python ?? own?.python) === p.python }, label(p)));
  select.append(h("option", { value: "__new" }, "New environment…"), h("option", { value: "__other" }, "Another Python…"));
  select.addEventListener("change", async () => {
    if (select.value === "__new") {
      const made = await newEnvironment({ folder: folderOf(doc.path), document: doc.path, appVersion: own?.version ?? "" });
      if (made) {
        useEnvironment(doc, made.python);
        if (made.imports.length && doc.notebook) doc.notebook.add("code", made.imports.join("\n"), true);
      }
      drawToolbar();
      return;
    }
    if (select.value === "__other") {
      const path = await chooseFile({ title: "Choose a Python", mode: "file", start: folderOf(doc.path) });
      if (path) useEnvironment(doc, path);
      drawToolbar();
      return;
    }
    useEnvironment(doc, select.value);
  });
  return select;
}

function drawToolbar(): void {
  const doc = current;
  const file = [
    button("Side bar", () => {
      layout.toggle("rail");
      drawToolbar();
    }, { icon: "panel", iconOnly: true, pressed: layout.state().rail, title: "Side bar (Ctrl+B)" }),
    button("New notebook", () => openNotebook(null, [], null), { icon: "plus" }),
    button("New script", () => openScript(null, "", null), { icon: "code" }),
    button("New app", () => openApp(null, [], null), { icon: "bucket", class: "wb-new-app", title: "New Streamlit app: a canvas of pages, its blocks linked to Python cells" }),
    button("Project", (e) => projectMenu(e.currentTarget as HTMLElement), { icon: "more", class: "wb-project-menu", title: "Project: a folder that starts with data.ipynb" }),
    button("Open…", () => void open(), { icon: "folder", title: "Open (Ctrl+O)" }),
    button("Recent", (e) => recentMenu(e.currentTarget as HTMLElement), { icon: "more" }),
    button("Save", () => void save(current), { icon: "save", title: "Save (Ctrl+S)" }),
  ];
  const palette = button("Commands", () => openPalette(), { icon: "steps", title: "Commands (Ctrl+Shift+P)" });
  const right = button("Variables", () => {
    if (layout.toggle("right")) void variables.refresh();
    drawToolbar();
  }, { icon: "columns", pressed: layout.state().right });
  if (!doc || (doc.kind !== "notebook" && doc.kind !== "script")) {
    clear(toolbar, h("div", { class: "ribbon-tools" }, ...file), h("div", { class: "ribbon-tools" }, right, palette));
    return;
  }
  const kernel = doc.kernel!;
  const run =
    doc.kind === "notebook"
      ? [
          button("Python", () => doc.notebook!.add("code"), { icon: "plus", title: "Add Python cell (B)" }),
          button("SQL", () => doc.notebook!.add("sql"), { icon: "sql", title: "Add SQL cell" }),
          button("DAX", () => doc.notebook!.add("dax"), { icon: "group", title: "Add DAX cell: a query on a Power BI workspace's dataset" }),
          button("HTML", () => doc.notebook!.add("html"), { icon: "image", title: "Add HTML cell: a design drawn from its HTML" }),
          button("Markdown", () => doc.notebook!.add("markdown"), { icon: "edit", title: "Add Markdown cell" }),
          button("Run all", () => void doc.notebook!.runAll(), { icon: "play", class: "primary", title: "Run all (F5)" }),
        ]
      : [
          button("Run file", () => void doc.script!.runFile(), { icon: "play", class: "primary", title: "Run file (F5)" }),
          button("Run statement", () => void doc.script!.runSelection(), { icon: "play", title: "Run statement (Ctrl+Enter)" }),
          button("DAX", () => void doc.script!.addDax(datasetNames[0] ?? ""), { icon: "group", title: "Add DAX cell: a query on a Power BI workspace's dataset" }),
          button("HTML", () => void doc.script!.addHtml(), { icon: "image", title: "Add HTML cell: a design drawn from its HTML" }),
        ];
  clear(
    toolbar,
    h("div", { class: "ribbon-tools" }, ...file),
    h(
      "div",
      { class: "ribbon-tools" },
      ...run,
      button("Interrupt", () => void kernel.interrupt(), { icon: "stop" }),
      button("Restart", () => void restartKernel(kernel), { icon: "back" }),
      pythonPicker(doc),
      tablesHost,
      right,
      palette,
    ),
  );
  drawTablesTool();
}

async function restartKernel(kernel: Kernel): Promise<boolean> {
  const did = await kernel.restart();
  toast(did ? "Restarted" : "Nothing to restart");
  return did;
}

/** The status bar: the kernel while it is not ready, the runs waiting, an environment of the notebook's
 *  own, the cursor. What is as expected (a ready kernel, this app's Python, the kind of file) is not said. */
function drawStatus(): void {
  const doc = current;
  const kernel = doc?.kernel;
  const python = doc?.python ?? pythons[0]?.python ?? "";
  const env = !doc?.python || doc.python === pythons[0]?.python ? "" : python.replace(/[\\/](bin[\\/]python[\d.]*|Scripts[\\/]python\.exe)$/i, "").split(/[\\/]/).filter(Boolean).slice(-2).join("/");
  clear(
    layout.status,
    kernel
      ? STATE_WORDS[kernel.state]
        ? h("span", { class: `wb-state ${kernel.state}` }, h("span", { class: "wb-dot", "aria-hidden": "true" }), `Kernel: ${STATE_WORDS[kernel.state]}`, kernel.running > 1 ? ` (${kernel.running - 1} waiting)` : "")
        : null
      : doc?.kind === "app"
        ? null
        : h("span", { class: "hint" }, doc ? "No kernel" : "Nothing open"),
    kernel && env ? h("span", { title: python }, env) : null,
    doc?.kind === "script" || doc?.kind === "notebook" ? h("span", {}, `Line ${cursor.line}, column ${cursor.column}`) : null,
    doc?.kind === "blade" || doc?.kind === "table" ? h("span", {}, doc.kind === "blade" ? "Blade" : "Explorer") : null,
    doc?.kind === "app" ? h("span", {}, "Streamlit app") : null,
  );
}

// ===== the left panel: connections, blades, the data explorer =====

function bladeDoc(name: string | null): void {
  const doc = makeDoc("blade", name ?? "New blade", null, null);
  editingBlade = true;
  const done = (): void => { editingBlade = false; close(doc); };
  const saved = (savedName: string): void => { editingBlade = false; rail.bladeSaved(savedName); void loadConnections(); };
  if (name !== null) void editBlade(doc.element, name, null, "other" as BladeKind, saved, done);
  else
    void showTemplatePicker(doc.element, (template, kind) => {
      void editBlade(doc.element, null, template, kind, saved, done);
    });
  show(doc);
}

const rail = mountRail({
  bladesHost: document.getElementById("blades") as HTMLElement,
  catalogHost: document.getElementById("catalog") as HTMLElement,
  editBlade: bladeDoc,
  isEditing: () => editingBlade,
  showTable: (view) => {
    let doc = docs.find((d) => d.kind === "table");
    if (!doc) doc = makeDoc("table", "Explorer", null, null);
    doc.title = view.table;
    clear(doc.element, ...tableDetails(view));
    show(doc);
  },
  connectionsByName: true,
  showSchema: (label, catalog, dialect, schema, note) => {
    let doc = docs.find((d) => d.kind === "table");
    if (!doc) doc = makeDoc("table", "Explorer", null, null);
    doc.title = label;
    clear(doc.element, ...schemaDetails(label, catalog, dialect, schema, note));
    show(doc);
  },
});

// ===== restore after a reload =====

interface Remembered {
  kind: "notebook" | "script" | "app";
  path: string | null;
  modified: number | null;
  dirty: boolean;
  python: string | null;
  text?: string;
  cells?: CellData[];
  next_cell?: number;
  pages?: SavedPage[];
}
const SESSION_KEY = "workbench-documents";
let rememberTimer: number | null = null;

/** Keep the open documents in this window's session storage (the browser's, never a file), so a
 *  reload or a crashed tab brings them back with their unsaved text. */
function rememberNow(): void {
  if (rememberTimer !== null) window.clearTimeout(rememberTimer);
  rememberTimer = null;
  const kept = (withOutputs: boolean): Remembered[] =>
    docs
      .filter((d) => d.notebook || d.script || d.canvas)
      .map((d) => ({
        kind: d.notebook ? "notebook" : d.canvas ? "app" : "script",
        path: d.path,
        modified: d.modified,
        dirty: d.dirty,
        python: d.python,
        // A saved document comes back from its file; only changed ones keep their text here.
        ...(d.dirty || !d.path ? (d.notebook ? { cells: d.notebook.cells().map((c) => (withOutputs ? c : { ...c, outputs: [] })), next_cell: d.notebook.nextCell() } : d.canvas ? { pages: d.canvas.pages() } : { text: d.script!.text() }) : {}),
      }));
  const at = current ? docs.filter((d) => d.notebook || d.script || d.canvas).indexOf(current) : -1;
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ docs: kept(true), current: at, project }));
  } catch {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({ docs: kept(false), current: at, project })); // too big with outputs
    } catch {
      /* storage refused: a reload starts empty, as before */
    }
  }
}

function remember(): void {
  if (rememberTimer === null) rememberTimer = window.setTimeout(rememberNow, 800);
}

/** The documents open before a reload (false: there were none). */
async function restore(): Promise<boolean> {
  type Saved = { docs: Remembered[]; current: number; project?: ProjectFiles | null } | null;
  const read = (): Saved => {
    try {
      return JSON.parse(sessionStorage.getItem(SESSION_KEY) ?? "null") as Saved;
    } catch {
      return null;
    }
  };
  const saved = read();
  if (!saved?.docs?.length) return false;
  project = saved.project ?? null;
  const opened: Doc[] = [];
  for (const r of saved.docs) {
    if (r.path && !r.dirty) {
      await open(r.path); // fresh from its file
      const reopened = docs.find((d) => d.path === r.path);
      if (reopened) opened.push(reopened);
      continue;
    }
    const doc = r.kind === "notebook" ? openNotebook(r.path, r.cells ?? [], r.modified, r.next_cell) : r.kind === "app" ? openApp(r.path, r.pages ?? [], r.modified) : openScript(r.path, r.text ?? "", r.modified);
    doc.python = r.python;
    if (r.python && !pythons.some((p) => p.python === r.python)) pythons.push({ python: r.python, version: "", ipykernel: true, swissarmygrid: true });
    doc.dirty = r.dirty;
    opened.push(doc);
  }
  const back = opened[saved.current] ?? opened[opened.length - 1];
  if (back) show(back);
  drawTabs();
  return opened.length > 0;
}

// ===== start =====

function showWelcome(): void {
  current = null;
  variables.show(null);
  layout.console.replaceChildren();
  drawTabs();
  drawToolbar();
  drawStatus();
  document.title = "Workbench";
  clear(
    docHost,
    h(
      "div",
      { class: "wb-welcome" },
      h("h1", {}, "Workbench"),
      h("div", { class: "row-actions" }, button("New notebook", () => openNotebook(null, [], null), { icon: "plus", class: "primary" }), button("New script", () => openScript(null, "", null), { icon: "code" }), button("New app", () => openApp(null, [], null), { icon: "bucket" }), button("New project…", () => void newProject().catch((e: Error) => toast(e.message, "error")), { icon: "plus" }), button("Open project…", () => void openProject().catch((e: Error) => toast(e.message, "error")), { icon: "folder" }), button("Open…", () => void open(), { icon: "folder" })),
      recent.length ? h("h3", {}, "Recent") : null,
      recent.length ? h("ul", { class: "wb-recent" }, ...recent.map((r) => h("li", {}, h("button", { type: "button", class: "link", disabled: !r.exists, onclick: () => void open(r.path) }, baseName(r.path)), h("span", { class: "hint" }, ` ${r.path}`)))) : null,
    ),
  );
}

// ===== commands: the palette, the keys and the agent (workbench_window) =====

const isCode = (): boolean => !!current?.notebook || !!current?.script;
const saves = (): boolean => isCode() || !!current?.canvas;
const isCanvas = (): boolean => !!current?.canvas;
const NO_CANVAS = "no Streamlit app is in front";
const isScript = (): boolean => !!current?.script;
const isNotebook = (): boolean => !!current?.notebook;
const notebook = (): NotebookView => {
  if (!current?.notebook) throw new Error("The document in front is not a notebook.");
  return current.notebook;
};
const script = (): ScriptView => {
  if (!current?.script) throw new Error("The document in front is not a script.");
  return current.script;
};
const kernelOf = (): Kernel => {
  if (!current?.kernel) throw new Error("The document in front runs no code.");
  return current.kernel;
};
const num = (args: Record<string, unknown>, name: string): number | undefined => {
  const value = args[name];
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "number" || !Number.isInteger(value)) throw new Error(`${name} is a whole number.`);
  return value;
};
const text = (args: Record<string, unknown>, name: string): string | undefined => {
  const value = args[name];
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string") throw new Error(`${name} is text.`);
  return value;
};
/** The front document's tables: a notebook's or a script's. */
const tablesView = (): NotebookView | ScriptView => {
  const view = current ? viewOf(current) : undefined;
  if (!view) throw new Error("No notebook or script is in front.");
  return view;
};
const kindArg = (args: Record<string, unknown>): "code" | "sql" | "dax" | "html" | "markdown" => {
  const kind = text(args, "kind") ?? "code";
  if (kind !== "code" && kind !== "sql" && kind !== "dax" && kind !== "html" && kind !== "markdown") throw new Error('kind is "code", "sql", "dax", "html" or "markdown".');
  return kind;
};
const hasLive = (): boolean => !!current?.streamlit?.state?.pieces.length;
const NO_LIVE = "the document in front has no cell that calls Streamlit";
/** The front document's live cells (the Python cells that call Streamlit) as the server sees them
 *  now: for the agent. */
async function pieceReport(): Promise<unknown> {
  const doc = current!;
  const state = await doc.streamlit!.sync();
  return {
    document: doc.title,
    path: doc.path,
    app: state?.app ?? null,
    running: state?.running ?? false,
    problem: state?.problem ?? null,
    cells: (state?.pieces ?? []).map((p) => ({ number: p.cell, name: p.name, makes: p.makes, reads: p.reads, tables: p.tables, state: p.state, changed: p.changed, problem: p.problem })),
  };
}
const step = (by: 1 | -1): void => {
  if (!current || docs.length < 2) return;
  show(docs[(docs.indexOf(current) + by + docs.length) % docs.length]!);
};

/** What the window holds: for the agent's "documents" (and the palette's nothing). */
function documents(): unknown {
  return {
    documents: docs.map((d, index) => ({
      index,
      kind: d.kind,
      title: d.title,
      path: d.path,
      unsaved_changes: d.dirty,
      in_front: d === current,
      kernel: d.kernel ? { id: d.kernel.id, state: d.kernel.state, runs_waiting: Math.max(0, d.kernel.running - 1) } : null,
      python: d.python,
      selected_cell: d.notebook ? d.notebook.selected() : null,
    })),
    panes: layout.state(),
    cursor: current?.script || current?.notebook ? cursor : null,
  };
}

const COMMANDS: Command[] = [
  // File
  { id: "file.newNotebook", group: "File", title: "New notebook", run: () => void openNotebook(null, [], null) },
  { id: "file.newScript", group: "File", title: "New script", run: () => void openScript(null, "", null) },
  { id: "file.newApp", group: "File", title: "New Streamlit app", run: () => {
    const doc = openApp(null, [], null);
    return { document: doc.title };
  } },
  { id: "file.open", group: "File", title: "Open a notebook, script or Streamlit app…", keys: "Ctrl+O", args: "path: the file (without it, the file chooser opens)", run: (a) => open(text(a, "path")) },
  { id: "file.save", group: "File", title: "Save", keys: "Ctrl+S", when: saves, whyNot: "nothing that saves is in front", run: () => save(current) },
  { id: "file.saveAs", group: "File", title: "Save a copy as…", keys: "Ctrl+Shift+S", when: saves, whyNot: "nothing that saves is in front", run: () => save(current, true) },
  { id: "project.new", group: "Project", title: "New project…", args: "folder: where it goes; name: its name; notebooks: names of notebooks to make; app: false for no Streamlit app (without folder and name, the file chooser opens)", run: (a) => newProject(text(a, "folder"), text(a, "name"), Array.isArray(a.notebooks) ? (a.notebooks as string[]) : [], a.app !== false) },
  { id: "project.open", group: "Project", title: "Open project…", args: "folder: the project's folder (without it, the file chooser opens)", run: (a) => openProject(text(a, "folder")) },
  { id: "project.exportData", group: "Project", title: "Export data.py (from data.ipynb)", when: () => docs.some(isData) || !!project, whyNot: "no project is open", run: () => exportData() },
  { id: "file.close", group: "File", title: "Close the document", args: "index: a document (default: the one in front)", when: () => docs.length > 0, whyNot: "nothing is open", run: (a) => {
    const at = num(a, "index");
    const doc = at === undefined ? current : docs[at];
    if (!doc) throw new Error(`There is no document ${at}.`);
    close(doc);
  } },
  // Documents
  { id: "documents", agentOnly: true, group: "Documents", title: "What is open", run: () => documents() },
  { id: "doc.read", agentOnly: true, group: "Documents", title: "The front document's text or cells", when: isCode, whyNot: "no notebook or script is in front", run: () => (current?.notebook ? { kind: "notebook", cells: current.notebook.cells() } : { kind: "script", text: script().text() }) },
  { id: "doc.show", group: "Documents", title: "Show a document", args: "index, or path", run: (a) => {
    const at = num(a, "index");
    const path = text(a, "path");
    const doc = at !== undefined ? docs[at] : docs.find((d) => d.path === path);
    if (!doc) throw new Error("No open document matches.");
    show(doc);
  } },
  { id: "doc.popOut", group: "Documents", title: "Open the document in its own window", when: saves, whyNot: "nothing that saves is in front", run: () => popOut(current!) },
  { id: "doc.next", group: "Documents", title: "Next document", keys: "Ctrl+Alt+PageDown", run: () => step(1) },
  { id: "doc.previous", group: "Documents", title: "Previous document", keys: "Ctrl+Alt+PageUp", run: () => step(-1) },
  // Run
  { id: "run.primary", group: "Run", title: "Run the file, or every cell", keys: "F5", when: isCode, whyNot: "no notebook or script is in front", run: () => runPrimary(current) },
  { id: "run.statement", group: "Run", title: "Run the statement at the cursor, then the next", keys: "Ctrl+Enter", when: isScript, whyNot: "the document in front is not a script", run: () => script().runSelection() },
  { id: "run.toHere", group: "Run", title: "Run from the top to the cursor", when: isScript, whyNot: "the document in front is not a script", run: () => script().runToHere() },
  { id: "run.fromHere", group: "Run", title: "Run from the cursor to the end", when: isScript, whyNot: "the document in front is not a script", run: () => script().runFromHere() },
  { id: "run.cell", group: "Run", title: "Run the selected cell", keys: "Ctrl+Enter", args: "index: a cell, from 0 (default: the selected one)", when: isNotebook, whyNot: "the document in front is not a notebook", run: (a) => notebook().runCell(num(a, "index")) },
  { id: "run.above", group: "Run", title: "Run the cells above", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().runAbove() },
  { id: "run.below", group: "Run", title: "Run this cell and the ones below", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().runBelow() },
  { id: "run.interrupt", group: "Run", title: "Interrupt", when: isCode, whyNot: "no notebook or script is in front", run: () => kernelOf().interrupt() },
  { id: "run.restart", group: "Run", title: "Restart the kernel", when: isCode, whyNot: "no notebook or script is in front", run: () => restartKernel(kernelOf()) },
  // Cells
  { id: "cell.insertAbove", group: "Cell", title: "Insert a cell above", keys: "A", args: "kind: code, sql, dax, html or markdown; source", when: isNotebook, whyNot: "the document in front is not a notebook", run: (a) => notebook().insert("above", kindArg(a), text(a, "source") ?? "") },
  { id: "cell.insertBelow", group: "Cell", title: "Insert a cell below", keys: "B", args: "kind: code, sql, dax, html or markdown; source", when: isNotebook, whyNot: "the document in front is not a notebook", run: (a) => notebook().insert("below", kindArg(a), text(a, "source") ?? "") },
  { id: "cell.select", group: "Cell", title: "Select a cell", args: "index (from 0); edit: true to put the cursor in it", when: isNotebook, whyNot: "the document in front is not a notebook", run: (a) => notebook().select(num(a, "index") ?? 0, a.edit === true) },
  { id: "cell.delete", group: "Cell", title: "Delete the cell", keys: "D D", args: "index (default: the selected one)", when: isNotebook, whyNot: "the document in front is not a notebook", run: (a) => notebook().remove(num(a, "index")) },
  { id: "cell.undo", group: "Cell", title: "Undo a cell's delete or move", keys: "Z", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().undo() },
  { id: "cell.moveUp", group: "Cell", title: "Move the cell up", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().move(-1) },
  { id: "cell.moveDown", group: "Cell", title: "Move the cell down", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().move(1) },
  { id: "cell.toCode", group: "Cell", title: "Make it a Python cell", keys: "Y", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().setKind("code") },
  { id: "cell.toMarkdown", group: "Cell", title: "Make it a Markdown cell", keys: "M", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().setKind("markdown") },
  { id: "cell.toSql", group: "Cell", title: "Make it a SQL cell", keys: "S", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().setKind("sql") },
  { id: "cell.toDax", group: "Cell", title: "Make it a DAX cell", keys: "X", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().setKind("dax") },
  { id: "cell.addDax", group: "Cell", title: "Add a DAX cell", args: "dataset: a Power BI workspace's dataset, as Finance/Sales model (default: the first); source: its DAX", when: isCode, whyNot: "no notebook or script is in front", run: async (a) => {
    const source = text(a, "source") ?? "";
    const dataset = text(a, "dataset") ?? datasetNames[0] ?? "";
    if (current?.notebook) {
      current.notebook.insert("below", "dax", source);
      if (dataset) current.notebook.setConnection(dataset);
      return { document: current.title, index: current.notebook.selected(), dataset: dataset || null };
    }
    await script().addDax(dataset, source);
    return { document: current!.title, dataset: dataset || null };
  } },
  { id: "cell.toHtml", group: "Cell", title: "Make it an HTML cell", keys: "H", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().setKind("html") },
  { id: "cell.copy", group: "Cell", title: "Copy the cell (its link, for a Streamlit app's canvas)", keys: "C", args: "number: the cell's own number (default: the selected cell, or the cursor's)", when: isCode, whyNot: "no notebook or script is in front", run: (a) => (current?.notebook ? notebook().copy(num(a, "number")) : script().copy(num(a, "number"))) },
  { id: "cell.paste", group: "Cell", title: "Paste the copied cell", keys: "V", when: () => isNotebook() || isCanvas(), whyNot: "no notebook or Streamlit app is in front", run: async () => {
    const done = current?.canvas ? await current.canvas.paste() : notebook().paste();
    if (!done) throw new Error("No cell was copied.");
    return current?.canvas ? current.canvas.report() : { index: notebook().selected() };
  } },
  { id: "cell.edit", group: "Cell", title: "Edit the cell (an HTML or Markdown cell that shows as drawn)", keys: "Enter", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().editSelected() },
  { id: "cell.duplicate", group: "Cell", title: "Duplicate the cell", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().duplicate() },
  { id: "cell.clearOutput", group: "Cell", title: "Clear the cell's output", args: "index (default: the selected one)", when: isNotebook, whyNot: "the document in front is not a notebook", run: (a) => notebook().clearOutput(num(a, "index")) },
  { id: "cell.clearAll", group: "Cell", title: "Clear every output", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().clearAll() },
  { id: "cell.toggleOutput", group: "Cell", title: "Hide or show the cell's output", keys: "O", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().toggleOutput() },
  { id: "cell.goTo", group: "Cell", title: "Go to a cell by its number", args: "number: the cell's own number (as @cell7 links to it)", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
    const number = num(a, "number");
    if (number === undefined) throw new Error("Send the cell's number.");
    if (!tablesView().goTo(number)) throw new Error(`There is no cell ${number} in the document in front.`);
    return { cell: number };
  } },
  // Tables: every table open in the grid has a read-only cell in its document
  { id: "tables.list", agentOnly: true, group: "Tables", title: "The document's tables and each cell's state", when: isCode, whyNot: "no notebook or script is in front", run: () => ({ document: current!.title, tables: tablesView().tables() }) },
  { id: "tables.run", group: "Tables", title: "Run a table's cell", args: "table: the table's name", when: isCode, whyNot: "no notebook or script is in front", run: async (a) => {
    const table = text(a, "table");
    if (!table) throw new Error("Send the table's name.");
    return { table, ok: await tablesView().runTable(table) };
  } },
  { id: "tables.runOutOfDate", group: "Tables", title: "Run every table's cell that is not up to date", when: isCode, whyNot: "no notebook or script is in front", run: async () => ({ ran: await tablesView().runOutOfDate(), tables: tablesView().tables().map((t) => ({ name: t.name, state: t.state })) }) },
  { id: "tables.fold", group: "Tables", title: "Fold the Tables group (or one table)", args: "table: one table (default: the whole group)", when: isCode, whyNot: "no notebook or script is in front", run: (a) => tablesView().foldTables(true, text(a, "table")) },
  { id: "tables.unfold", group: "Tables", title: "Open the Tables group (or one table)", args: "table: one table (default: the group, one level)", when: isCode, whyNot: "no notebook or script is in front", run: (a) => tablesView().foldTables(false, text(a, "table")) },
  // HTML cells: a design drawn from the cell's HTML, its {{ names }} filled from the kernel
  { id: "html.add", group: "HTML", title: "Add an HTML cell", args: "source: its HTML; height: its pane in pixels (default: the design's own)", when: isCode, whyNot: "no notebook or script is in front", run: async (a) => {
    const source = text(a, "source") ?? "";
    const height = num(a, "height") ?? null;
    if (current?.notebook) {
      current.notebook.insert("below", "html", source);
      const added = current.notebook.htmlCells().find((c) => c.index === current!.notebook!.selected());
      if (added?.number != null && height !== null) current.notebook.resizeHtml(added.number, height);
      // With HTML it shows its design at once; an empty one waits for typing.
      if (source.trim()) current.notebook.commandMode();
      return { document: current.title, cell: current.notebook.htmlCells().find((c) => c.index === current!.notebook!.selected()) ?? null };
    }
    await script().addHtml(source, height);
    return { document: current!.title, cells: script().htmlCells() };
  } },
  { id: "html.list", agentOnly: true, group: "HTML", title: "The document's HTML cells: each one's HTML, names and state", when: isCode, whyNot: "no notebook or script is in front", run: () => ({ document: current!.title, cells: tablesView().htmlCells() }) },
  { id: "html.run", group: "HTML", title: "Run an HTML cell: fill its names and draw it", args: "number: the cell's own number (default: every one not up to date)", when: isCode, whyNot: "no notebook or script is in front", run: async (a) => ({ document: current!.title, cells: await tablesView().runHtml(num(a, "number")) }) },
  { id: "html.resize", group: "HTML", title: "Size an HTML cell's pane", args: "number: the cell's own number; height: pixels (60 to 2000; without it: the design's own height)", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
    const number = num(a, "number");
    if (number === undefined) throw new Error("Send the cell's number.");
    tablesView().resizeHtml(number, num(a, "height") ?? null);
    return { cell: number, height: num(a, "height") ?? null };
  } },
  { id: "html.edit", group: "HTML", title: "Open an HTML cell's HTML", args: "number: the cell's own number", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
    const number = num(a, "number");
    if (number === undefined) throw new Error("Send the cell's number.");
    if (current?.notebook) {
      const at = current.notebook.htmlCells().find((c) => c.number === number);
      if (!at) throw new Error(`This notebook has no HTML cell ${number}.`);
      current.notebook.select(at.index, true);
    } else script().editHtml(number);
    return { cell: number };
  } },
  // Streamlit: a Python cell that calls Streamlit shows live in its cell
  { id: "streamlit.list", agentOnly: true, group: "Streamlit", title: "The document's live cells (the ones that call Streamlit): name, makes, reads, state", when: isCode, whyNot: "no notebook or script is in front", run: () => pieceReport() },
  { id: "streamlit.run", group: "Streamlit", title: "Run the live cells (the ones that call Streamlit)", when: hasLive, whyNot: NO_LIVE, run: async () => {
    await runApp(current!);
    return pieceReport();
  } },
  { id: "streamlit.resize", group: "Streamlit", title: "Size a live cell's pane", args: "number: the cell's own number; height: pixels (60 to 2000; without it: the usual height)", when: hasLive, whyNot: NO_LIVE, run: (a) => {
    const number = num(a, "number");
    if (number === undefined) throw new Error("Send the cell's number.");
    viewOf(current!)!.resizePiece(number, num(a, "height") ?? null);
    return { cell: number, height: num(a, "height") ?? null };
  } },
  { id: "streamlit.stop", group: "Streamlit", title: "Stop the live cells' Streamlit process", when: () => !!current?.streamlit?.state?.running, whyNot: "it is not running", run: async () => {
    await current!.streamlit!.stop();
    return pieceReport();
  } },
  // A Streamlit app's canvas: blocks linked to cells; Play shows the page live in place
  { id: "canvas.state", agentOnly: true, group: "Streamlit app", title: "The canvas in front: its app, page, blocks, whether it shows the live page", when: isCanvas, whyNot: NO_CANVAS, run: () => canvas().report() },
  { id: "canvas.play", group: "Streamlit app", title: "Play: run the page and show it live", args: "page: the page to show (its id)", when: isCanvas, whyNot: NO_CANVAS, run: async (a) => {
    await canvas().play(text(a, "page"));
    return canvas().report();
  } },
  { id: "canvas.edit", group: "Streamlit app", title: "Edit: back to the blocks", when: isCanvas, whyNot: NO_CANVAS, run: () => {
    canvas().edit();
    return canvas().report();
  } },
  { id: "canvas.export", group: "Streamlit app", title: "Export an app that runs alone…", args: "folder: where it goes (without it, the file chooser opens)", when: isCanvas, whyNot: NO_CANVAS, run: (a) => canvas().exportApp(text(a, "folder")) },
  { id: "canvas.saveAs", group: "Streamlit app", title: "Save as… (the project as one zip)", args: "path: the zip (without it, the file chooser opens)", when: isCanvas, whyNot: NO_CANVAS, run: (a) => canvas().saveAs(text(a, "path")) },
  // Console
  { id: "console.focus", group: "Console", title: "Go to the console", keys: "Ctrl+2", when: isCode, whyNot: "no notebook or script is in front", run: () => layout.focus("console") },
  { id: "console.run", group: "Console", title: "Run code in the console", args: "code", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
    const code = text(a, "code");
    if (!code?.trim()) throw new Error("Send the code to run.");
    return current!.console!.run({ code }, code.split("\n").map((l, i) => `${i ? "..." : ">>>"} ${l}`).join("\n"));
  } },
  { id: "console.read", agentOnly: true, group: "Console", title: "What the console shows", when: isCode, whyNot: "no notebook or script is in front", run: () => current!.console!.text() },
  { id: "console.clear", group: "Console", title: "Clear the console", when: isCode, whyNot: "no notebook or script is in front", run: () => current!.console!.clear() },
  // View
  { id: "palette", group: "View", title: "Show every command", keys: "Ctrl+Shift+P", run: () => openPalette() },
  { id: "view.source", group: "View", title: "Go to the source", keys: "Ctrl+1", run: () => layout.focus("source") },
  { id: "view.variables", group: "View", title: "Go to Variables", keys: "Ctrl+3", run: () => layout.focus("variables") },
  { id: "view.nextPane", group: "View", title: "Next pane", keys: "F6", run: () => layout.cycle(1) },
  { id: "view.previousPane", group: "View", title: "Previous pane", keys: "Shift+F6", run: () => layout.cycle(-1) },
  { id: "view.toggleSidebar", group: "View", title: "Show or hide the side bar", keys: "Ctrl+B", run: () => { layout.toggle("rail"); drawToolbar(); } },
  { id: "view.toggleRight", group: "View", title: "Show or hide Variables", run: () => { if (layout.toggle("right")) void variables.refresh(); drawToolbar(); } },
  { id: "view.toggleConsole", group: "View", title: "Show or hide the console", run: () => layout.toggle("console") },
  { id: "view.standard", group: "View", title: "Layout: standard", run: () => { layout.setLayout("standard"); drawToolbar(); } },
  { id: "view.focus", group: "View", title: "Layout: source only", keys: "Ctrl+Shift+1", run: () => { layout.setLayout("focus"); drawToolbar(); } },
  { id: "view.wide", group: "View", title: "Layout: wide data", run: () => { layout.setLayout("wide"); drawToolbar(); } },
  { id: "view.variablesRefresh", group: "View", title: "Read the variables again", when: isCode, whyNot: "no notebook or script is in front", run: () => variables.refresh().then(() => variables.snapshot()) },
  // Help
  { id: "help.atCursor", group: "Help", title: "Help on the name at the cursor", keys: "F1", when: isCode, whyNot: "no notebook or script is in front", run: () => showHelp() },
  { id: "commands", agentOnly: true, group: "Help", title: "Every command and its arguments", run: () => allCommands().map((c) => ({ id: c.id, title: c.title, group: c.group, keys: c.keys ?? null, args: c.args ?? null, available: c.when ? c.when() : true })) },
];
registerCommands(COMMANDS);
// What is sent to the agent or the Sandbox names the document it came from.
setDocumentName(() => current?.title ?? "the Workbench");

/** The keys the window takes wherever the focus is (before an editor or the browser sees them). */
const WINDOW_KEYS: Record<string, string> = {
  F5: "run.primary",
  F1: "help.atCursor",
  F6: "view.nextPane",
  "Shift+F6": "view.previousPane",
  "Ctrl+Shift+P": "palette",
  "Ctrl+S": "file.save",
  "Ctrl+Shift+S": "file.saveAs",
  "Ctrl+O": "file.open",
  "Ctrl+B": "view.toggleSidebar",
  "Ctrl+1": "view.source",
  "Ctrl+2": "console.focus",
  "Ctrl+3": "view.variables",
  "Ctrl+Shift+1": "view.focus",
  "Ctrl+Alt+PageDown": "doc.next",
  "Ctrl+Alt+PageUp": "doc.previous",
};

function keyName(e: KeyboardEvent): string {
  const key = /^Digit\d$/.test(e.code) ? e.code.slice(5) : e.key.length === 1 ? e.key.toUpperCase() : e.key;
  return [e.ctrlKey || e.metaKey ? "Ctrl" : "", e.altKey ? "Alt" : "", e.shiftKey ? "Shift" : "", key].filter(Boolean).join("+");
}

document.addEventListener(
  "keydown",
  (e) => {
    const id = WINDOW_KEYS[keyName(e)];
    if (!id) return;
    // F5 would reload the window (stopping every kernel), F1 open the browser's help: the window's own.
    e.preventDefault();
    e.stopPropagation();
    if (document.querySelector(".wb-palette-shade") && id !== "palette") return;
    void runCommand(id).catch((error: Error) => toast(error.message, "error"));
  },
  true,
);
document.addEventListener("keydown", (e) => {
  // Ctrl+Z outside an editor: a notebook's cell delete or move comes back (inside, the editor's own undo).
  const inEditor = (e.target as HTMLElement | null)?.closest?.(".monaco-editor, input, textarea, select");
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z" && !inEditor) {
    // Never the browser's own undo: with the keyboard on a button it took back the last text typed
    // into some editor, whole and unseen (an HTML cell's edit, in the instant after Edit HTML).
    e.preventDefault();
    current?.notebook?.undo();
  }
});
window.addEventListener("beforeunload", (e) => {
  if (docs.some((d) => d.dirty)) e.preventDefault();
});
window.addEventListener("pagehide", () => {
  rememberNow();
  for (const d of docs) d.kernel?.stop(true);
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  for (const d of docs) {
    (d.notebook ?? d.script)?.setTheme(effectiveTheme());
    d.console?.setTheme(effectiveTheme());
  }
});

// The left panel's lists, and kept current: a blade or connection saved anywhere, a catalog refreshed.
void rail.loadBlades().then(() => rail.loadCatalogs());
connect((live) => {
  if (!live) return;
  refreshTablesSoon(); // what is open in the grid now
  void loadApprovals(); // an agent's request (an export, say) asks here too
  if (document.hasFocus()) tellFocus();
}, { catalog: "1", workbench: "1", window: WINDOW_ID });
// The agent's workbench_window goes to the Workbench window the user was last in.
window.addEventListener("focus", tellFocus);
onNotice((notice) => {
  handleAgentNotice(notice);
  // The agent's workbench_window: a command run here, as the palette would, and answered.
  if (notice.type === "workbench_command") void answerAgent(notice as unknown as { id: string; command: string; args?: Record<string, unknown> });
  if (notice.type === "catalogs_changed") {
    void rail.loadCatalogs();
    forgetCatalogs(); // completion asks the catalogs again
    void loadDatasets(); // a workspace's datasets are its catalog's
  }
  if (notice.type === "blades_changed") {
    void rail.loadBlades();
    void loadConnections();
  }
  // (below) a table opened, closed or renamed, or its grid's steps changed: its cell here follows.
  if (notice.type === "dataset_renamed") {
    const { dataset, to } = notice as unknown as { dataset: string; to: string };
    const owned = tableOwner.get(dataset);
    for (const doc of docs) viewOf(doc)?.renameTable(dataset, to);
    if (owned) {
      tableOwner.set(to, owned);
      tableOwner.delete(dataset);
    }
  }
  if (["grid_updated", "grid_shown", "grid_closed", "dataset_updated", "dataset_closed", "dataset_renamed"].includes(notice.type)) {
    refreshTablesSoon();
    // A live cell or a block that names a changed table is out of date now.
    for (const doc of docs) {
      doc.streamlit?.tablesChanged();
      doc.canvas?.tablesChanged();
    }
  }
  // An app's pages or run changed somewhere (a linked cell typed in another window, the agent).
  if (notice.type === "streamlit_changed") {
    for (const doc of docs) {
      doc.streamlit?.noticed((notice as unknown as { app: string }).app);
      doc.canvas?.noticed((notice as unknown as { app: string }).app);
    }
  }
});

void Promise.all([
  refreshHome(),
  loadConnections(),
  api<{ pythons: PythonChoice[] }>("/workbench/pythons").then((r) => (pythons = r.pythons), () => undefined),
]).then(() => {
  showWelcome();
  // A document popped out into this window starts it fresh (a new window copies its opener's session).
  const fresh = openedWith.get("fresh") === "1";
  if (fresh) sessionStorage.removeItem(SESSION_KEY);
  void (fresh ? Promise.resolve(false) : restore()).then(() => {
    const wanted = openedWith.get("open"); // the address as opened (the page clears it once the token is read)
    if (wanted) void open(wanted);
  });
});
