/**
 * workbenchPage.ts: the Workbench, in a window of its own (Plans/workbench-and-connections.plan.md;
 * opened from the grid page's Workbench tab; redesigned 2026-11-15, docs/ideas.md). [COMPOSITION]
 *
 *   [TOP]      one row: the mark, the focused document's name (a dot while it has unsaved changes),
 *              Save, Save as…, and "…" (New notebook, New script, Open…, Recent, split, Commands)
 *   [DATA]     the Data panel on the left (workbenchData.ts; Ctrl+B folds it): the open tables, the
 *              blades' variables, a project's files when there is one. "+ Table" (Open file…, a
 *              connection's tables, the catalog's search) and "+ Blade" open the side bar's old lists
 *              (catalogRail.ts) beside it
 *   [GROUPS]   the documents as tabs in groups (workbenchGroups.ts): drag a tab along a row, or to a
 *              group's edge to split it; splitters size them. The focused group's row ends with its
 *              document's controls: a notebook's "+ Cell", Run all and "…"; a script's "+ Cell", Run
 *              file and "…" (Open…, Recent, Interrupt, Restart, Save as…, the Streamlit app, split)
 *   [PANES]    after RStudio (workbenchLayout.ts): the focused document's console under the groups and
 *              Variables on the right, both closed until the status bar opens them (a run in the
 *              console opens it). Pictures go to the Sandbox
 *   [STATUS]   for the focused document: its kernel (a menu: Interrupt, Restart), its environment, the
 *              cursor; then the Console and Variables toggles
 *   [EMPTY]    nothing open: Start a notebook (and Start an app, once app pages are registered)
 *   [AGENT]    right-click an error or selected code: Send to the agent (workbenchAgent.ts)
 *   [DOC]      a notebook (workbenchNotebook.ts) or a script (workbenchScript.ts), each with its own
 *              console (workbenchConsole.ts) on its kernel; a blade being edited; a table from the catalog
 *   [COMMANDS] every action by one name (workbenchCommands.ts): the palette (Ctrl+Shift+P), the keys, and
 *              the agent's workbench_window tool; the groups' too (split right, split down, move a tab,
 *              focus a group) and the Data panel's
 *   [KEYS]     F5 runs (the file, or every cell) wherever the focus is, never reloading the window;
 *              Ctrl+S saves, Ctrl+O opens; Ctrl+Z outside an editor undoes a cell's delete or move;
 *              Ctrl+1 to Ctrl+3 (and F6) move between the panes; Ctrl+Alt+Page Up and Page Down switch
 *              documents; Ctrl+\ splits right; F1 on a name shows its help
 *   [RESTORE]  open documents, their unsaved text and the groups' layout come back after a reload or a
 *              crashed tab (kept in this window's session storage, in the browser only: nothing is
 *              written to disk)
 *   [TABLES]   every table open in the grid has a read-only cell in the document it belongs to
 *              (docs/ideas.md, 2026-11-14): the document whose kernel sent it, else the one that
 *              already holds its cell, else the one in front. The group's row offers Run tables when a
 *              table's cell is out of date or has not run
 *   [STREAMLIT] there is no Streamlit kind of cell: a Python cell that calls Streamlit shows live in
 *              its cell (workbenchStreamlit.ts). A Streamlit app is a document of its own, a canvas
 *              (workbenchCanvas.ts): New app opens one as a tab; any Python cell is dragged onto it (onto
 *              its tab too) or copied and pasted, as a link; Play shows the page live in place
 *   [PROJECT]  a project is a folder that starts with data.ipynb (its export: data.py): New project,
 *              Open project (its files as tabs, and listed in the Data panel), Export data.py
 *   [POP OUT]  a saved document moves into a Workbench window of its own (the group's "…")
 *
 * ROUTING: /workbench/home, /open, /save, /pythons (routes_workbench.py); kernels in workbenchKernel.ts.
 */
import { handleAgentNotice, loadApprovals } from "./agentAccess";
import { agentApi, api, ApiError, connect, onNotice, openedWith, tellFocus, token } from "./api";
import type { FilledSnippet } from "./starters";
import { type BladeKind, type BladeSummary, editBlade, showTemplatePicker } from "./bladeEditor";
import { mountRail, schemaDetails, tableDetails, watchTheme } from "./catalogRail";
import { openConnections } from "./connectionsWindow";
import { button, clear, h, icon, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { openFile, tableName } from "./openFile";
import { effectiveTheme } from "./theme";
import { allCommands, answerAgent, type Command, openPalette, registerCommands, runCommand } from "./workbenchCommands";
import { consoleView, type ConsoleView } from "./workbenchConsole";
import { forgetCatalogs, listDatasets, pythonCompleter, setDialects } from "./workbenchCompletion";
import { newEnvironment } from "./workbenchEnvironment";
import type { Fix } from "./workbenchErrors";
import { mountDataPanel } from "./workbenchData";
import { mountGroups, onTabKinds, registerTabKind, type SavedLayout, type Side, tabKinds } from "./workbenchGroups";
import { mountLayout } from "./workbenchLayout";
import { menuButton, type MenuEntry, openMenu } from "./workbenchMenu";
import { loadPanels, onPanels, panelOn, turnedOff } from "./panels";
import { openSettings } from "./settingsWindow";
import { betaCommands, betaMark, betaOn, exportBetaLog, mountBeta, setBeta } from "./betaNotes";
import { setDocumentName } from "./workbenchAgent";
import { fetchTables, type TableInfo } from "./workbenchTables";
import { variablesPanel } from "./workbenchVariables";
import { Kernel, WINDOW_ID } from "./workbenchKernel";
import { type CellData, type CellKind, notebookView, type NotebookView } from "./workbenchNotebook";
import { scriptView, type ScriptView } from "./workbenchScript";
import { canvasView, type CanvasView } from "./workbenchCanvas";
import { CELL_DRAG, draggedLink, type MovePlan, problemText, type PaneDocument, type SavedPage, StreamlitDoc, type StreamlitHost } from "./workbenchStreamlit";

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
  /** A notebook's or script's own app on the server: its Python cells, the live ones' state. */
  streamlit?: StreamlitDoc;
  /** A Streamlit app's canvas. */
  canvas?: CanvasView;
}

interface PythonChoice {
  python: string;
  version: string;
  ipykernel: boolean;
  swissarmybench: boolean;
}

const top = document.getElementById("wb-top") as HTMLElement;
// The panes around the groups: the console under them, Variables on the right (the status bar's
// Console and Variables open them).
const layout = mountLayout(
  document.getElementById("wb-body") as HTMLElement,
  document.querySelector(".wb-main") as HTMLElement,
  () => focusSource(),
  () => focusConsole(),
  () => window.setTimeout(() => drawStatus()),
);
const variables = variablesPanel(() => {
  layout.toggle("right", false);
  drawStatus();
});
layout.variables.append(variables.element);
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
let bladeVariables: BladeSummary[] = []; // the blades that are not connections: the Data panel's Variables
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
    bladeVariables = (every as BladeSummary[]).filter((b) => !b.connection);
  } catch {
    connectionNames = [];
    workspaceNames = [];
    bladeNames = [];
    codeNames = [];
    bladeVariables = [];
  }
  data.setBlades(bladeVariables);
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
    drawCursor();
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
        data.setTables(found.map((t) => ({ name: t.name, variable: t.variable, rows: t.rows ?? 0, source: t.source ?? "", origin: t.origin, steps: t.steps })));
        assignTables();
      },
      () => undefined, // the server is away: the cells stay as they are
    );
  }, 120);
}

/** The group row's word on the focused document's tables: Run tables, when one is not up to date. */
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
// The Streamlit cells pane (the Data panel): what the server last listed, the canvas its marks are for.
let paneDocuments: PaneDocument[] = [];
let lastCanvas: Doc | null = null;
let paneTimer: number | null = null;
let paneReady = false;
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
    drew: () => {
      if (doc === current) drawStatus();
      if (doc === markedCanvas()) drawPane(); // its page's blocks are the pane's marks
    },
    moveToData: (plan) => moveToData(plan, doc),
  });
  doc.element.append(doc.canvas.element);
  show(doc);
  return doc;
}

/** A thin cell's move (domain/thin_cells.py): the model work goes into a named cell at the end of the
 *  project's data.ipynb, and the block's cell keeps one line that reads it back. Both documents are
 *  opened when they are not, and left with the change unsaved, as typing leaves them; then the canvas
 *  comes back to the front. */
async function moveToData(plan: MovePlan, from: Doc): Promise<void> {
  const same = (a: string | null, b: string): boolean => !!a && a.replace(/\\/g, "/") === b.replace(/\\/g, "/");
  const held = async (path: string): Promise<Doc> => {
    let doc = docs.find((d) => same(d.path, path));
    if (!doc) {
      await open(path);
      doc = docs.find((d) => same(d.path, path));
    }
    if (!doc) throw new Error(`${baseName(path)} could not be opened: Move to data.ipynb needs the project's data.ipynb (New project… makes one).`);
    return doc;
  };
  const data = await held(plan.notebook);
  if (!data.notebook) throw new Error(`${baseName(plan.notebook)} is not a notebook.`);
  const source = await held(plan.document);
  data.notebook.appendNamed(plan.data_code.replace(/\n+$/, ""), plan.title);
  if (source.notebook) source.notebook.setSource(plan.cell, plan.cell_code.replace(/\n+$/, ""));
  else if (source.script) source.script.setSource(plan.cell, plan.cell_code);
  else throw new Error(`${baseName(plan.document)} is not a notebook or a script.`);
  show(from);
  toast(`Moved to data.ipynb: ${plan.names.join(", ")}`);
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

/** The project's files in the Data panel: data.ipynb, data.py set in as its output, the app's canvas,
 *  the notebooks and scripts. */
function listProject(): void {
  refreshPane(); // the project's files are the pane's too
  if (!project) return void data.setFiles(null);
  const files = project.files.flatMap((path) => {
    const name = baseName(path);
    const file = { path: name, icon: name.toLowerCase().endsWith(APP_ENDING) ? "page" : name.toLowerCase().endsWith(".py") ? "code" : "notebook", open: () => void open(path) };
    // data.py is data.ipynb's export: listed under it, greyed, never opened from here.
    return name.toLowerCase() === DATA_NOTEBOOK ? [file, { path: "data.py", icon: "code", derived: true }] : [file];
  });
  data.setFiles({ root: `${project.name}/`, files });
}

/** A project's files as tabs: data.ipynb first (and in front), then the app's canvas, then the rest. */
async function showProject(found: ProjectFiles): Promise<ProjectFiles> {
  project = found;
  listProject();
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

/** `agent`: the agent asked (workbench_window): its request, which the server holds for the user's Allow
 * when data.ipynb would hold a pasted table's rows. */
async function newProject(folder?: string, name?: string, notebooks: string[] = [], app = true, agent = false): Promise<ProjectFiles | null> {
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
  return showProject(await (agent ? agentApi : api)<ProjectFiles>("/projects", "POST", { folder: where, name: called, notebooks, app }));
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

interface ExportAnswer {
  path: string | null;
  file: string;
  problems: string[];
  lint: string[];
  stubs: string[];
  skipped: string[];
  settings: { variable: string; secret: boolean }[];
  ask?: string;
  run?: string;
}

/** Export as one Python script… (or as one notebook…): the document as it stands here (saved or
 * not) as one self-contained file that runs with plain `python` (or top to bottom in any Jupyter),
 * written where the file chooser says (docs/ideas.md, 2026-11-15). What cannot be exported is named
 * by its cell first, and the rest goes out with a FILL IN stub for each only when the user says so.
 * `to`: where it goes (the agent's palette call); without it, the file chooser opens. */
async function exportDocument(doc: Doc | null, format: "script" | "notebook", to?: string, agent = false): Promise<ExportAnswer | null> {
  if (!doc || (!doc.notebook && !doc.script)) throw new Error("Open a notebook or a script to export.");
  const ending = format === "notebook" ? ".ipynb" : ".py";
  const stem = (doc.path ? baseName(doc.path) : doc.title).replace(/\.(ipynb|py)$/i, "");
  const suggested = `${stem.trim().replace(/\W+/g, "_").replace(/^_+|_+$/g, "").toLowerCase() || "job"}_automation${ending}`;
  let path = to;
  if (!path) {
    const title = format === "notebook" ? "Export as one notebook" : "Export as one Python script";
    path = (await chooseFile({ title, mode: "save", start: doc.path ?? project?.folder ?? homeFolder, name: suggested })) ?? undefined;
    if (!path) return null;
  }
  if (!path.toLowerCase().endsWith(ending)) path += ending;
  const body: Record<string, unknown> = {
    format,
    to: path,
    path: doc.path,
    name: doc.title,
    ...(doc.notebook ? { kind: "notebook", cells: doc.notebook.cells() } : { kind: "script", text: doc.script!.text() }),
  };
  const call = agent ? agentApi : api;
  let done = await call<ExportAnswer>("/workbench/export-script", "POST", body);
  if (done.ask) {
    const said = [...done.problems, ...done.lint].map((p) => `• ${p}`).join("\n");
    if (agent || !confirm(`These cannot be exported:\n${said}\n\nExport the rest, with a stub that raises FILL IN for each?`)) {
      if (!agent) toast("Nothing was exported.");
      return done;
    }
    done = await call<ExportAnswer>("/workbench/export-script", "POST", { ...body, stub: true });
  }
  for (const said of done.skipped) toast(said);
  const secrets = done.settings.filter((s) => s.secret).map((s) => s.variable);
  const note = secrets.length ? ` Set ${secrets.join(", ")} where it runs.` : "";
  toast(`Exported ${done.file}${done.stubs.length ? ` (FILL IN: ${done.stubs.join(", ")})` : ""}.${note}`);
  return done;
}

/** The project's entries (in a group's "+" and the top bar's "…"). */
function projectEntries(): MenuEntry[] {
  const guarded = (act: () => Promise<unknown>) => (): void => void act().catch((e: Error) => toast(e.message, "error"));
  const open = docs.some(isData) || !!project;
  return [
    { label: "New project…", icon: "plus", title: "A folder that starts with data.ipynb", run: guarded(() => newProject()) },
    { label: "Open project…", icon: "folder", run: guarded(() => openProject()) },
    { label: "Export data.py", icon: "export", disabled: !open, title: open ? "Written again from data.ipynb" : "No project is open", run: guarded(exportData) },
  ];
}

// ----- a document MOVES to another Workbench window (the owner, 2026-11-15) -----
// Popped out into a window of its own, or moved back to the main window: its unsaved text, its cell
// numbers, its outputs and its running kernel go with it, and this window's tab closes once the other
// has taken it (the server holds it on the way: /workbench/handoffs). Never two live copies.

/** A window a tab was popped out into (else this is a main window: one the user opened). Kept in this
 *  window's session storage, so a reload of a popped-out window still knows it. */
const POPPED: boolean = ((): boolean => {
  const key = "workbench-popped";
  try {
    if (openedWith.get("popped") === "1") sessionStorage.setItem(key, "1");
    else if (openedWith.get("fresh") !== "1" && !openedWith.get("take")) return sessionStorage.getItem(key) === "1";
    return openedWith.get("popped") === "1";
  } catch {
    return openedWith.get("popped") === "1";
  }
})();
const isMainWindow = (): boolean => !POPPED;
const moves = (doc: Doc): boolean => !!(doc.notebook || doc.script || doc.canvas);

/** A document as it moves: everything the window holds of it. */
function movingState(doc: Doc): Remembered & { title: string } {
  return {
    kind: doc.notebook ? "notebook" : doc.canvas ? "app" : "script",
    path: doc.path,
    title: doc.title,
    modified: doc.modified,
    dirty: doc.dirty,
    python: doc.python,
    ...(doc.notebook ? { cells: doc.notebook.cells(), next_cell: doc.notebook.nextCell() } : doc.canvas ? { pages: doc.canvas.pages() } : { text: doc.script!.text() }),
  };
}

/** Hand a document to another window (`to`: a window's id; null: a new window, opened for it). Its
 *  tab here closes once that window has taken it; if none does, it stays. */
async function moveOut(doc: Doc, to: string | null): Promise<{ title: string; window: "new" | "main" }> {
  if (!moves(doc)) throw new Error("Only a notebook, a script or a Streamlit app moves to another window.");
  const kernel = doc.kernel?.id ?? null;
  const { id } = await api<{ id: string }>("/workbench/handoffs", "POST", { document: movingState(doc), kernel, to });
  if (to === null) {
    const hash = new URLSearchParams({ token, take: id, fresh: "1", popped: "1" }).toString();
    const opened = window.open(`/workbench#${hash}`, `swissarmybench-workbench-${Date.now()}`, "popup,width=1200,height=800");
    if (!opened) {
      await api(`/workbench/handoffs/${id}`, "DELETE").catch(() => undefined);
      throw new Error("The browser blocked the new window. Allow pop-ups for this address.");
    }
  }
  doc.element.classList.add("moving"); // nothing typed here now: it is on its way
  const until = Date.now() + (to === null ? 30000 : 8000);
  while (Date.now() < until) {
    await new Promise((done) => setTimeout(done, 250));
    const state = await api<{ taken: boolean }>(`/workbench/handoffs/${id}`).catch(() => ({ taken: false }));
    if (!state.taken) continue;
    doc.kernel?.release(); // it runs on, the other window's now
    close(doc, true);
    return { title: doc.title, window: to === null ? "new" : "main" };
  }
  const cancelled = await api<{ cancelled: boolean }>(`/workbench/handoffs/${id}`, "DELETE").catch(() => ({ cancelled: true }));
  if (!cancelled.cancelled) {
    doc.kernel?.release();
    close(doc, true);
    return { title: doc.title, window: to === null ? "new" : "main" };
  }
  doc.element.classList.remove("moving");
  throw new Error(to === null ? `The new window did not take ${doc.title}: it stays here.` : `The main Workbench window is not open: ${doc.title} stays here.`);
}

/** Pop a document out into a Workbench window of its own (so it can sit on another screen). */
const popOut = (doc: Doc): Promise<{ title: string; window: "new" | "main" }> => moveOut(doc, null);

/** A popped-out window's document back to the main window. */
function moveToMain(doc: Doc): Promise<{ title: string; window: "new" | "main" }> {
  if (isMainWindow()) throw new Error("This is the main Workbench window.");
  return moveOut(doc, "main"); // the main window that takes it first (the server makes sure only one does)
}

/** Take a document another window handed to this one: as it was there, its kernel still running. */
async function takeDocument(id: string): Promise<void> {
  const taken = await api<{ document: Remembered & { title: string }; kernel: string | null }>(`/workbench/handoffs/${id}/take`, "POST", { window: WINDOW_ID });
  const r = taken.document;
  const doc = r.kind === "notebook" ? openNotebook(r.path, r.cells ?? [], r.modified, r.next_cell) : r.kind === "app" ? openApp(r.path, r.pages ?? [], r.modified) : openScript(r.path, r.text ?? "", r.modified);
  if (!r.path && r.title) doc.title = r.title;
  doc.python = r.python;
  if (r.python && !pythons.some((p) => p.python === r.python)) pythons.push({ python: r.python, version: "", ipykernel: true, swissarmybench: true });
  doc.dirty = r.dirty;
  if (taken.kernel && doc.kernel) doc.kernel.adopt(taken.kernel, r.python ?? "");
  show(doc);
  drawTabs();
  drawStatus();
  remember();
}

const restoreSteps = (grid: string, steps: unknown[]): void => void api(`/grids/${encodeURIComponent(grid)}/steps`, "POST", { steps }).catch((e: Error) => toast(e.message, "error"));

function makeDoc(kind: Doc["kind"], title: string, path: string | null, modified: number | null): Doc {
  const doc: Doc = { id: ++counter, kind, title, path, modified, dirty: false, kernel: null, python: null, element: h("div", { class: `wb-doc-body kind-${kind}` }) };
  if (kind === "notebook" || kind === "script") {
    const kernel = new Kernel(() => doc.path, () => doc.python);
    doc.kernel = kernel;
    kernel.onState(() => {
      if (doc === current) drawStatus();
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

/** F5 and the group row's main Run: the file, or every cell. */
async function runPrimary(doc: Doc | null): Promise<void> {
  if (doc?.script) await doc.script.runFile();
  else if (doc?.notebook) await doc.notebook.runAll();
}

function focusSource(): void {
  if (current?.script) current.script.focus();
  else if (current?.notebook) current.notebook.commandMode();
  else (document.querySelector(".wb-group.focused .wb-gbody")?.querySelector("button, input, [tabindex]") as HTMLElement | null)?.focus();
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

/** A run in a document's console: the console opens to show it. */
function useConsole(doc: Doc): void {
  if (doc !== current || layout.state().console || !panelOn("workbench.console")) return;
  layout.toggle("console", true);
  drawStatus();
}

/** Show a document: in front of its group, that group focused (a new one opens in the focused group). */
function show(doc: Doc): void {
  groups.show(doc);
}

/** The focused group's document changed: everything that follows the focused document follows. */
function focused(doc: Doc | null): void {
  current = doc;
  variables.show(doc?.kernel ?? null);
  // A Streamlit app runs no code of its own: its console's place says nothing.
  if (doc?.kind === "app") layout.console.replaceChildren();
  else layout.console.replaceChildren(doc?.console?.element ?? h("p", { class: "hint wb-pane-empty" }, "No console"));
  cursor = { line: 1, column: 1 };
  drawEmpty();
  drawControls();
  drawStatus();
  document.title = doc ? `${doc.title} · Workbench` : "Workbench";
  remember();
  assignSoon(); // a table with no document yet goes to the one in front
  if (doc?.canvas) lastCanvas = doc;
  drawPane(); // the marks are the canvas page's in front
}

function close(doc: Doc, moved = false): void {
  // (A document that moved to another window took its changes with it.)
  if (!moved && doc.dirty && !confirm(`${doc.title} has changes that are not saved. Close it anyway?`)) return;
  doc.kernel?.stop();
  doc.streamlit?.close(); // its Streamlit process and temporary folder go with it
  doc.canvas?.close();
  // Its Monaco editors and design frames go too (they were kept alive, detached, before).
  doc.notebook?.dispose();
  doc.script?.dispose();
  doc.console?.dispose();
  docs.splice(docs.indexOf(doc), 1);
  tablesSent.delete(doc);
  if (doc.kind === "blade") editingBlade = false;
  groups.remove(doc); // the group's next document comes to the front (and the group goes with its last)
  drawEmpty();
  remember();
}

/** A document's title or unsaved dot changed. */
function drawTabs(): void {
  groups.redraw();
  drawTop();
}

/** A document's kind of tab: Data (a notebook named data.ipynb), Notebook, Script, App page (a
 *  Streamlit app's canvas), Blade, Table. */
function kindOf(doc: Doc): string {
  if (doc.kind === "app") return "page";
  if (doc.kind === "notebook") return doc.title.toLowerCase() === "data.ipynb" ? "data" : "notebook";
  return doc.kind === "table" ? "explorer" : doc.kind;
}

registerTabKind({ id: "data", label: "Data", icon: "sql", mark: "data" });
registerTabKind({ id: "notebook", label: "Notebook", icon: "notebook", mark: "notebook", start: { label: "New notebook", run: () => void openNotebook(null, [], null) } });
registerTabKind({ id: "script", label: "Script", icon: "code", mark: "notebook", start: { label: "New script", run: () => void openScript(null, "", null) } });
registerTabKind({ id: "page", label: "App page", icon: "page", mark: "page", start: { label: "New Streamlit app", run: () => void openApp(null, [], null) } });
registerTabKind({ id: "blade", label: "Blade", icon: "bolt", mark: "notebook" });
registerTabKind({ id: "explorer", label: "Table", icon: "rows", mark: "notebook" });

const groups = mountGroups<Doc>({
  kindOf,
  focused,
  close: (doc) => close(doc),
  plus: (anchor) => void openMenu(anchor, "New tab", newEntries(anchor)),
  changed: () => remember(),
  tabMade: (doc, element) => {
    // Right-click: the tab's moves between windows, and Close.
    element.addEventListener("contextmenu", (e) => {
      if (!moves(doc)) return;
      e.preventDefault();
      openMenu(element, "Tab menu", [...moveEntries(doc), null, { label: "Close", icon: "close", run: () => close(doc) }]);
    });
    // A cell dropped on a Streamlit app's tab goes to the end of its current page.
    element.addEventListener("dragover", (e) => {
      if (!doc.canvas || !e.dataTransfer?.types.includes(CELL_DRAG)) return;
      e.preventDefault();
      element.classList.add("drop");
    });
    element.addEventListener("dragleave", () => element.classList.remove("drop"));
    element.addEventListener("drop", (e) => {
      element.classList.remove("drop");
      const link = doc.canvas ? draggedLink(e.dataTransfer) : null;
      if (!link) return;
      e.preventDefault();
      void doc.canvas!.place(link);
    });
  },
});
const empty = h("div", { class: "wb-welcome wb-empty", hidden: true });
layout.source.append(groups.element, empty);

/** What a group's "+" and the top bar's "…" make: each kind that starts from there, then Open and Recent. */
function newEntries(anchor: HTMLElement): MenuEntry[] {
  return [
    ...tabKinds()
      .filter((k) => k.start)
      .map((k) => ({ label: k.start!.label, icon: k.icon, run: k.start!.run })),
    null,
    ...projectEntries(),
    null,
    { label: "Open…", icon: "folder", keys: "Ctrl+O", run: () => void open() },
    { label: "Recent…", icon: "more", run: () => recentMenu(anchor) },
  ];
}

/** Whether a document's group has another tab to keep when it moves out to a new group. */
const canSplit = (doc: Doc | null): boolean => !!doc && (groups.list()[groups.indexOf(doc)]?.tabs.length ?? 0) > 1;
const SPLIT_WHY = "its group has only this tab: open another first";

function splitDoc(doc: Doc | null, side: Side): void {
  if (!doc || !groups.split(doc, side)) throw new Error(`It cannot split: ${SPLIT_WHY}.`);
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
      if (!pythons.some((p) => p.python === found.python)) pythons.push({ python: found.python, version: "", ipykernel: true, swissarmybench: true });
      drawStatus();
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
  openMenu(
    anchor,
    "Recent files",
    recent.length
      ? recent.map((r) => ({ label: baseName(r.path), title: r.exists ? r.path : `${r.path} (missing)`, disabled: !r.exists, run: () => void open(r.path) }))
      : [{ label: "No recent files", heading: true }],
    { align: anchor.closest(".wb-top") ? "right" : "left" },
  );
}

// ===== the top bar, a group's row, the status bar =====

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
  if (!pythons.some((p) => p.python === python)) pythons.push({ python, version: "", ipykernel: true, swissarmybench: true });
  if (doc.kernel?.id) {
    doc.kernel.stop();
    toast("Kernel stopped");
  }
  if (doc.path) void api("/workbench/environment", "POST", { path: doc.path, python }).catch((e: Error) => toast(e.message, "error"));
  drawStatus();
}

/** A Python by its environment's last two folders (project/.venv); this app's own by those words. */
function pythonName(python: string): string {
  if (python === pythons[0]?.python) return "This app's Python";
  return python.replace(/[\\/](bin[\\/]python[\d.]*|Scripts[\\/]python\.exe)$/i, "").split(/[\\/]/).filter(Boolean).slice(-2).join("/");
}

function pythonPicker(doc: Doc): HTMLElement {
  const select = h("select", { class: "wb-env-pick", "aria-label": "Environment", title: "Environment" }) as HTMLSelectElement;
  const own = pythons[0];
  const label = (p: PythonChoice): string => `${pythonName(p.python)}${p.version ? ` (${p.version})` : ""}${p.ipykernel ? "" : ", no ipykernel"}`;
  for (const p of pythons) select.append(h("option", { value: p.python, title: p.python, selected: (doc.python ?? own?.python) === p.python }, label(p)));
  select.append(h("option", { value: "__new" }, "New environment…"), h("option", { value: "__other" }, "Another Python…"));
  select.addEventListener("change", async () => {
    if (select.value === "__new") {
      const made = await newEnvironment({ folder: folderOf(doc.path), document: doc.path, appVersion: own?.version ?? "" });
      if (made) {
        useEnvironment(doc, made.python);
        if (made.imports.length && doc.notebook) doc.notebook.add("code", made.imports.join("\n"), true);
      }
      drawStatus();
      return;
    }
    if (select.value === "__other") {
      const path = await chooseFile({ title: "Choose a Python", mode: "file", start: folderOf(doc.path) });
      if (path) useEnvironment(doc, path);
      drawStatus();
      return;
    }
    useEnvironment(doc, select.value);
  });
  return select;
}

// ----- the top bar: the mark, the focused document's name, Save, Save as…, "…"

const topName = h("span", { class: "wb-name" });
const saveButton = button("Save", () => void save(current), { icon: "save", title: "Save (Ctrl+S)" });
const saveAsButton = button("Save as…", () => void save(current, true), { icon: "folder", title: "Save as (Ctrl+Shift+S)" });
const topMenu = menuButton(button("Workbench menu", () => undefined, { icon: "more", iconOnly: true, class: "ghost", title: "More" }), "Workbench menu", () => topEntries(), { align: "right" });
{
  // The app's mark: the window's icon, drawn small.
  const mark = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  mark.setAttribute("viewBox", "0 0 100 100");
  mark.setAttribute("aria-hidden", "true");
  mark.innerHTML = '<path d="M42 23h16v19h19v16H58v19H42V58H23V42h19z"/>';
  top.append(h("span", { class: "wb-mark" }, mark), topName, saveButton, saveAsButton, h("span", { class: "wb-grow" }), topMenu);
}

function drawTop(): void {
  const doc = current;
  clear(topName, h("span", { class: "wb-name-text" }, doc?.title ?? "Workbench"), doc?.dirty ? h("span", { class: "wb-name-dot", role: "img", "aria-label": "Unsaved changes", title: "Unsaved changes" }) : null);
  topName.title = doc?.path ?? doc?.title ?? "";
  for (const b of [saveButton, saveAsButton]) {
    b.disabled = !saves();
    b.title = saves() ? (b === saveButton ? "Save (Ctrl+S)" : "Save as (Ctrl+Shift+S)") : "Nothing that saves is in front";
  }
}

/** The top bar's "…": what makes a document, opens one, splits the groups, and every command. */
function topEntries(): MenuEntry[] {
  const folded = data.collapsed();
  return [
    ...newEntries(topMenu),
    null,
    { label: "Split right", icon: "splitRight", keys: "Ctrl+\\", disabled: !canSplit(current), title: canSplit(current) ? undefined : SPLIT_WHY, run: () => splitDoc(current, "right") },
    { label: "Split down", icon: "splitDown", disabled: !canSplit(current), title: canSplit(current) ? undefined : SPLIT_WHY, run: () => splitDoc(current, "down") },
    null,
    ...(panelOn("workbench.data") ? [{ label: folded ? "Expand the Data panel" : "Collapse the Data panel", icon: folded ? "expand" : "collapse", keys: "Ctrl+B", run: () => void data.toggle() }] : []),
    { label: "Layout: source only", icon: "max", keys: "Ctrl+Shift+1", run: () => void runCommand("view.focus") },
    { label: "Layout: standard", icon: "restore", run: () => void runCommand("view.standard") },
    null,
    { label: "Commands…", icon: "steps", keys: "Ctrl+Shift+P", run: () => openPalette() },
    { label: "Settings…", icon: "cog", run: () => openSettings() },
    null,
    betaOn() ? { label: "Turn beta mode off", icon: "exclude", run: () => void setBeta(false) } : { label: "Turn beta mode on", icon: "check", run: () => void setBeta(true) },
    { label: "Export beta log…", icon: "export", run: () => void exportBetaLog() },
  ];
}

// ----- a group's row: the focused document's controls

/** The kinds of cell "+ Cell" adds: a notebook's five, a script's two (its cells are marked lines).
 *  There is no Streamlit kind: a Python cell that calls Streamlit is shown live. */
function cellEntries(doc: Doc): MenuEntry[] {
  if (doc.script) {
    return [
      { label: "DAX", icon: "group", title: "A query on a Power BI workspace's dataset", run: () => void doc.script!.addDax(datasetNames[0] ?? "") },
      { label: "HTML", icon: "image", title: "A design drawn from its HTML", run: () => void doc.script!.addHtml() },
    ];
  }
  const add = (kind: CellKind) => (): void => doc.notebook!.add(kind);
  return [
    { label: "Python", icon: "code", keys: "B", run: add("code") },
    { label: "SQL", icon: "sql", run: add("sql") },
    { label: "DAX", icon: "group", title: "A query on a Power BI workspace's dataset", run: add("dax") },
    { label: "HTML", icon: "image", title: "A design drawn from its HTML", run: add("html") },
    { label: "Markdown", icon: "edit", run: add("markdown") },
  ];
}

/** A group's "…": the rest of what the old toolbar held, for the document in front of it. */
function moreEntries(doc: Doc, anchor: HTMLElement): MenuEntry[] {
  const kernel = doc.kernel;
  const split = canSplit(doc);
  return [
    ...(doc.script ? [{ label: "Run statement", icon: "play", keys: "Ctrl+Enter", run: () => void doc.script!.runSelection() }] : []),
    ...(doc.notebook ? [{ label: "Clear every output", icon: "clean", run: () => doc.notebook!.clearAll() }] : []),
    null,
    { label: "Open…", icon: "folder", keys: "Ctrl+O", run: () => void open() },
    { label: "Recent…", icon: "more", run: () => recentMenu(anchor) },
    ...(doc.notebook || doc.script ? [{ label: "Save as…", icon: "save", keys: "Ctrl+Shift+S", run: () => void save(doc, true) }] : []),
    ...(doc.notebook || doc.script
      ? [
          { label: "Export as one Python script…", icon: "export", title: "One .py that runs with plain python: its connections, vault lookups and grid steps written out", run: () => void exportDocument(doc, "script").catch((e: Error) => toast(e.message, "error")) },
          { label: "Export as one notebook…", icon: "export", title: "One linear .ipynb that runs top to bottom in any Jupyter (nbconvert, papermill)", run: () => void exportDocument(doc, "notebook").catch((e: Error) => toast(e.message, "error")) },
        ]
      : []),
    null,
    ...(kernel
      ? [
          { label: "Interrupt", icon: "stop", run: () => void kernel.interrupt() },
          { label: "Restart", icon: "back", run: () => void restartKernel(kernel) },
        ]
      : []),
    null,
    ...moveEntries(doc),
    { label: "Split right", icon: "splitRight", keys: "Ctrl+\\", disabled: !split, title: split ? undefined : SPLIT_WHY, run: () => splitDoc(doc, "right") },
    { label: "Split down", icon: "splitDown", disabled: !split, title: split ? undefined : SPLIT_WHY, run: () => splitDoc(doc, "down") },
    { label: "Close", icon: "close", run: () => close(doc) },
  ];
}

/** A tab's moves between windows (its "…" menu and its right-click menu). */
function moveEntries(doc: Doc): MenuEntry[] {
  if (!moves(doc)) return [];
  const guarded = (act: () => Promise<unknown>) => (): void => void act().catch((e: Error) => toast(e.message, "error"));
  return [
    { label: "Open in its own window", icon: "popout", run: guarded(() => popOut(doc)) },
    ...(isMainWindow() ? [] : [{ label: "Move to the main window", icon: "back", run: guarded(() => moveToMain(doc)) }]),
  ];
}

/** The focused group's row, right side: Run tables (only while one waits), "+ Cell", the main Run, "…". */
function drawControls(): void {
  drawTop();
  const host = groups.controls();
  const doc = current;
  if (!doc) return void host.replaceChildren();
  const more = button("Document menu", () => undefined, { icon: "more", iconOnly: true, class: "ghost wb-more", title: "More" });
  menuButton(more, "Document menu", () => moreEntries(doc, more), { align: "right" });
  // A Streamlit app's canvas: Play, Edit, Export, Save as (its pages are tabs inside the canvas).
  if (doc.canvas) return void host.replaceChildren(doc.canvas.tools, more);
  if (!doc.notebook && !doc.script) return void host.replaceChildren(more);
  const addCell = h("button", { type: "button", class: "btn line wb-add-cell", "aria-label": "Add cell", title: "Add cell" }, icon("plus"), h("span", { class: "btn-label" }, "Cell"), icon("down")) as HTMLButtonElement;
  menuButton(addCell, "Cell kinds", () => cellEntries(doc));
  const run = doc.notebook
    ? button("Run all", () => void doc.notebook!.runAll(), { icon: "play", class: "primary", title: "Run all (F5)" })
    : button("Run file", () => void doc.script!.runFile(), { icon: "play", class: "primary", title: "Run file (F5)" });
  host.replaceChildren(tablesHost, addCell, run, more);
  drawTablesTool();
}

async function restartKernel(kernel: Kernel): Promise<boolean> {
  const did = await kernel.restart();
  toast(did ? "Restarted" : "Nothing to restart");
  return did;
}

// ----- the status bar: for the focused document

const kernelHost = h("span", { class: "wb-status-kernel" });
const envHost = h("span", { class: "wb-status-env" });
const cursorHost = h("span", { class: "wb-status-cursor" });
const consoleToggle = button("Console", () => {
  layout.toggle("console");
  drawStatus();
}, { class: "ghost wb-toggle wb-console-toggle", pressed: false });
const variablesToggle = button("Variables", () => {
  if (layout.toggle("right")) void variables.refresh();
  drawStatus();
}, { class: "ghost wb-toggle wb-variables-toggle", pressed: false });
layout.status.append(kernelHost, envHost, cursorHost, h("span", { class: "spacer" }), betaMark(), consoleToggle, variablesToggle);

function drawCursor(): void {
  const doc = current;
  cursorHost.textContent = doc?.notebook || doc?.script ? `Line ${cursor.line}, column ${cursor.column}` : "";
}

/** The status bar: the kernel (its state only while it is not ready, as principle 7.9 asks; its menu
 *  always), the environment, the cursor; the Console and Variables toggles. */
function drawStatus(): void {
  const doc = current;
  const kernel = doc?.kernel;
  if (kernel) {
    const words = STATE_WORDS[kernel.state];
    const knob = h(
      "button",
      { type: "button", class: `btn ghost wb-kernel ${kernel.state}`, "aria-label": "Kernel", title: "Kernel: Interrupt, Restart" },
      h("span", { class: "wb-dot", "aria-hidden": "true" }),
      h("span", {}, "Kernel"),
      words ? h("span", { class: `wb-state ${kernel.state}` }, words, kernel.running > 1 ? ` (${kernel.running - 1} waiting)` : "") : null,
      icon("down"),
    ) as HTMLButtonElement;
    menuButton(knob, "Kernel", () => [
      { label: "Interrupt", icon: "stop", run: () => void kernel.interrupt() },
      { label: "Restart", icon: "back", run: () => void restartKernel(kernel) },
    ], { above: true });
    clear(kernelHost, knob);
    // Not drawn again while the picker is in use (a run's state changes would close it).
    if (!envHost.contains(document.activeElement) || envHost.dataset.doc !== String(doc.id)) {
      clear(envHost, pythonPicker(doc));
      envHost.dataset.doc = String(doc.id);
    }
  } else if (doc?.canvas) {
    // A Streamlit app: the Python it runs in (its first linked file's), and Play's state while it
    // is starting. Its other states are on the canvas itself (out of date, missing, a problem).
    const python = doc.canvas.state()?.python;
    clear(
      kernelHost,
      python ? h("span", { class: "hint wb-app-python", title: python }, pythonName(python)) : null,
      doc.canvas.busy() ? h("span", { class: "wb-state starting" }, "starting…") : null,
    );
    clear(envHost);
    envHost.dataset.doc = "";
  } else {
    clear(kernelHost, doc ? h("span", { class: "hint" }, doc.kind === "blade" ? "Blade" : "Table") : null);
    clear(envHost);
    envHost.dataset.doc = "";
  }
  drawCursor();
  const state = layout.state();
  consoleToggle.setAttribute("aria-pressed", String(state.console));
  variablesToggle.setAttribute("aria-pressed", String(state.right));
  consoleToggle.disabled = !doc?.console;
  consoleToggle.title = doc?.console ? "Console (Ctrl+2)" : "No console for what is in front";
}

// ===== the Data panel: the tables, the blades' variables; the catalog and the blades beside it =====

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

const data = mountDataPanel({
  goToTable: (name) => goToTable(name),
  goToCell: (document, title, cell) => void goToCell(document, title, cell).catch((e: Error) => toast(e.message, "error")),
  addTable: (anchor) => void openMenu(anchor, "Add a table", tableEntries()),
  openBlade: (name) => bladeDoc(name),
  toggled: () => remember(),
});
(document.querySelector(".wb-layout") as HTMLElement).prepend(data.element);
paneReady = true;

/** "+ Table": a file, a connection's tables, the catalog's search, a new connection. */
function tableEntries(): MenuEntry[] {
  const sources = [...connectionNames, ...workspaceNames];
  return [
    { label: "Open file…", icon: "folder", run: () => void openFile() },
    null,
    ...(sources.length ? [{ label: "Connections", heading: true }] : []),
    ...sources.map((name) => ({ label: name, icon: "sql", run: () => browse(name) })),
    { label: "Search the catalog…", icon: "zoom", run: () => browse() },
    { label: "Add connection…", icon: "plus", run: () => void openConnections().then(() => void rail.loadBlades()) },
  ];
}

/** The catalog beside the Data panel: a connection's tables (or the search, without one). */
function browse(connection?: string): void {
  data.flyout("catalog");
  if (connection) void rail.loadCatalogs(connection);
}

/** A table's click in the Data panel: its read-only cell in the focused document. */
/** A Streamlit cells pane entry's click: its document in front (opened when it is not), the cell shown. */
async function goToCell(document: string | null, title: string, cell: number): Promise<void> {
  let doc = docs.find((d) => (document ? d.path === document : !d.path && d.title === title));
  if (!doc && document) {
    await open(document);
    doc = docs.find((d) => d.path === document);
  }
  if (!doc) throw new Error(`${title} is not open here.`);
  show(doc);
  if (!viewOf(doc)?.goTo(cell)) throw new Error(`${title} has no cell ${cell} now.`);
}

// ----- the Streamlit cells pane (the Data panel): every cell that calls Streamlit, by document

/** The canvas the pane's marks are for: the one in front, else the last one that was. */
function markedCanvas(): Doc | null {
  return current?.canvas ? current : lastCanvas && docs.includes(lastCanvas) ? lastCanvas : (docs.find((d) => d.canvas) ?? null);
}

/** The pane drawn from what the server last said, each cell on the marked canvas's page marked. */
function drawPane(): void {
  if (!paneReady) return; // the Data panel is not made yet
  const canvasDoc = markedCanvas();
  const state = canvasDoc?.canvas?.state();
  const front = canvasDoc?.canvas?.report() as { page?: string | null } | undefined;
  const page = state?.pages.find((p) => p.id === front?.page) ?? state?.pages[0];
  data.setStreamlitCells(paneDocuments, new Set((page?.blocks ?? []).map((b) => `${b.document}#${b.cell}`)));
}

/** The pane's entries from the server, soon (the open documents', and the project's files). */
function refreshPane(): void {
  if (paneTimer !== null) window.clearTimeout(paneTimer);
  paneTimer = window.setTimeout(() => {
    paneTimer = null;
    const folder = project ? `?folder=${encodeURIComponent(project.folder)}` : "";
    void api<{ documents: PaneDocument[] }>(`/streamlit/cells${folder}`).then(
      (listed) => {
        paneDocuments = listed.documents;
        drawPane();
      },
      () => undefined,
    );
  }, 150);
}

function goToTable(name: string): void {
  const view = current ? viewOf(current) : undefined;
  const line = view?.tables().find((t) => t.name === name);
  if (!view || !line?.cell) {
    toast(current ? `${name} has no cell in ${current.title}` : `Open a notebook for ${name}'s cell`);
    return;
  }
  view.foldTables(false, name);
  view.goTo(line.cell);
}

const rail = mountRail({
  bladesHost: data.bladesHost,
  catalogHost: data.catalogHost,
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
  const code = docs.filter((d) => d.notebook || d.script || d.canvas);
  const at = current ? code.indexOf(current) : -1;
  // The groups as they are: each document by its place in `docs` (a blade or a table is left out).
  const layoutNow = groups.save((d) => (code.includes(d) ? code.indexOf(d) : null));
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ docs: kept(true), current: at, groups: layoutNow, project }));
  } catch {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({ docs: kept(false), current: at, groups: layoutNow, project })); // too big with outputs
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
  type Saved = { docs: Remembered[]; current: number; groups?: SavedLayout; project?: ProjectFiles | null } | null;
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
  listProject();
  const opened: Doc[] = [];
  const byKey = new Map<number, Doc>();
  for (const [key, r] of saved.docs.entries()) {
    if (r.path && !r.dirty) {
      await open(r.path); // fresh from its file
      const reopened = docs.find((d) => d.path === r.path);
      if (reopened) {
        opened.push(reopened);
        byKey.set(key, reopened);
      }
      continue;
    }
    const doc = r.kind === "notebook" ? openNotebook(r.path, r.cells ?? [], r.modified, r.next_cell) : r.kind === "app" ? openApp(r.path, r.pages ?? [], r.modified) : openScript(r.path, r.text ?? "", r.modified);
    doc.python = r.python;
    if (r.python && !pythons.some((p) => p.python === r.python)) pythons.push({ python: r.python, version: "", ipykernel: true, swissarmybench: true });
    doc.dirty = r.dirty;
    opened.push(doc);
    byKey.set(key, doc);
  }
  // The groups as they were (their tabs, sizes and the focused one); without them, the one in front.
  if (saved.groups) groups.restore(saved.groups, (key) => byKey.get(key));
  else {
    const back = byKey.get(saved.current) ?? opened[opened.length - 1];
    if (back) show(back);
  }
  drawTabs();
  return opened.length > 0;
}

// ===== start =====

/** Nothing open: the empty state has the area (Start a notebook; Start an app once app pages exist). */
function drawEmpty(): void {
  const none = docs.length === 0;
  groups.element.hidden = none;
  empty.hidden = !none;
  layout.empty(none);
  layout.status.hidden = none;
  if (!none || empty.childElementCount) return;
  const app = tabKinds().find((k) => k.mark === "page" && k.start);
  clear(
    empty,
    h("div", { class: "wb-empty-choice" }, h("span", { class: "wb-empty-icon" }, icon("notebook")), button("Start a notebook", () => void openNotebook(null, [], null), { icon: "plus", class: "primary" })),
    h(
      "div",
      { class: "wb-empty-choice app" },
      h("span", { class: "wb-empty-icon app" }, icon("page")),
      app
        ? button("Start an app", () => app.start!.run(), { icon: "plus", class: "primary" })
        : Object.assign(button("Start an app", () => undefined, { icon: "plus", class: "primary", title: "App pages are not here yet" }), { disabled: true }),
    ),
  );
}
// App pages arrive by registering their kind: the empty state's second button follows.
onTabKinds(() => {
  clear(empty);
  drawEmpty();
});

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
  const order = groups.tabs(); // group by group, as the rows show them
  if (!current || order.length < 2) return;
  show(order[(order.indexOf(current) + by + order.length) % order.length]!);
};
/** A document named by `index` (from 0, as "documents" lists them), else the one in front. */
const docArg = (args: Record<string, unknown>): Doc => {
  const at = num(args, "index");
  const doc = at === undefined ? current : docs[at];
  if (!doc) throw new Error(at === undefined ? "Nothing is open." : `There is no document ${at}.`);
  return doc;
};
const groupArg = (args: Record<string, unknown>, name = "group"): number => {
  const at = num(args, name);
  if (at === undefined) throw new Error(`Send ${name}: a group, from 0 in reading order ("documents" lists them).`);
  if (!groups.list()[at]) throw new Error(`There is no group ${at}: there ${groups.list().length === 1 ? "is 1 group" : `are ${groups.list().length} groups`}.`);
  return at;
};
const sideArg = (args: Record<string, unknown>): Side | undefined => {
  const side = text(args, "side");
  if (side === undefined) return undefined;
  if (side !== "left" && side !== "right" && side !== "up" && side !== "down") throw new Error('side is "left", "right", "up" or "down".');
  return side;
};
const hasTabs = (): boolean => groups.tabs().length > 0;
const manyGroups = (): boolean => groups.list().length > 1;

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
      group: groups.indexOf(d),
    })),
    // The tab groups in reading order: each one's documents (by index), the one in front, the focused one.
    groups: groups.list().map((g, index) => ({ index, documents: g.tabs.map((d) => docs.indexOf(d)), in_front: g.active ? docs.indexOf(g.active) : null, focused: g.focused })),
    panes: { ...layout.state(), data_panel: data.collapsed() ? "collapsed" : "open" },
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
  { id: "file.exportScript", group: "File", title: "Export as one Python script…", args: "path: where it goes (without it, the file chooser opens)", when: isCode, whyNot: "no notebook or script is in front", run: (a, from) => exportDocument(current, "script", text(a, "path"), from.agent) },
  { id: "file.exportNotebook", group: "File", title: "Export as one notebook…", args: "path: where it goes (without it, the file chooser opens)", when: isCode, whyNot: "no notebook or script is in front", run: (a, from) => exportDocument(current, "notebook", text(a, "path"), from.agent) },
  { id: "project.new", group: "Project", title: "New project…", args: "folder: where it goes; name: its name; notebooks: names of notebooks to make; app: false for no Streamlit app (without folder and name, the file chooser opens)", run: (a, from) => newProject(text(a, "folder"), text(a, "name"), Array.isArray(a.notebooks) ? (a.notebooks as string[]) : [], a.app !== false, from.agent) },
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
  { id: "doc.popOut", group: "Documents", title: "Open the document in its own window", when: () => !!current && moves(current), whyNot: "no notebook, script or Streamlit app is in front", run: () => popOut(current!) },
  { id: "doc.moveToMain", group: "Documents", title: "Move the document to the main window", when: () => !!current && moves(current) && !isMainWindow(), whyNot: "this is the main window, or nothing that moves is in front", run: () => moveToMain(current!) },
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
  { id: "snippet.insert", group: "Cell", title: "Insert a snippet…", args: "name: a snippet (blades_starters); values: {placeholder: value} (with them, no form: the agent's); number: the cell's own number (default: the selected cell, else a new one)", when: isCode, whyNot: "no notebook or script is in front", run: async (a, from) => {
    const name = text(a, "name");
    const values = (a.values && typeof a.values === "object" ? a.values : {}) as Record<string, unknown>;
    const number = num(a, "number");
    if (current?.notebook) {
      if (!name && !from.agent) return void current.notebook.insertSnippetHere();
      if (!name) throw new Error("Send the snippet's name (blades_starters lists them).");
      return { document: current.title, ...(await current.notebook.insertSnippet(name, values, number)) };
    }
    if (!name) throw new Error("Send the snippet's name (blades_starters lists them).");
    const filled = await api<FilledSnippet>(`/blades/${encodeURIComponent(name)}/snippet`, "POST", { values });
    if (filled.language === "dax") await script().addDax(datasetNames[0] ?? "", filled.text);
    else if (filled.language === "html") await script().addHtml(filled.text);
    else await script().addCode(filled.text, filled.cell_name ?? "");
    return { document: current!.title, language: filled.language, name: filled.cell_name };
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
  { id: "cell.name", group: "Cell", title: "Name the cell…", args: "number: the cell's own number (default: the selected cell, or the cursor's); name: one line (\"\" takes the name away; without it, the name is typed in place)", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
    const name = text(a, "name");
    const view = current?.notebook ?? script();
    if (name === undefined) return void view.editName();
    return view.nameCell(num(a, "number"), name);
  } },
  { id: "data.streamlitCells", agentOnly: true, group: "Data", title: "The Streamlit cells pane: its documents and cells, and the ones on the canvas page in front", run: () => {
    drawPane();
    const canvasDoc = markedCanvas();
    return { documents: paneDocuments, canvas: canvasDoc?.title ?? null, placed: [...document.querySelectorAll<HTMLElement>(".wb-st-cell.placed")].map((e) => ({ document: e.dataset.document, cell: Number(e.dataset.cell) })) };
  } },
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
  { id: "html.list", agentOnly: true, group: "HTML", title: "The document's HTML cells (and Markdown cells with names): each one's text, names and state", when: isCode, whyNot: "no notebook or script is in front", run: () => ({ document: current!.title, cells: tablesView().htmlCells() }) },
  { id: "html.run", group: "HTML", title: "Run an HTML cell (or a Markdown cell with names): fill its names and draw it", args: "number: the cell's own number (default: every one not up to date)", when: isCode, whyNot: "no notebook or script is in front", run: async (a) => ({ document: current!.title, cells: await tablesView().runHtml(num(a, "number")) }) },
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
  { id: "canvas.test", group: "Streamlit app", title: "Test this page (each filter's values)", args: "page: the page (its id; default: the one in front)", when: isCanvas, whyNot: NO_CANVAS, run: async (a) => {
    const done = await canvas().test(text(a, "page"));
    return done ?? canvas().report();
  } },
  { id: "canvas.moveToData", group: "Streamlit app", title: "Move a block's model work to data.ipynb", args: "block: the block's id (one with a thin hint)", when: isCanvas, whyNot: NO_CANVAS, run: async (a) => {
    const block = text(a, "block");
    if (!block) throw new Error("Send the block's id (workbench_canvas lists the blocks and their thin hints).");
    const plan = await canvas().moveToData(block);
    return plan ? { moved: plan.names, notebook: plan.notebook, document: plan.document, cell: plan.cell } : null;
  } },
  { id: "canvas.export", group: "Streamlit app", title: "Export an app that runs alone…", args: "folder: where it goes (without it, the file chooser opens)", when: isCanvas, whyNot: NO_CANVAS, run: (a, from) => canvas().exportApp(text(a, "folder"), from.agent) },
  { id: "canvas.saveAs", group: "Streamlit app", title: "Save as… (the project as one zip)", args: "path: the zip (without it, the file chooser opens)", when: isCanvas, whyNot: NO_CANVAS, run: (a, from) => canvas().saveAs(text(a, "path"), from.agent) },
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
  { id: "view.variables", group: "View", title: "Go to Variables", keys: "Ctrl+3", when: () => panelOn("workbench.variables"), whyNot: turnedOff("Variables"), run: () => layout.focus("variables") },
  { id: "view.nextPane", group: "View", title: "Next pane", keys: "F6", run: () => layout.cycle(1) },
  { id: "view.previousPane", group: "View", title: "Previous pane", keys: "Shift+F6", run: () => layout.cycle(-1) },
  { id: "view.toggleSidebar", group: "View", title: "Collapse or expand the Data panel", keys: "Ctrl+B", args: "collapsed: true or false (default: the other way)", when: () => panelOn("workbench.data"), whyNot: turnedOff("The Data panel"), run: (a) => ({ collapsed: data.toggle(typeof a.collapsed === "boolean" ? a.collapsed : undefined) }) },
  { id: "view.toggleRight", group: "View", title: "Show or hide Variables", args: "show: true or false (default: the other way)", when: () => panelOn("workbench.variables"), whyNot: turnedOff("Variables"), run: (a) => {
    const shown = layout.toggle("right", typeof a.show === "boolean" ? a.show : undefined);
    if (shown) void variables.refresh();
    drawStatus();
    return { shown };
  } },
  { id: "view.toggleConsole", group: "View", title: "Show or hide the console", args: "show: true or false (default: the other way)", when: () => panelOn("workbench.console"), whyNot: turnedOff("The Console"), run: (a) => {
    const shown = layout.toggle("console", typeof a.show === "boolean" ? a.show : undefined);
    drawStatus();
    return { shown };
  } },
  { id: "view.standard", group: "View", title: "Layout: standard", run: () => { layout.setLayout("standard"); drawStatus(); } },
  { id: "view.focus", group: "View", title: "Layout: source only", keys: "Ctrl+Shift+1", run: () => { layout.setLayout("focus"); drawStatus(); } },
  { id: "view.wide", group: "View", title: "Layout: wide data", run: () => { layout.setLayout("wide"); drawStatus(); } },
  // Groups: tabs side by side or stacked, as Visual Studio Code's editor groups
  { id: "group.splitRight", group: "Groups", title: "Split right: the tab moves to a new group on the right", keys: "Ctrl+\\", args: "index: a document (default: the one in front)", when: () => canSplit(current), whyNot: SPLIT_WHY, run: (a) => {
    splitDoc(docArg(a), "right");
    return { groups: groups.list().length, focused: groups.focusedIndex() };
  } },
  { id: "group.splitDown", group: "Groups", title: "Split down: the tab moves to a new group below", args: "index: a document (default: the one in front)", when: () => canSplit(current), whyNot: SPLIT_WHY, run: (a) => {
    splitDoc(docArg(a), "down");
    return { groups: groups.list().length, focused: groups.focusedIndex() };
  } },
  { id: "group.moveTab", group: "Groups", title: "Move a tab to another group", args: "group: the group, from 0 in reading order; index: a document (default: the one in front); position: its place in that group's row, from 0 (default: the end); side: left, right, up or down to split that side of the group instead", when: hasTabs, whyNot: "nothing is open", run: (a) => {
    const doc = docArg(a);
    const at = groupArg(a);
    const side = sideArg(a);
    if (side) {
      if (!groups.split(doc, side, at)) throw new Error(`It cannot split: ${SPLIT_WHY}.`);
    } else groups.move(doc, at, num(a, "position"));
    return { group: groups.indexOf(doc), groups: groups.list().length };
  } },
  { id: "group.moveToNext", group: "Groups", title: "Move the tab to the next group", when: manyGroups, whyNot: "there is one group", run: () => {
    const doc = docArg({});
    groups.move(doc, (groups.indexOf(doc) + 1) % groups.list().length);
  } },
  { id: "group.focus", group: "Groups", title: "Focus a group", args: "group: from 0, in reading order", when: hasTabs, whyNot: "nothing is open", run: (a) => groups.focusGroup(groupArg(a)) },
  { id: "group.focusNext", group: "Groups", title: "Focus the next group", when: manyGroups, whyNot: "there is one group", run: () => groups.focusGroup((groups.focusedIndex() + 1) % groups.list().length) },
  { id: "group.focusPrevious", group: "Groups", title: "Focus the previous group", when: manyGroups, whyNot: "there is one group", run: () => groups.focusGroup((groups.focusedIndex() - 1 + groups.list().length) % groups.list().length) },
  { id: "tab.moveLeft", group: "Groups", title: "Move the tab left in its row", args: "index: a document (default: the one in front)", when: hasTabs, whyNot: "nothing is open", run: (a) => groups.reorder(docArg(a), -1) },
  { id: "tab.moveRight", group: "Groups", title: "Move the tab right in its row", args: "index: a document (default: the one in front)", when: hasTabs, whyNot: "nothing is open", run: (a) => groups.reorder(docArg(a), 1) },
  // The Data panel: tables, the blades' variables
  { id: "data.list", agentOnly: true, group: "Data", title: "The Data panel's tables and variables", run: () => ({ tables: tables.map((t) => ({ name: t.name, rows: t.rows ?? null, source: t.source ?? "", steps: t.steps })), variables: bladeVariables.map((b) => ({ name: b.variable ?? b.name, blade: b.name, description: b.description })), collapsed: data.collapsed() }) },
  { id: "data.goToTable", group: "Data", title: "Go to a table's cell in the focused document", args: "table: the table's name", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
    const table = text(a, "table");
    if (!table) throw new Error("Send the table's name.");
    const line = tablesView().tables().find((t) => t.name === table);
    if (!line?.cell) throw new Error(`${table} has no cell in ${current!.title}.`);
    goToTable(table);
    return { table, cell: line.cell };
  } },
  { id: "data.openFile", group: "Data", title: "Open a file as a table…", args: "path: the file (without it, the file chooser opens)", run: async (a) => {
    const path = text(a, "path");
    if (!path) return openFile();
    const name = tableName(path);
    await api(`/datasets/${encodeURIComponent(name)}/load`, "POST", { path });
    return { table: name };
  } },
  { id: "data.browse", group: "Data", title: "Browse a connection's tables", args: "connection: its name (default: the catalog as it is)", run: (a) => browse(text(a, "connection")) },
  { id: "data.blades", group: "Data", title: "Show the blades and connections", run: () => data.flyout("blades") },
  { id: "data.closeFlyout", group: "Data", title: "Close the catalog or the blades beside the Data panel", when: () => data.flyoutShown() !== null, whyNot: "neither is open", run: () => data.flyout(null) },
  { id: "data.addConnection", group: "Data", title: "Add connection…", run: () => openConnections().then(() => void rail.loadBlades()) },
  { id: "view.variablesRefresh", group: "View", title: "Read the variables again", when: isCode, whyNot: "no notebook or script is in front", run: () => variables.refresh().then(() => variables.snapshot()) },
  // Help
  { id: "help.atCursor", group: "Help", title: "Help on the name at the cursor", keys: "F1", when: isCode, whyNot: "no notebook or script is in front", run: () => showHelp() },
  { id: "commands", agentOnly: true, group: "Help", title: "Every command and its arguments", run: () => allCommands().map((c) => ({ id: c.id, title: c.title, group: c.group, keys: c.keys ?? null, args: c.args ?? null, available: c.when ? c.when() : true })) },
];
registerCommands(COMMANDS);
registerCommands(betaCommands()); // beta mode on or off, Leave a note…, Export beta log…
// Beta mode (the beta log and Leave a note…) in this window too; nothing while it is off.
mountBeta("workbench", { window: POPPED ? "popout" : "main", tabs: () => docs.map((d) => kindOf(d)) });
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
  "Ctrl+\\": "group.splitRight",
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
  // A document moved back to this (the main) window from one it was popped out into.
  const handedTo = notice.type === "workbench_handoff" ? (notice as unknown as { to: string }).to : null;
  if (handedTo !== null && (handedTo === WINDOW_ID || (handedTo === "main" && isMainWindow()))) void takeDocument((notice as unknown as { id: string }).id).catch((e: Error) => {
      if (!(e instanceof ApiError && e.status === 409)) toast(e.message, "error"); // another main window took it
    });
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
  // A cell that calls Streamlit was typed, named, opened or closed somewhere: the pane follows.
  if (notice.type === "streamlit_cells") refreshPane();
  // An app's pages or run changed somewhere (a linked cell typed in another window, the agent).
  if (notice.type === "streamlit_changed") {
    for (const doc of docs) {
      doc.streamlit?.noticed((notice as unknown as { app: string }).app);
      doc.canvas?.noticed((notice as unknown as { app: string }).app);
    }
  }
});

// A panel turned off in Settings is gone (grid.css, by <body>'s class); an open console or Variables
// closes with it, and stays closed until it is turned on again and opened.
onPanels(() => {
  if (!panelOn("workbench.console") && layout.state().console) layout.toggle("console", false);
  if (!panelOn("workbench.variables") && layout.state().right) layout.toggle("right", false);
  drawStatus();
});

void Promise.all([
  loadPanels(),
  refreshHome(),
  loadConnections(),
  api<{ pythons: PythonChoice[] }>("/workbench/pythons").then((r) => (pythons = r.pythons), () => undefined),
]).then(() => {
  drawEmpty();
  refreshPane();
  // A document popped out into this window starts it fresh (a new window copies its opener's session).
  const fresh = openedWith.get("fresh") === "1";
  if (fresh) sessionStorage.removeItem(SESSION_KEY);
  void (fresh ? Promise.resolve(false) : restore()).then(() => {
    const wanted = openedWith.get("open"); // the address as opened (the page clears it once the token is read)
    if (wanted) void open(wanted);
    // A document popped out of another window: this window was opened to take it.
    const handed = openedWith.get("take");
    if (handed) void takeDocument(handed).catch((e: Error) => toast(e.message, "error"));
  });
});
