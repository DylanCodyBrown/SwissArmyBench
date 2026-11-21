/**
 * workbenchPage.ts: the Workbench, in a window of its own (Plans/workbench-and-connections.plan.md;
 * opened from the grid page's Workbench tab; redesigned 2026-11-15, docs/ideas.md). [COMPOSITION]
 *
 *   [TOP]      one row: the mark, the focused document's name (a dot while it has unsaved changes),
 *              Save, Save as…, and "…" (New notebook, New script, Open…, Recent, split, Commands)
 *   [DATA]     the Data Explorer on the left (workbenchExplorer.ts; Ctrl+Shift+E or the status bar opens
 *              it, beside every document; off until then): one search over everything that holds data
 *              (dataExplorer.ts), a project's files when there is one. "+ Table" (Open file…, a
 *              connection's tables, the catalog's search) and "+ Blade" open the side bar's old lists
 *              (catalogRail.ts) beside it. Pop out opens the Data page (dataPage.ts) in a window of its own
 *   [GROUPS]   the documents as tabs in groups (workbenchGroups.ts): drag a tab along a row, or to a
 *              group's edge to split it; splitters size them. The focused group's row ends with its
 *              document's controls: a notebook's "+ Cell", Run all and "…"; a script's "+ Cell", Run
 *              file and "…" (Open…, Recent, Interrupt, Restart, Save as…, the Streamlit app, split)
 *   [PANES]    after RStudio (workbenchLayout.ts): the focused document's console under the groups and
 *              Variables on the right, both closed until the status bar opens them (a run in the
 *              console opens it). Pictures go to Analyze
 *   [STATUS]   for the focused document: its kernel (a menu: Interrupt, Restart), its environment, the
 *              cursor; then the Console and Variables toggles
 *   [EMPTY]    nothing open: Start a notebook (and Start an app, once app pages are registered)
 *   [AGENT]    right-click an error or selected code: Send to the agent (workbenchAgent.ts)
 *   [DOC]      a notebook (workbenchNotebook.ts) or a script (workbenchScript.ts), each with its own
 *              console (workbenchConsole.ts) on its kernel; a blade being edited; a table from the catalog
 *   [COMMANDS] every action by one name (workbenchCommands.ts): the palette (Ctrl+Shift+P), the keys, and
 *              the agent's workbench_window tool; the groups' too (split right, split down, move a tab,
 *              focus a group) and the Data Explorer's
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
 *              Open project (its files as tabs, and listed at the Data Explorer's foot), Export data.py
 *   [POP OUT]  a saved document moves into a Workbench window of its own (the group's "…")
 *
 * ROUTING: /workbench/home, /open, /save, /pythons (routes_workbench.py); kernels in workbenchKernel.ts.
 */
import { inlineStatus } from "./inlineCompletion";
import { bringPage, type CodePage, openOnPage, PAGE_WINDOW, PAGE_WORDS, pageOfKind, pageOfPath, splitSession, thisPage, wrongPage } from "./workbenchPages";
import { mountCodeExplorer, type TreeFile } from "./codeExplorer";
import { ideMoves, searchScripts } from "./workbenchIde";
import { handleAgentNotice, loadApprovals } from "./agentAccess";
import { agentApi, api, ApiError, connect, onNotice, openedWith, requireSession, tellFocus, token } from "./api";
import type { FilledSnippet } from "./starters";
import { type BladeKind, type BladeSummary, editBlade, showTemplatePicker } from "./bladeEditor";
import { mountRail, schemaDetails, tableDetails, watchTheme } from "./catalogRail";
import { openConnections, setCellOpener } from "./connectionsWindow";
import { button, clear, h, icon, openDialog, toast } from "./dom";
import { closeWindow, inApp } from "./desktopApp";
import { chooseFile } from "./fileChooser";
import { openFile, tableName } from "./openFile";
import { effectiveTheme } from "./theme";
import { allCommands, answerAgent, type Command, mountShortcutKeys, openPalette, openShortcuts, registerCommands, runCommand, setAgentHooks } from "./workbenchCommands";
import { following, pulse, userBusy } from "./sessionPage";
import { consoleView, type ConsoleView } from "./workbenchConsole";
import { forgetCatalogs, listDatasets, pythonCompleter, setDialects } from "./workbenchCompletion";
import { onProblems, problemsOf, pythonIntel, ruffOffer } from "./workbenchIntel";
import { newEnvironment } from "./workbenchEnvironment";
import type { Fix } from "./workbenchErrors";
import { mountExplorerPane } from "./workbenchExplorer";
import { cellsPane } from "./workbenchCellsPane";
import { type ExplorerResult, type ExplorerState, openDataWindow } from "./dataExplorer";
import { openVariables } from "./variablesPage";
import { mountGroups, onTabKinds, registerTabKind, type SavedLayout, type Side, type TabKind, tabKinds } from "./workbenchGroups";
import { type CodeFileView, newCodeFile, openCodeFile } from "./workbenchCodeFile";
import { mountLayout } from "./workbenchLayout";
import { menuButton, type MenuEntry, openMenu } from "./workbenchMenu";
import { back, canGoBack, forward, go, goHome, HOME_WINDOW, mountNav, setTitle, startNav, withParams } from "./nav";
import { loadPanels, onPanels, panelOn, turnedOff } from "./panels";
import { mountNavRail } from "./rail";
import { type LandingDoc, mountLanding } from "./workbenchLanding";
import { watchConnectionColours } from "./connectionColours";
import { type Kind, kindIcon, kindOfPath, loadKindColours, notebookRole, notebookWord, onKindColours, projectOpen, setProjectFolder } from "./kindColours";
import { areaOfKind, gatedRun } from "./gates";
import { markBusy } from "./loading";
import { type Missing, type PromptOptions, promptInstall } from "./missingPackages";
import { openSettings } from "./settingsWindow";
import { betaCommands, betaOn, exportBetaLog, mountBeta, setBeta } from "./betaNotes";
import { installZoomInput } from "./zoom";
import { mountAppFooter } from "./appFooter";
import { updateCommands } from "./updates";
import { claudeCommands } from "./claudeLaunch";
import { setDocumentName } from "./workbenchAgent";
import { fetchTables, type TableInfo } from "./workbenchTables";
import { variablesPanel } from "./workbenchVariables";
import { Kernel, WINDOW_ID } from "./workbenchKernel";
import { type CellData, type CellKind, notebookView, type NotebookView } from "./workbenchNotebook";
import { scriptView, type ScriptView } from "./workbenchScript";
import { type Align, type Arrange, canvasView, type CanvasView, type DesignWidth, type Device, type Where } from "./workbenchCanvas";
import { drawOutline as drawCanvasOutline, drawToolbox } from "./canvasToolbox";
import { type LineageGraph, type LineageNode, type LineageTarget, closePlacedLineage, lineageNoticed, openLineage } from "./workbenchLineage";
import { type AppHost, appPanels } from "./workbenchApp";
import type { CodePlan } from "./canvasPane";
import { type Descriptions, type DictionaryTable, described, drawDictionary, drawLineageEmpty, drawOutline, drawRunHistory, drawRunSettings, type FlowState, type OutlineItem, readDictionary, readFlow, recordRunFile, runAsScheduled, runHistory, type RunRecord, runSettings } from "./workbenchDocModes";
import { fillSnippet } from "./starters";
import { excelView, type ExcelView, WORKBOOK_ENDING } from "./excelCanvas";
import { activeMode, canvasAnywhere, cellRoute, modes, offersCanvas, onMode, refreshMode, whenMode } from "./modes";
import { closeProject, copyProject, exportOutline, loadProject, mountProject, newProject as newProjectFolder, onBeforeSave, onProject, openProject as openProjectFolder, projectLabel, projectState, type ProjectState, reportLayout, saveProject } from "./projectFile";
import { starterGallery } from "./workbenchStarters";
import { importFile, openImport } from "./projectImport";
import { modeFrame, type ModeFrame } from "./workbenchModes";
import { type AppSettings, CELL_DRAG, draggedLink, type MovePlan, problemText, type PaneDocument, type SavedPage, StreamlitDoc, type StreamlitHost } from "./workbenchStreamlit";
import { installVariableAnywhere } from "./variableAnywhere";
import { errorHere, errorNote, errorToast } from "./errorNote";

// A variable in any box: typing ${ lists them, right-click inserts one (12.7).
installVariableAnywhere();

watchTheme();

interface Doc {
  id: number;
  kind: "notebook" | "script" | "app" | "blade" | "table" | "workbook" | "codefile";
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
  /** A workbook's design on the Excel canvas (the Accounting extension's; excelCanvas.ts). */
  workbook?: ExcelView;
  /** Its mode's own panels (workbenchModes.ts): beside it in its group. */
  modes?: ModeFrame;
  /** App mode: Properties and State share the live page's state. */
  app?: ReturnType<typeof appPanels>;
  /** A code app's file (workbenchCodeFile.ts, the Power Apps extension's plug-in): TypeScript or TSX. */
  codefile?: CodeFileView;
  /** Its file's text's hash as this window last read or wrote it (the file_changed notice is compared). */
  hash?: string | null;
  /** Its file changed elsewhere while it had unsaved edits (or is gone): Save waits for the choice. */
  elsewhere?: { hash: string | null; bar: HTMLElement };
}

interface PythonChoice {
  python: string;
  version: string;
  ipykernel: boolean;
  swissarmybench: boolean;
}

const top = document.getElementById("wb-top") as HTMLElement;
// Notebooks and Scripts are two pages (the owner, 2026-11-21: "notebooks and scripts should not reuse the
// same page they are seperate things"): this window is one of them (its path says which, workbenchPages.ts).
const PAGE: CodePage = thisPage();
document.body.dataset.page = PAGE;
// An address that names the other page's file (an old /workbench#open=load.py): this tab goes to that page,
// the address's words with it, before anything is drawn.
{
  const asked = openedWith.get("open");
  const there = pageOfPath(asked);
  if (asked && there && there !== PAGE && !openedWith.get("take")) {
    const words = new URLSearchParams(openedWith);
    if (token && !words.get("token")) words.set("token", token);
    location.replace(`/${there}${location.search}#${words.toString()}`);
  }
}
// No top bar (the owner, 2026-11-21, on the Scripts landing: "without all of this at the top"): Save and
// Save as are a document's own (its "…" menu, Ctrl+S and Ctrl+Shift+S); New is the creator and the explorer.
top.hidden = true;
// The explorer's marks and outline (codeExplorer.ts, mounted further down): called from the first draw on.
const codexHooks = { label: (_label: string): void => undefined, mark: (): void => undefined, typed: (_path: string, _text: string): void => undefined, refresh: (): void => undefined };
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
let bladeVariables: BladeSummary[] = []; // the blades that are not connections
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
    vaultNames = every.filter((b) => b.connection === "vault").map((b) => b.name);
  } catch {
    connectionNames = [];
    workspaceNames = [];
    bladeNames = [];
    codeNames = [];
    bladeVariables = [];
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
        assignTables();
      },
      () => undefined, // the server is away: the cells stay as they are
    );
  }, 120);
}

/** A table open in Grids given to `doc`: its read-only cell joins the document's Tables group (the error
 *  panel's "orders is open in Grids: add its table cell", and tables.add). Its cell already in another
 *  document stays there, and that is said. */
async function giveTable(doc: Doc, name: string): Promise<string> {
  tables = await fetchTables();
  const info = tables.find((t) => t.name === name) ?? tables.find((t) => t.name.toLowerCase() === name.toLowerCase());
  if (!info) throw new Error(`${name} is not open in Grids.`);
  const owner = tableOwner.get(info.name);
  if (owner && owner !== doc && docs.includes(owner)) throw new Error(`${info.name}'s cell is in ${owner.title}.`);
  tableOwner.set(info.name, doc);
  tablesSent.delete(doc);
  assignTables();
  return info.name;
}

/** The group row's word on the focused document's tables: Run tables, when one is not up to date. */
function drawTablesTool(): void {
  const view = current ? viewOf(current) : undefined;
  const waiting = view ? view.tables().filter((t) => t.state === "outOfDate" || t.state === "notRun" || t.state === "notRunSinceOpening") : [];
  const stale = waiting.filter((t) => t.state === "outOfDate").length;
  clear(
    tablesHost,
    waiting.length
      ? button(stale ? `Run tables: ${stale} out of date` : `Run tables: ${waiting.length} not run`, () => void view!.runOutOfDate().catch((e: Error) => errorHere(e)), {
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
// The Streamlit cells pane (App mode's panel): what the server last listed, the canvas its marks are for.
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
      dictionary: () => (isData(doc) ? (dataViews.get(doc)?.dictionary ?? null) : null),
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
  if (state.problem?.kind === "failed") errorHere(problemText(state.problem));
  // Streamlit missing from the document's Python: the prompt in the user's face (it installs, then runs).
  if (state.problem?.kind === "missing") void promptInstall(state.problem, streamlitInstall(doc));
  return state.running && !state.problem;
}

/** Into the document's own Python, through its app (which runs again once it is in). */
const streamlitInstall = (doc: Doc): PromptOptions => ({
  install: async () => {
    await doc.streamlit?.install();
  },
});

/** A live cell's Install: the prompt again, asked for (after Not now). */
async function installStreamlit(doc: Doc): Promise<void> {
  const problem = doc.streamlit?.state?.problem;
  if (problem?.kind === "missing") void promptInstall(problem, { ...streamlitInstall(doc), force: true });
}

const streamlitHost = (doc: Doc): StreamlitHost => ({
  state: () => doc.streamlit?.state ?? null,
  changed: () => doc.streamlit?.syncSoon(),
  isLive: (cell) => doc.streamlit?.isLive(cell) ?? Promise.resolve(false),
  run: () => runApp(doc),
  install: () => void installStreamlit(doc),
  link: () => ({ document: doc.path, title: doc.title }),
  addToApp: async (cell) => {
    // The cell's document is saved (a block links to a file), then placed on the app in front (else the
    // first open one, else a new one).
    if (!(await save(doc))) throw new Error(`${doc.title} could not be saved.`);
    await doc.streamlit?.sync().catch(() => null);
    const app = (current?.canvas ? current : null) ?? docs.find((d) => d.canvas) ?? openApp(null, [], null);
    show(app);
    await app.canvas!.place({ document: doc.path, cell, title: doc.title });
  },
});

/** A Streamlit app: its canvas as a document of its own. */
function openApp(path: string | null, pages: SavedPage[], modified: number | null, settings?: AppSettings): Doc {
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
      doc.app?.refresh(); // Properties and State follow the canvas
      doc.modes?.redraw("outline");
    },
    moveToData: (plan) => moveToData(plan, doc),
    applyCode: (plan) => applyCode(doc, plan, false),
    lineage: (page, block) => void showLineage({ app: doc.canvas?.app() ?? undefined, page, block }),
    selected: () => {
      doc.modes?.redraw("properties");
      doc.modes?.redraw("outline");
    },
    starter: (name, where) => void addStarter(doc, name, where).catch((e: Error) => errorHere(e)),
    toolbox: (element, where) => addElement(doc, element, where),
  }, settings);
  doc.element.append(doc.canvas.element);
  doc.modes = modeFrame(doc.element, () => doc === current && drawStatus());
  doc.app = appPanels(doc.modes, () => doc.canvas!, appHost(doc));
  // On its left (they were the Data panel's): the cells to build a page from, or the starter gallery.
  doc.modes.add({ id: "cells", title: "Streamlit cells", label: "Cells", icon: "page", where: "left", panel: "workbench.streamlit", draw: (body) => body.replaceChildren(streamlitCells.element) });
  doc.modes.add({ id: "starters", title: "Starters", icon: "star", where: "left", panel: "workbench.starters", draw: (body) => body.replaceChildren(gallery.element) });
  // The designer (2026-11-19): the Toolbox (every Streamlit element and container) and the Document Outline.
  doc.modes.add({ id: "toolbox", title: "Toolbox", icon: "plus", where: "left", panel: "workbench.starters", draw: (body) => drawToolbox(body, () => doc.canvas!, () => doc.modes?.toggle("starters", true)) });
  doc.modes.add({ id: "outline", title: "Document Outline", label: "Outline", icon: "outline", where: "left", panel: "workbench.properties", draw: (body) => drawCanvasOutline(body, () => doc.canvas!) });
  doc.modes.toggle("cells", true);
  show(doc);
  return doc;
}

/** A workbook's design (workbook.design.json) on the Excel canvas: offered while the open project's mode
 *  names the canvas (modes.ts); a design opened by its file opens whatever the mode. */
function openWorkbook(path: string | null): Doc {
  const doc = makeDoc("workbook", path ? baseName(path) : `Untitled workbook ${counter + 1}`, path, null);
  doc.workbook = excelView(path, {
    path: () => doc.path,
    title: () => (doc.path ? baseName(doc.path).slice(0, -WORKBOOK_ENDING.length) : project?.name ?? doc.title),
    changed: (dirty) => {
      if (doc.dirty === dirty) return;
      doc.dirty = dirty;
      drawTabs();
    },
    chooseSave: () => chooseFile({ title: "Save workbook design", mode: "save", start: doc.path ?? project?.folder ?? homeFolder, name: `workbook${WORKBOOK_ENDING}` }).then((p) => (p && !p.toLowerCase().endsWith(".json") ? p + WORKBOOK_ENDING : p)),
    saved: (saved, modified) => {
      doc.path = saved;
      doc.modified = modified;
      doc.title = baseName(saved);
      doc.dirty = false;
      drawTabs();
      void refreshHome();
    },
    drew: () => {
      if (doc === current) drawStatus();
    },
  });
  doc.element.append(doc.workbook.element);
  show(doc);
  return doc;
}

const workbookInFront = (): ExcelView => {
  if (!current?.workbook) throw new Error("No workbook is in front.");
  return current.workbook;
};

/** The canvases' "New" entries follow the open project's mode (modes.ts): each is offered only where the
 *  mode names it (the base's: the Streamlit canvas; an Accounting project's: the Excel canvas). */
function registerCanvasKinds(): void {
  registerTabKind({ id: "page", label: "App page", icon: "page", mark: "app", ...(offersCanvas("streamlit") ? { start: { label: "New Streamlit app", run: () => void openApp(null, [], null) } } : {}) });
  registerTabKind({ id: "workbook", label: "Workbook", icon: "excel", mark: "app", ...(offersCanvas("excel") ? { start: { label: "New Excel workbook", run: () => void openWorkbook(null) } } : {}) });
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

// A project opened or closed: the notebooks' kinds (data, app, plain) follow: their tabs, the Data
// Explorer's files and the landing.
onKindColours(() => {
  drawTabs();
  if (project) listProject();
  landing.redraw();
  drawTop();
});

/** The project's files in the Data Explorer: data.ipynb, data.py set in as its output, the app's canvas,
 *  the notebooks and scripts. */
function listProject(): void {
  setProjectFolder(project?.folder ?? null);
  refreshPane(); // the project's files are the pane's too
  if (!project) return void explorerPane.setFiles(null);
  const files = project.files.flatMap((path) => {
    const name = baseName(path);
    const file = { path: name, icon: kindIcon(kindOfPath(name), path), word: kindOfPath(name) === "notebook" ? notebookWord(path) : undefined, open: () => void open(path) };
    // data.py is data.ipynb's export: listed under it, greyed, never opened from here.
    return name.toLowerCase() === DATA_NOTEBOOK ? [file, { path: "data.py", icon: "code", derived: true }] : [file];
  });
  // The mode's own files a person edits (a code app's .ts and .tsx under src/), opened in the code editor.
  for (const path of modeFiles) files.push({ path, icon: "code", word: undefined, open: () => void openCodeFileDoc(path) });
  explorerPane.setFiles({ root: `${project.name}/`, files });
}

let modeFiles: string[] = [];

/** The files the mode lists for the open project (its route), then the list drawn again. */
async function loadModeFiles(): Promise<void> {
  const route = activeMode().mode.project_files;
  let found: string[] = [];
  if (route && project) {
    try {
      found = (await api<{ files: string[] }>(route)).files ?? [];
    } catch {
      found = [];
    }
  }
  modeFiles = found;
  listProject();
}

/** Open project…: a project's folder, opened as THE project (projectFile.ts); its documents open here
 *  (followProject). */
async function openProject(folder?: string): Promise<ProjectFiles | null> {
  const opened = await openProjectFolder(folder);
  if (!opened?.project) return null;
  return api<ProjectFiles>("/projects/open", "POST", { folder: opened.project.folder, remember: false });
}

/** New project: a folder scaffolded and opened as THE project. Without a name, New project's dialog
 *  (name, type, where). `agent`: the agent asked (workbench_window). */
async function newProject(folder?: string, name?: string, notebooks: string[] = [], app?: boolean, agent = false, type?: string): Promise<ProjectFiles | null> {
  if (!name) {
    const made = await newProjectFolder();
    if (!made?.project) return null;
    return api<ProjectFiles>("/projects/open", "POST", { folder: made.project.folder, remember: false });
  }
  const body = { name, ...(folder ? { folder } : {}), notebooks, ...(app !== undefined ? { app } : {}), ...(type ? { type } : {}) };
  const made = await (agent ? agentApi : api)<ProjectState & ProjectFiles>("/project/new", "POST", body);
  await loadProject();
  return made;
}

/** Export data.py: written again from the project's data.ipynb, as it stands here. */
async function exportData(): Promise<unknown> {
  const data = docs.find(isData);
  const folder = data?.path ? folderOf(data.path) : project?.folder;
  if (!folder) throw new Error("No project is open (a folder with a data.ipynb).");
  await settleDocuments();
  const done = await api<{ path: string; names: string[]; fill_in: string[]; skipped: string[] }>("/projects/export-data", "POST", { folder });
  for (const said of done.skipped) toast(said);
  if (done.fill_in.length) errorHere(`data.py cannot read ${done.fill_in.join(", ")} again: add the code that reads it to data.ipynb.`);
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
  /** Each connection it uses that runs only on this computer (domain/portability.py), in one paragraph. */
  local?: { connection: string; local: { key: string; reason: string; instead: string; words: string }[] }[];
  local_words?: string;
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
  // A connection it uses that runs only on this computer is said before anything is written (the owner,
  // 2026-11-17: "this is meant to scale to a function app or up to a hosted streamlit application").
  if (!agent) {
    const looked = await call<ExportAnswer>("/workbench/export-script", "POST", { ...body, check: true });
    if (looked.local_words && !confirm(`${looked.local_words}\n\nExport it anyway?`)) {
      toast("Nothing was exported.");
      return null;
    }
  }
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
  const guarded = (act: () => Promise<unknown>) => (): void => void act().catch((e: Error) => errorHere(e));
  const open = docs.some(isData) || !!project;
  return [
    { label: "New project…", icon: "plus", title: "A folder that starts with data.ipynb", run: guarded(() => newProject()) },
    // Each other project type this app can make (an extension's: modes.ts), its deliverable said.
    ...modes()
      .filter((m) => m.type !== "bi")
      .map((m) => ({ label: `New ${m.name} project…`, icon: "plus", title: `Its deliverable: ${m.deliverable}`, run: guarded(() => newProject(undefined, undefined, [], false, false, m.type)) })),
    { label: "Open project…", icon: "folder", run: guarded(() => openProject()) },
    { label: "Export data.py", icon: "export", disabled: !open, title: open ? "Written again from data.ipynb" : "No project is open", run: guarded(exportData) },
    ...(sabOpen()
      ? [
          null,
          { label: "Copy project to…", icon: "copy", run: guarded(() => copyProject()) },
          { label: "Export outline", icon: "outline", title: "ARCHITECTURE.md: the project for someone joining it", run: guarded(() => exportOutline()) },
          { label: "Close project", icon: "close", run: guarded(() => closeProject()) },
        ]
      : []),
  ];
}

// ----- a project folder (projectFile.ts): its documents open here, its layout is kept, and
// Save covers it (the owner, 2026-11-16) -----

const SAB_KEY = "workbench-sab";
let sab: { serial: number; folder: string | null } = (() => {
  try {
    return (JSON.parse(sessionStorage.getItem(SAB_KEY) ?? "null") as { serial: number; folder: string | null } | null) ?? { serial: -1, folder: null };
  } catch {
    return { serial: -1, folder: null };
  }
})();

const sabOpen = (): boolean => !!projectState().project;
const inFolder = (path: string | null, folder: string | null): boolean => !!path && !!folder && (path.startsWith(`${folder}/`) || path.startsWith(`${folder}\\`));
const relativeTo = (path: string, folder: string): string => path.slice(folder.length + 1).replace(/\\/g, "/");
const joinPath = (folder: string, relative: string): string => {
  const sep = folder.includes("\\") && !folder.includes("/") ? "\\" : "/";
  return `${folder}${sep}${relative.split("/").join(sep)}`;
};

/** The open project's documents (and its groups) as the window reports them for the next save. */
function sabLayout(): { layout: Record<string, unknown>; unsaved: string[] } | null {
  const open = projectState().project;
  if (!open) return null;
  const mine = docs.filter((d) => (d.notebook || d.script || d.canvas) && inFolder(d.path, open.folder));
  // Each page's own (the Notebooks page's and the Scripts page's), beside the other's as it was kept.
  const kept = (open.layout?.workbench ?? {}) as Record<string, unknown>;
  const other: CodePage = PAGE === "scripts" ? "notebooks" : "scripts";
  return {
    layout: {
      ...(kept[other] ? { [other]: kept[other] } : {}),
      [PAGE]: {
        documents: mine.map((d) => relativeTo(d.path!, open.folder)),
        groups: groups.save((d) => (mine.includes(d) ? mine.indexOf(d) : null)),
        current: current && mine.includes(current) ? mine.indexOf(current) : null,
      },
    },
    unsaved: mine.filter((d) => d.dirty).map((d) => d.title),
  };
}

function reportSab(): Promise<void> {
  const now = sabLayout();
  return now ? reportLayout("workbench", now.layout, now.unsaved) : Promise.resolve();
}

/** A project opened or closed (here, on the home page, by the agent): its documents open here as they
 *  were saved, and the last one's close. Their unsaved changes were asked about already. */
async function followProject(state: ProjectState): Promise<void> {
  const opened = state.project;
  drawTop();
  if (opened && opened.serial === sab.serial && opened.folder === sab.folder) return;
  if (sab.folder) {
    for (const doc of docs.filter((d) => inFolder(d.path, sab.folder))) close(doc, true);
    if (project?.folder === sab.folder) {
      project = null;
      listProject();
    }
  }
  sab = { serial: opened ? opened.serial : -1, folder: opened ? opened.folder : null };
  try {
    sessionStorage.setItem(SAB_KEY, JSON.stringify(sab));
  } catch {
    /* storage refused: a reload opens the documents again */
  }
  if (!opened) return;
  const listed = await api<ProjectFiles>("/projects/open", "POST", { folder: opened.folder, remember: false }).catch(() => null);
  if (listed) {
    project = listed;
    listProject();
    void loadModeFiles(); // the mode's own files (a code app's), for this project
  }
  // This page's documents as kept (a project from before the two pages: its list, this page's kind only).
  type Kept = { documents?: string[]; groups?: SavedLayout };
  const all = opened.layout.workbench as (Kept & Partial<Record<CodePage, Kept>>) | undefined;
  const own = all?.[PAGE];
  const saved: Kept | undefined = own ?? (all?.documents ? { documents: all.documents } : undefined);
  const wanted = (saved?.documents?.length ? saved.documents.map((relative) => joinPath(opened.folder, relative)) : (listed?.files ?? [])).filter((p) => (pageOfPath(p) ?? PAGE) === PAGE);
  const byKey = new Map<number, Doc>();
  for (const [key, path] of wanted.entries()) {
    await open(path);
    const doc = docs.find((d) => d.path === path);
    if (doc) byKey.set(key, doc);
  }
  if (saved?.groups && byKey.size) groups.restore(saved.groups, (key) => byKey.get(key));
  const front = docs.find((d) => d.path === listed?.data);
  if (!saved?.groups && front) show(front);
  drawTabs();
  void reportSab();
}

/** Save: the project when one is open and the document in front is one of its own (or nothing is in
 *  front); else the document. */
/** Save: the document in front (a project's documents are its own files, saved by their own Save), then
 *  the open project's .sab/ quietly; with nothing in front, the project (Save as: Copy project to…). */
async function saveFront(as = false): Promise<unknown> {
  const opened = projectState().project;
  if (opened && !current) return as ? copyProject() : saveProject();
  const done = await save(current, as);
  if (opened && !as && inFolder(current?.path ?? null, opened.folder)) await api("/project/save", "POST", {}).catch(() => undefined);
  return done;
}

/** The project's documents with unsaved changes, saved (the server asks before it writes .sab/). */
async function saveProjectDocuments(folder: string | undefined): Promise<{ saved: number }> {
  let saved = 0;
  for (const doc of docs.filter((d) => d.dirty && inFolder(d.path, folder ?? projectState().project?.folder ?? null))) {
    if (await save(doc)) saved += 1;
  }
  return { saved };
}

// ===== the Workbench's modes (2026-11-15): App, Notebook, Script and Data =====
// Each document's own panels sit beside it in its group (workbenchModes.ts), so they follow the group;
// the status bar's toggles are the focused document's.

/** App mode's reach into the rest of the window: a block's cell, renamed or gone to; the logo's file. */
function appHost(doc: Doc): AppHost {
  return {
    lineage: (block) => void showLineage({ app: doc.canvas?.app() ?? undefined, page: (doc.canvas?.report() as { page?: string } | undefined)?.page ?? undefined, block }).catch((e: Error) => errorHere(e)),
    goToCell: (document, cell, line) => void goToCell(document, baseName(document), cell, line).catch((e: Error) => errorHere(e)),
    applyCode: (plan) => applyCode(doc, plan),
    openVariable: (name) => openVariables(name),
    openConnection: (name) => void openConnections({ detail: name }).then(() => void rail.loadBlades()),
    openGrid: (grid) => showGridAtHome(grid),
    sources: (kind) => (kind === "dax" ? datasetNames : connectionNames),
    setConnection: async (document, cell, connection) => {
      let held = docs.find((d) => d.path === document);
      if (!held) {
        await open(document);
        held = docs.find((d) => d.path === document);
        if (doc.canvas) show(doc);
      }
      if (!held?.notebook) throw new Error(`${baseName(document)} is not open.`);
      held.notebook.setCellConnection(cell, connection);
      held.streamlit?.syncSoon();
    },
    renameCell: async (document, cell, name) => {
      let held = docs.find((d) => d.path === document);
      if (!held) {
        await open(document);
        held = docs.find((d) => d.path === document);
        if (doc.canvas) show(doc); // the canvas stays in front
      }
      const view = held ? viewOf(held) : undefined;
      if (!held || !view) throw new Error(`${baseName(document)} is not open.`);
      view.nameCell(cell, name);
      held.streamlit?.syncSoon();
    },
    chooseLogo: async () => {
      const path = await chooseFile({ title: "Logo", mode: "file", suffixes: [".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"], start: folderOf(doc.path) });
      if (!path || !doc.path) return path;
      const folder = folderOf(doc.path);
      return path.startsWith(folder) ? path.slice(folder.length + 1).replace(/\\/g, "/") : path;
    },
  };
}

/** The project's mockups notebook (where a starter dropped on a canvas is written as a cell): an open
 *  notebook beside the app whose name says mockups, else that file, else a new one, saved. */
async function mockupsDoc(app: Doc): Promise<Doc> {
  if (!app.path) throw new Error("Save the app first: a starter becomes a cell of a notebook beside it.");
  const folder = folderOf(app.path);
  const near = (d: Doc): boolean => !!d.notebook && !!d.path && folderOf(d.path) === folder;
  const found = docs.find((d) => near(d) && /mock/i.test(d.title)) ?? null;
  if (found) return found;
  const sep = app.path.includes("\\") ? "\\" : "/";
  const files = project?.files ?? [];
  const named = `${folder}${sep}app mockups.ipynb`;
  const onDisk = files.find((f) => /mock/i.test(baseName(f)) && f.toLowerCase().endsWith(".ipynb")) ?? named;
  // A mockups notebook already there (in the project, or by its usual name) is opened, never replaced.
  const there = await api("/workbench/open", "POST", { path: onDisk }).then(() => true, () => false);
  if (there) {
    await open(onDisk);
    const opened = docs.find((d) => d.path === onDisk || baseName(d.path ?? "") === baseName(onDisk));
    if (opened) return opened;
  }
  const made = openNotebook(named, [], null);
  made.title = "app mockups.ipynb";
  made.notebook!.add("code", "from data import *", true);
  if (!(await save(made))) throw new Error("The mockups notebook could not be saved.");
  return made;
}

/** A starter dropped on a canvas: filled (its form, or the agent's values), written as a real named
 *  cell of the mockups notebook, saved, and placed where it was dropped. */
async function addStarter(app: Doc, name: string, where?: Where, values?: Record<string, unknown>): Promise<unknown> {
  const notebookDoc = await mockupsDoc(app);
  const view = notebookDoc.notebook!;
  if (values === undefined) {
    const filled = await fillSnippet(name);
    if (!filled) return null;
    view.select(view.cells().length - 1);
    view.add("code", filled.text);
    const at = view.selected();
    const number = view.cells()[at]?.number;
    if (typeof number !== "number") throw new Error("The cell was not made.");
    if (filled.cell_name) view.nameCell(number, filled.cell_name);
    return placeStarter(app, notebookDoc, number, where);
  }
  view.select(view.cells().length - 1);
  const made = await view.insertSnippet(name, values);
  return placeStarter(app, notebookDoc, made.cell, where);
}

/** The app notebook (where a Toolbox element's cell is written): the first notebook the canvas links to
 *  that is not data.ipynb, else app.ipynb beside the app, else the mockups notebook. */
async function appNotebookDoc(app: Doc): Promise<Doc> {
  if (!app.path) throw new Error("Save the app first: an element becomes a cell of a notebook beside it.");
  const folder = folderOf(app.path);
  const sep = app.path.includes("\\") ? "\\" : "/";
  const linked = (app.canvas?.state()?.pages ?? []).flatMap((p) => p.blocks.map((b) => b.document)).find((d) => d.toLowerCase().endsWith(".ipynb") && baseName(d).toLowerCase() !== "data.ipynb");
  for (const path of [linked, `${folder}${sep}app.ipynb`]) {
    if (!path) continue;
    const held = docs.find((d) => d.path === path && d.notebook);
    if (held) return held;
    if (await api("/workbench/open", "POST", { path }).then(() => true, () => false)) {
      await open(path);
      const opened = docs.find((d) => d.path === path && d.notebook);
      if (opened) return opened;
    }
  }
  return mockupsDoc(app);
}

/** A Toolbox element dropped on a canvas (or clicked): its cell (the server's: names free of every linked
 *  cell's) written into the app notebook under its own name, saved, and its block placed where it was dropped. */
async function addElement(app: Doc, element: string, where?: Where): Promise<unknown> {
  const id = app.canvas?.app();
  if (!id) throw new Error("The app is not open yet.");
  const notebookDoc = await appNotebookDoc(app);
  const made = await api<{ code: string; name: string; variable: string | null; kind: "code" | "sql" | "dax" }>(`/streamlit/apps/${encodeURIComponent(id)}/toolbox`, "POST", { element });
  // A SQL or DAX query: a %%sql or %%dax cell, on the first connection (a DAX cell: its first dataset).
  const cell = notebookDoc.notebook!.appendNamed(made.code.replace(/\n+$/, ""), made.name, made.kind ?? "code");
  const placed = (await placeStarter(app, notebookDoc, cell, where)) as { document: string | null; cell: number };
  return { ...placed, name: made.name, variable: made.variable };
}

async function placeStarter(app: Doc, notebookDoc: Doc, cell: number, where?: Where): Promise<unknown> {
  if (!(await save(notebookDoc))) throw new Error(`${notebookDoc.title} could not be saved.`);
  await notebookDoc.streamlit?.sync().catch(() => null);
  show(app);
  await app.canvas!.place({ document: notebookDoc.path, cell, title: notebookDoc.title }, where);
  return { document: notebookDoc.path, cell };
}

// ----- Notebook mode: the run order (edited, out of date), the Outline, Run up to here, Present

interface Flow {
  cells: FlowState[];
  outline: OutlineItem[];
}
const flows = new Map<Doc, Flow>();
const flowTimers = new Map<Doc, number>();

function flowSoon(doc: Doc): void {
  if (!doc.notebook) return;
  const was = flowTimers.get(doc);
  if (was !== undefined) window.clearTimeout(was);
  flowTimers.set(doc, window.setTimeout(() => {
    flowTimers.delete(doc);
    void refreshFlow(doc);
  }, 300));
}

async function refreshFlow(doc: Doc): Promise<Flow | null> {
  if (!doc.notebook || !docs.includes(doc)) return null;
  try {
    const read = await readFlow(doc.notebook.flowCells());
    flows.set(doc, read);
    doc.notebook.markFlow(read.cells);
    doc.modes?.redraw("outline");
    return read;
  } catch {
    return null;
  }
}

function notebookModes(doc: Doc): void {
  doc.modes = modeFrame(doc.element, () => doc === current && drawStatus());
  doc.modes.add({
    id: "outline",
    title: "Outline",
    icon: "outline",
    where: "side",
    panel: "workbench.outline",
    draw: (body) => {
      const flow = flows.get(doc);
      const view = doc.notebook!;
      const at = view.selected();
      const selectedNumber = at >= 0 ? (view.cells()[at]?.number ?? null) : null;
      drawOutline(body, flow?.outline ?? [], flow?.cells ?? [], selectedNumber, view.tables().length > 0, (n) => void view.goTo(n), () => {
        view.foldTables(false);
        const first = view.cells().find((c) => c.role === "tables");
        if (first?.number) view.goTo(first.number);
      });
    },
  });
  void refreshFlow(doc);
}

/** Present: the notebook as a document, the Data Explorer closed while it shows. */
let openBeforePresent: boolean | null = null;
function present(doc: Doc, on?: boolean): boolean {
  const now = doc.notebook!.present(on);
  doc.element.classList.toggle("presenting", now);
  if (now && openBeforePresent === null) {
    openBeforePresent = explorerPane.isOpen();
    if (openBeforePresent) explorerPane.toggle(false);
  } else if (!now && openBeforePresent !== null) {
    if (openBeforePresent) explorerPane.toggle(true);
    openBeforePresent = null;
  }
  drawControls();
  return now;
}

// ----- Script mode: run settings, Run as scheduled, run history

const historyAt = new Map<Doc, { at: number }>();
let vaultNames: string[] = [];

function scriptModes(doc: Doc): void {
  doc.modes = modeFrame(doc.element, () => doc === current && drawStatus());
  const chosen = { at: 0 };
  historyAt.set(doc, chosen);
  doc.modes.add({ id: "runSettings", title: "Run settings", icon: "sliders", where: "side", panel: "workbench.runSettings", draw: (body) => drawRunSettings(body, doc.path, vaultNames, () => void readArguments(doc)) });
  doc.modes.add({ id: "runHistory", title: "Run history", icon: "history", where: "bottom", panel: "workbench.runHistory", draw: (body) => drawRunHistory(body, doc.path, () => void runScheduled(doc), chosen) });
}

/** Run as scheduled: saved first, then the script as a fresh process with no app; the history shows it. */
async function runScheduled(doc: Doc): Promise<RunRecord | null> {
  if (!doc.script) return null;
  if ((doc.dirty || !doc.path) && !(await save(doc))) return null;
  scheduling.add(doc);
  drawControls();
  try {
    const run = await runAsScheduled(doc.path!, doc.python);
    historyAt.get(doc)!.at = 0;
    if (!doc.modes?.isOpen("runHistory")) doc.modes?.toggle("runHistory", true);
    else doc.modes.redraw("runHistory");
    if (run.exit_code !== 0) errorHere(`Exit code ${run.exit_code ?? "stopped"}`);
    return run;
  } catch (e) {
    errorHere(e);
    return null;
  } finally {
    scheduling.delete(doc);
    drawControls();
  }
}
const scheduling = new Set<Doc>();
const scriptArguments = new Map<Doc, string>();

/** The run settings' arguments, for Run file (read when the script opens and when its settings change). */
async function readArguments(doc: Doc): Promise<void> {
  if (!doc.path) return;
  try {
    scriptArguments.set(doc, (await runSettings(doc.path)).arguments);
  } catch {
    /* a script that cannot be read: no arguments */
  }
}

// ----- Data mode (data.ipynb): Cells | Lineage | Dictionary

type DataView = "cells" | "lineage" | "dictionary";
const dataViews = new Map<Doc, { view: DataView; host: HTMLElement; chosen: { table: string | null }; dictionary: Descriptions }>();

/** What data.ipynb saves beside its cells: its data dictionary's descriptions. */
function dataBody(doc: Doc): { dictionary?: Descriptions } {
  const held = dataViews.get(doc);
  return held && isData(doc) ? { dictionary: held.dictionary } : {};
}

function dataMode(doc: Doc, dictionary: Descriptions): void {
  const host = h("div", { class: "wb-data-view", hidden: true });
  doc.element.append(host);
  dataViews.set(doc, { view: "cells", host, chosen: { table: null }, dictionary });
}

function setDataView(doc: Doc, view: DataView): DataView {
  const held = dataViews.get(doc);
  if (!held || !doc.notebook) throw new Error("The document in front is not a project's data.ipynb.");
  held.view = view;
  doc.notebook.element.hidden = view !== "cells";
  held.host.hidden = view === "cells";
  doc.element.classList.toggle("data-view", view !== "cells");
  if (view !== "lineage") closePlacedLineage();
  if (view === "dictionary") void drawDictionaryView(doc);
  else if (view === "lineage") void dataLineage(doc, held.host).catch(() => undefined);
  drawControls();
  return view;
}

async function dictionaryTables(doc: Doc): Promise<DictionaryTable[]> {
  const held = dataViews.get(doc)!;
  const named = doc.notebook!.tables().map((t) => ({ name: t.name, source: tables.find((i) => i.name === t.name)?.source ?? "" }));
  return readDictionary(named, held.dictionary);
}

async function drawDictionaryView(doc: Doc): Promise<void> {
  const held = dataViews.get(doc);
  if (!held || held.view !== "dictionary") return;
  try {
    const found = await dictionaryTables(doc);
    drawDictionary(held.host, found, held.chosen, (table, column, text) => describe(doc, table, column, text));
  } catch (e) {
    clear(held.host, errorNote(e, { dismiss: false }));
  }
}

/** A description typed in the Dictionary (or sent by the agent): kept in data.ipynb (unsaved until
 *  Save), and data.py's next export carries it. */
function describe(doc: Doc, table: string, column: string | null, text: string): Descriptions {
  const held = dataViews.get(doc);
  if (!held) throw new Error("The document in front is not a project's data.ipynb.");
  held.dictionary = described(held.dictionary, table, column, text);
  markChanged(doc)();
  doc.streamlit?.syncSoon();
  return held.dictionary;
}

// ----- the status bar's mode toggles, and a group's mode switches

const modeToggles = h("span", { class: "wb-mode-toggles" });

function drawModeToggles(doc: Doc | null): void {
  const panels = doc?.modes?.panels() ?? [];
  clear(
    modeToggles,
    ...panels.map((p) =>
      button(p.label ?? p.title, () => {
        doc!.modes!.toggle(p.id);
        drawStatus();
      }, { class: `ghost wb-toggle wb-mode-toggle-${p.id}`, pressed: doc!.modes!.isOpen(p.id) }),
    ),
  );
}

/** A notebook's Cells | Present switch; data.ipynb's Cells | Lineage | Dictionary. */
function modeSwitch(doc: Doc): HTMLElement | null {
  if (!doc.notebook) return null;
  const pick = (label: string, ic: string, on: boolean, run: () => void): HTMLButtonElement => button(label, run, { icon: ic, pressed: on, class: `wb-view-${label.toLowerCase()}` });
  const held = dataViews.get(doc);
  if (held && isData(doc)) {
    return h(
      "span",
      { class: "cv-mode wb-view-switch", role: "group", "aria-label": "View" },
      pick("Cells", "notebook", held.view === "cells", () => void setDataView(doc, "cells")),
      pick("Lineage", "lineage", held.view === "lineage", () => void setDataView(doc, "lineage")),
      pick("Dictionary", "book", held.view === "dictionary", () => void setDataView(doc, "dictionary")),
    );
  }
  const presenting = doc.element.classList.contains("presenting");
  return h(
    "span",
    { class: "cv-mode wb-view-switch", role: "group", "aria-label": "View" },
    pick("Cells", "notebook", !presenting, () => void present(doc, false)),
    pick("Present", "eye", presenting, () => void present(doc, true)),
  );
}

onPanels(() => {
  for (const d of docs) d.modes?.follow();
  drawStatus();
});

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
// The page's main window is found by its name (sab-notebooks, sab-scripts): the rail and a file's link bring it
// forward instead of opening another.
if (!POPPED) window.name = PAGE_WINDOW[PAGE];
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
    ...(doc.notebook ? { cells: doc.notebook.cells(), next_cell: doc.notebook.nextCell(), ...dataBody(doc) } : doc.canvas ? { pages: doc.canvas.pages(), settings: doc.canvas.settings() } : { text: doc.script!.text() }),
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
    const opened = window.open(`/${PAGE}#${hash}`, `swissarmybench-workbench-${Date.now()}`, "popup,width=1200,height=800"); // a pop-out keeps its page
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
  const taken = await api<{ document: Remembered & { title: string }; kernel: string | null }>(`/workbench/handoffs/${id}/take`, "POST", { window: WINDOW_ID, page: PAGE });
  if ((taken.document as { kind: string }).kind === "explorer") return explorerBack(taken.document as unknown as ExplorerState);
  const r = taken.document;
  const doc = r.kind === "notebook" ? openNotebook(r.path, r.cells ?? [], r.modified, r.next_cell, r.dictionary) : r.kind === "app" ? openApp(r.path, r.pages ?? [], r.modified, r.settings) : openScript(r.path, r.text ?? "", r.modified);
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

const restoreSteps = (grid: string, steps: unknown[]): void => void api(`/grids/${encodeURIComponent(grid)}/steps`, "POST", { steps }).catch((e: Error) => errorHere(e));

function makeDoc(kind: Doc["kind"], title: string, path: string | null, modified: number | null): Doc {
  const refused = wrongPage(kind, PAGE); // a notebook never opens on the Scripts page, nor a script here
  if (refused) throw new Error(refused);
  const doc: Doc = { id: ++counter, kind, title, path, modified, dirty: false, kernel: null, python: null, element: h("div", { class: `wb-doc-body kind-${kind}` }) };
  if (kind === "notebook" || kind === "script") {
    const kernel = new Kernel(() => doc.path, () => doc.python);
    doc.kernel = kernel;
    kernel.onState(() => {
      if (doc === current) drawStatus();
      if (kernel.state === "idle") lineageNoticed(); // a run ended: the lineage's values may have changed
      assignSoon(); // a started kernel has its id: the tables it sends belong to this document
    });
    // The console: Python against the kernel's names (no lint: a line typed there runs at once).
    const consoleIntel = pythonIntel(kernel, { notebook: true, document: () => doc.path ?? doc.title });
    const consoleCompleter = pythonCompleter(kernel, names);
    doc.console = consoleView(kernel, () => effectiveTheme(), {
      complete: (code, offset) => consoleIntel.complete(code, offset).then((found) => found ?? consoleCompleter(code, offset)),
      help: (code, offset) => kernel.help(code, offset),
      intel: { signature: consoleIntel.signature, hover: consoleIntel.hover },
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

/** The fixes only the window can make: install into the document's Python (in its console). A run that
 * stopped on a missing package puts the prompt in the user's face (fix.auto); the panel's Install fix
 * opens it again when asked. Installed, the cell runs again (fix.again). */
const pageFix = (doc: Doc) => (fix: Fix): boolean => {
  if (fix.kind === "table" && fix.name) {
    void giveTable(doc, fix.name).then((name) => toast(`Added ${name}'s table cell: run the cell again`), (e: Error) => errorHere(e));
    return true;
  }
  if (fix.kind === "install" && fix.package && doc.console) {
    const packages = fix.missing?.packages ?? [fix.package];
    if (!packages.every((p) => /^[A-Za-z0-9._\-[\],=<>!~]+$/.test(p))) return false;
    const missing: Missing = fix.missing ?? { feature: "This code", packages, python: doc.kernel?.python ?? "", command: `%pip install ${packages.join(" ")}` };
    void promptInstall(missing, { force: !fix.auto, install: kernelInstall(doc, fix.module), then: fix.again });
    return true;
  }
  return false;
};

/** Into the document's own Python, in its console (`%pip install`, uv when it has no pip; as before);
 * then the module is imported there, so a failed install says so. */
const kernelInstall = (doc: Doc, module?: string) => async (missing: Missing): Promise<void> => {
  const line = `%pip install ${missing.packages.join(" ")}`;
  if (!doc.console || !(await doc.console.run({ code: line }, line))) throw new Error("The install failed: the console says why.");
  if (module && /^[A-Za-z_][\w.]*$/.test(module)) {
    const check = `import importlib; importlib.invalidate_caches(); import ${module}`;
    if (!(await doc.console.run({ code: check }, check))) throw new Error(`${module} is still not there: the console says why.`);
  }
};

/** A cell's table result as a grid: the kernel still holds it as Out[n]. */
async function openResult(doc: Doc, count: number, name?: string): Promise<void> {
  if (!doc.kernel?.id) return;
  try {
    const opened = await api<{ dataset: string }>(`/workbench/kernels/${doc.kernel.id}/grid`, "POST", name ? { output: count, name } : { output: count });
    toast(`${opened.dataset} is open as a grid.`);
  } catch (e) {
    errorHere(e);
  }
}

async function openGrid(doc: Doc, name: string): Promise<void> {
  if (!doc.kernel?.id) return;
  try {
    await api(`/workbench/kernels/${doc.kernel.id}/grid`, "POST", { name });
    toast(`${name} is open as a grid.`);
  } catch (e) {
    errorHere(e);
  }
}

/** A frame in another file: open it in the Workbench at that line. */
async function openAt(path: string, line: number): Promise<void> {
  await open(path);
  const doc = docs.find((d) => d.path === path);
  if (doc?.script)
    setTimeout(() => {
      doc.script?.reveal(line);
      doc.script?.focus(); // the keyboard in the editor at that line (the explorer's outline, F12)
    }, 300);
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
  if (doc.script && doc.path) codexHooks.typed(doc.path, doc.script.text()); // its outline follows the text
  if (!doc.dirty) {
    doc.dirty = true;
    drawTabs();
  }
  remember();
  flowSoon(doc); // Notebook mode: an edited cell says so
};

function openNotebook(path: string | null, cells: CellData[], modified: number | null, nextCell?: number, dictionary?: Descriptions): Doc {
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
    lineage: (number) => void showLineage({ document: docName(doc), cell: number }),
    ran: () => flowSoon(doc),
  });
  doc.element.append(doc.notebook.element);
  notebookModes(doc);
  if (isData(doc)) dataMode(doc, dictionary ?? {});
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
  doc.script = scriptView(text, doc.kernel!, doc.console!, () => effectiveTheme(), markChanged(doc), names, file, {
    ...hooks,
    fix: pageFix(doc),
    openFile: (path, line) => void openAt(path, line),
    openGrid: (name) => void openGrid(doc, name),
    openResult: (n, name) => void openResult(doc, n, name),
    tablesChanged: () => doc === current && drawTablesTool(),
    streamlit: streamlitHost(doc),
    lineage: (number) => void showLineage({ document: docName(doc), cell: number }),
    // Script mode: Run file takes the run settings' arguments, and is kept in the run history.
    arguments: () => scriptArguments.get(doc) ?? "",
    ranFile: (ok, seconds) => {
      if (!doc.path) return;
      void recordRunFile(doc.path, ok, seconds).then(() => doc.modes?.redraw("runHistory"), () => undefined);
    },
    // The Scripts IDE's moves (workbenchIde.ts): F12, Shift+F12, F2, Shift+Alt+F.
    ide: ideMoves(
      { path: () => doc.path, text: () => doc.script!.text(), python: () => doc.python, replaceText: (t) => doc.script!.replaceText(t), reveal: (line) => doc.script!.reveal(line) },
      { openAt: (p, line) => void openAt(p, line) },
    ),
  });
  attachStreamlit(doc);
  doc.element.append(doc.script.element);
  scriptModes(doc);
  if (path) void readArguments(doc);
  show(doc);
  doc.streamlit!.syncSoon();
  return doc;
}

// ===== lineage: a cell or a block back to the data, with its values (workbenchLineage.ts) =====

/** A document as the lineage names it: its path, or its title while it has none. */
const docName = (doc: Doc): string => doc.path ?? doc.title;

/** The error each cell's last run ended with, by its number ("KeyError: 'amount'"). */
function cellErrors(cells: CellData[]): Record<string, string> {
  const found: Record<string, string> = {};
  for (const c of cells) {
    const error = c.outputs.find((o) => o.output_type === "error");
    if (error && c.number) found[String(c.number)] = `${String(error.ename ?? "Error")}: ${String(error.evalue ?? "")}`.trim();
  }
  return found;
}

/** The request for a target: a cell of a document open here goes with the cells as the window holds them. */
function lineageBody(target: LineageTarget): Record<string, unknown> {
  if (target.app) return { app: target.app, page: target.page, block: target.block };
  const doc = docs.find((d) => (d.notebook || d.script) && docName(d) === target.document);
  if (!doc) return { document: target.document, cell: target.cell };
  const base = { document: docName(doc), cell: target.cell, kernel: doc.kernel?.id ?? null };
  if (doc.script) return { ...base, text: doc.script.text() };
  const cells = doc.notebook!.cells();
  const lean = cells.map(({ kind, source, connection, number, role, table, name }) => ({ kind, source, connection, number, role, table, name }));
  return { ...base, cells: lean, errors: cellErrors(cells) };
}

/** Double-click on a node: its cell, in its document (opened when it is not open here). */
async function goToNode(node: LineageNode): Promise<void> {
  if (node.cell === null || !node.document) return;
  let doc = docs.find((d) => (d.notebook || d.script) && (docName(d) === node.document || d.path === node.document));
  if (!doc) {
    await open(node.document);
    doc = docs.find((d) => d.path === node.document);
  }
  if (!doc) return;
  show(doc);
  viewOf(doc)?.goTo(node.cell);
}

const lineageHost = { body: lineageBody, goTo: (node: LineageNode) => void goToNode(node) };

/** The Data mode's Lineage view: data.ipynb's selected cell (else its last numbered one) back to the
 *  data, drawn in place by the lineage overlay's own code; a double-click on a node goes back to the
 *  cells, at that cell. */
async function dataLineage(doc: Doc, into: HTMLElement, cell?: number): Promise<LineageGraph | null> {
  const numbered = doc.notebook!.cells().filter((c) => c.number && c.kind !== "markdown" && c.source.trim());
  const number = cell ?? doc.notebook!.selectedNumber() ?? numbered[numbered.length - 1]?.number ?? null;
  if (!number) {
    drawLineageEmpty(into);
    return null;
  }
  const host = {
    body: lineageBody,
    goTo: (node: LineageNode) => {
      if (dataViews.get(doc)?.view === "lineage") setDataView(doc, "cells");
      void goToNode(node);
    },
  };
  return openLineage({ document: docName(doc), cell: number }, host, into);
}

/** The lineage overlay: a cell of a document, a block of a canvas; without a target, the front
 *  document's selected cell (the cursor's in a script) or the front canvas's first block. */
async function showLineage(target?: LineageTarget & { number?: number }, into?: HTMLElement): Promise<LineageGraph> {
  let chosen: LineageTarget | null = null;
  if (target?.app || target?.document) chosen = target;
  else if (current?.canvas && (target?.block || !target?.number)) {
    const report = current.canvas.report() as { page: string | null; pages: { id: string; blocks: { id: string }[] }[] };
    const page = report.pages.find((p) => p.id === report.page);
    const block = target?.block ?? page?.blocks[0]?.id;
    if (!page || !block || !current.canvas.app()) throw new Error("The canvas in front has no block on its page.");
    chosen = { app: current.canvas.app()!, page: page.id, block };
  } else if (current?.notebook || current?.script) {
    const number = target?.number ?? target?.cell ?? (current.notebook ? current.notebook.selectedNumber() : current.script!.cursorCell());
    if (!number) throw new Error("Select a cell first.");
    chosen = { document: docName(current), cell: number };
  }
  if (!chosen) throw new Error("No notebook, script or Streamlit app is in front.");
  return openLineage(chosen, lineageHost, into);
}

// For the agent's palette and the tests: the overlay, or (`into`) the same flow drawn in that element.
(window as unknown as { openLineage: (target?: LineageTarget & { number?: number }, into?: HTMLElement) => Promise<LineageGraph> }).openLineage = showLineage;

/** A run in a document's console: the console opens to show it. */
function useConsole(doc: Doc): void {
  if (doc !== current || layout.state().console || !panelOn("workbench.console")) return;
  layout.toggle("console", true);
  drawStatus();
}

/** Show a document: in front of its group, that group focused (a new one opens in the focused group).
 *  The landing page on show makes way (its address replaced: the document is what is here now). */
function show(doc: Doc): void {
  if (landing.kind()) {
    hideLanding();
    const k = docKindOf(doc);
    void go(withParams(k ? { view: null, kind: k } : { view: null }), "replace");
  }
  groups.show(doc);
}

/** App mode's starter gallery (its Starters panel): a click adds one to the canvas in front. */
const gallery = starterGallery((name) => {
  if (current?.canvas) void addStarter(current, name).catch((e: Error) => errorHere(e));
});

/** The focused group's document changed: everything that follows the focused document follows. */
function focused(doc: Doc | null): void {
  current = doc;
  variables.show(doc?.kernel ?? null);
  // A Streamlit app runs no code of its own: its console's place says nothing.
  if (doc?.kind === "app" || doc?.kind === "workbook") layout.console.replaceChildren();
  else layout.console.replaceChildren(doc?.console?.element ?? h("p", { class: "hint wb-pane-empty" }, "No console"));
  cursor = { line: 1, column: 1 };
  drawEmpty();
  drawControls();
  drawStatus();
  setTitle(PAGE_WORDS[PAGE], doc?.title ?? ""); // "Workbench · sales.ipynb": the page, then the place
  followKind(doc);
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
  doc.workbook?.close();
  // Its Monaco editors and design frames go too (they were kept alive, detached, before).
  doc.notebook?.dispose();
  doc.script?.dispose();
  doc.console?.dispose();
  doc.codefile?.dispose();
  docs.splice(docs.indexOf(doc), 1);
  tablesSent.delete(doc);
  flows.delete(doc);
  dataViews.delete(doc);
  scriptArguments.delete(doc);
  if (doc.kind === "blade") editingBlade = false;
  groups.remove(doc); // the group's next document comes to the front (and the group goes with its last)
  drawEmpty();
  remember();
}

/** A document's title or unsaved dot changed. */
function drawTabs(): void {
  groups.redraw();
  codexHooks.mark();
  drawTop();
}

/** A document's kind colour (kindColours.ts): app pages violet, notebooks blue, scripts green. */
function docMark(doc: Doc): "app" | "notebook" | "script" | undefined {
  return doc.kind === "app" ? "app" : doc.kind === "notebook" ? "notebook" : doc.kind === "script" ? "script" : undefined;
}

/** A document's kind of tab: Data notebook (a project's data.ipynb), App notebook (any other notebook
 *  in a project), Notebook (one outside a project), Script, App page (a Streamlit app's canvas), Blade,
 *  Table. */
function kindOf(doc: Doc): string {
  if (doc.kind === "app") return "page";
  if (doc.kind === "workbook") return "workbook";
  if (doc.kind === "notebook") {
    const role = notebookRole(doc.path);
    return role === "data" ? "dataNotebook" : role === "app" ? "appNotebook" : "notebook";
  }
  return doc.kind === "table" ? "explorer" : doc.kind;
}

// Kind colours (kindColours.ts): app pages violet, notebooks blue (the data notebook and the app
// notebooks too, each with its own icon and word: the owner, 2026-11-16), scripts green; a blade or a
// catalog table wears none.
registerTabKind({ id: "dataNotebook", label: "Data notebook", icon: "dataNotebook", mark: "notebook" });
registerTabKind({ id: "notebook", label: "Notebook", icon: "notebook", mark: "notebook", start: { label: "New notebook", run: () => void openNotebook(null, [], null) } });
registerTabKind({ id: "appNotebook", label: "App notebook", icon: "appNotebook", mark: "notebook" });
registerTabKind({ id: "script", label: "Script", icon: "code", mark: "script", start: { label: "New script", run: () => void openScript(null, "", null) } });
registerTabKind({ id: "blade", label: "Blade", icon: "bolt", mark: "plain" });
registerTabKind({ id: "explorer", label: "Table", icon: "rows", mark: "plain" });
registerCanvasKinds();
// The open project's mode (modes.ts): its canvases offered by New, its families first in the pickers.
onMode(() => {
  registerCanvasKinds();
  drawEmpty();
  drawTop();
  void loadModeFiles(); // the mode's own files, for the project now open
});
void whenMode();

registerTabKind({ id: "codefile", label: "Code file", icon: "codeapp", mark: "script" });

// ===== a code app's files (the Power Apps extension's plug-in: workbenchCodeFile.ts) =====

/** A file of the open code app, in the editor (TypeScript or TSX with Monaco's own language service). */
async function openCodeFileDoc(path: string): Promise<void> {
  const already = docs.find((d) => d.kind === "codefile" && d.codefile?.path === path);
  if (already) return show(already);
  const doc = makeDoc("codefile", baseName(path), path, null);
  try {
    doc.codefile = await openCodeFile(path, effectiveTheme(), () => {
      if (!doc.dirty) {
        doc.dirty = true;
        drawTabs();
      }
    });
  } catch (e) {
    docs.splice(docs.indexOf(doc), 1);
    errorHere(e);
    return;
  }
  doc.element.append(doc.codefile.element);
  show(doc);
}

/** The mode's first language when it is not Python: New makes a file of it (a code app: TypeScript). */
const scriptLanguage = (): string | null => {
  const first = activeMode().mode.languages[0];
  return first && first !== "python" ? first : null;
};
const LANGUAGE_WORDS: Record<string, string> = { typescript: "TypeScript", tsx: "TSX", python: "Python" };
async function newModeFile(language: string): Promise<void> {
  const ending = language === "tsx" ? ".tsx" : ".ts";
  const name = prompt(`New ${LANGUAGE_WORDS[language] ?? language} file (in src/shared, or a path under src/pages/<Page>/)`, `module${ending}`);
  if (!name) return;
  try {
    const path = await newCodeFile(name.endsWith(ending) || /\.(ts|tsx)$/.test(name) ? name : `${name}${ending}`);
    await openCodeFileDoc(path);
  } catch (e) {
    errorHere(e);
  }
}

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
// The rail's Notebooks, Scripts and Apps land on their kind's page (workbenchLanding.ts): its documents as
// cards (New and Open… are the top bar's); Scripts and Notebooks show the tables' transformations first.
const sameDoc = (k: Kind, chosen: LandingDoc): Doc | undefined => docs.find((d) => docKindOf(d) === k && (chosen.path ? d.path === chosen.path : !d.path && d.title === chosen.title));
const landing = mountLanding({
  openDocs: (k) => docs.filter((d) => docKindOf(d) === k).map((d) => ({ title: d.title, path: d.path, dirty: d.dirty, front: d === current })),
  choose: (k, chosen) => {
    // A move of the user's: pushed, so Back comes back to this page.
    hideLanding();
    void go(withParams({ view: null, kind: k }), "push");
    if (k === "app") appPanes();
    const found = sameDoc(k, chosen);
    if (found) show(found);
    else if (chosen.path) void open(chosen.path);
  },
  tables: async () => (await fetchTables()).map((t) => ({ name: t.name, steps: t.step_words ?? [], problem: t.problem })),
  showTable: (name) => void showTransformations(name).catch((e: Error) => errorHere(e)),
  start: () => topStart(),
});
layout.source.append(groups.element, empty, landing.element);

/** The landing page for `k` in place of the groups (the address says ?kind=k&view=list). */
function showLanding(k: Kind): void {
  // The other page's kind: that page's window, brought forward (never its tabs here).
  const page = pageOfKind(k);
  if (page && page !== PAGE) {
    bringPage(page, `/${page}?kind=${k}&view=list`);
    return;
  }
  // The creator shows only while none of the kind is open (the owner, 2026-11-21): else its tab comes forward.
  const mine = k !== "app" ? [...docs].reverse().find((d) => docKindOf(d) === k) : undefined;
  if (mine) {
    void go(withParams({ view: null, kind: k }), "replace");
    show(mine);
    return;
  }
  landing.show(k);
  groups.element.hidden = true;
  empty.hidden = true;
  setTitle(PAGE_WORDS[PAGE], KIND_WORDS[k].name);
  drawTop();
}

function hideLanding(): void {
  if (!landing.kind()) return;
  landing.hide();
  drawEmpty();
  drawTop();
  setTitle(PAGE_WORDS[PAGE], current?.title ?? "");
  // The groups are back: Monaco and the canvas measure again.
  window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
}

/** Whether a kind of tab is made on this page: a script's on the Scripts page, a notebook's and a canvas's
 *  on the Notebooks page; a plain one (a blade, a table) on both. */
const kindHere = (kind: TabKind): boolean => kind.mark === "plain" || (kind.mark === "script" ? PAGE === "scripts" : PAGE === "notebooks");

/** A kind's New: in a project a new notebook is an app notebook (the project has one data notebook). */
function startLabel(kind: TabKind): string {
  return kind.id === "notebook" && projectOpen() ? "New app notebook" : (kind.start?.label ?? "");
}

/** What a group's "+" and the top bar's "…" make: each kind that starts from there, then Open and Recent. */
function newEntries(anchor: HTMLElement): MenuEntry[] {
  return [
    ...tabKinds()
      .filter((k) => k.start && kindHere(k))
      .map((k) => ({ label: startLabel(k), icon: k.id === "notebook" ? kindIcon("notebook", null) : k.icon, run: gatedRun(areaOfKind(k.id), k.start!.run) })),
    null,
    ...projectEntries(),
    null,
    { label: "Open…", icon: "folder", keys: "Ctrl+O", run: () => void open() },
    { label: "Import…", icon: "import", title: "Notebooks, scripts and apps from another project", disabled: !sabOpen(), run: () => void importDocuments() },
    { label: "In this project…", icon: "more", run: () => recentMenu(anchor) },
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
  let chosen = path ?? (await chooseFile({ title: "Open", mode: "file", suffixes: PAGE === "scripts" ? [".py"] : [".ipynb", ...(canvasAnywhere("streamlit") ? [APP_ENDING] : []), ...(offersCanvas("excel") ? [WORKBOOK_ENDING] : [])], start: sab.folder ?? current?.path ?? homeFolder }));
  if (!chosen) return;
  // Documents are the project's (the owner, 2026-11-16): a file from outside it is copied in, and the copy opens.
  if (!path && sabOpen() && sab.folder && !inFolder(chosen, sab.folder)) {
    try {
      chosen = await importFile(chosen);
    } catch (e) {
      errorHere(e);
      return;
    }
  }
  // A notebook opens on the Notebooks page, a .py on the Scripts page (the owner, 2026-11-21): the other
  // page's window opens it (opened on it when there is none).
  const there = pageOfPath(chosen);
  if (there && there !== PAGE) return openOnPage(chosen);
  const already = docs.find((d) => d.path === chosen);
  if (already) return show(already);
  if (chosen.toLowerCase().endsWith(WORKBOOK_ENDING)) return void openWorkbook(chosen);
  try {
    const found = await api<{ path: string; kind: "notebook" | "script" | "app"; modified: number; cells?: CellData[]; text?: string; python: string | null; next_cell?: number; pages?: SavedPage[]; settings?: AppSettings; dictionary?: Descriptions; hash?: string | null }>("/workbench/open", "POST", { path: chosen });
    if (found.kind === "notebook") openNotebook(found.path, found.cells ?? [], found.modified, found.next_cell, found.dictionary);
    else if (found.kind === "app") openApp(found.path, found.pages ?? [], found.modified, found.settings);
    else openScript(found.path, found.text ?? "", found.modified);
    if (current?.path === found.path) current.hash = found.hash ?? null;
    // Its own environment, as remembered (or the .venv beside it): the picker shows it, Run uses it.
    if (found.python && current) {
      current.python = found.python;
      if (!pythons.some((p) => p.python === found.python)) pythons.push({ python: found.python, version: "", ipykernel: true, swissarmybench: true });
      drawStatus();
    }
    void refreshHome();
  } catch (e) {
    errorHere(e);
  }
}

// ===== a file changed anywhere (the owner, 2026-11-21: "scripts autoupdate when they are touched anywhere in
// the app"; services/code_files.py's file_changed notice) =====

function clearElsewhere(doc: Doc): void {
  doc.elsewhere?.bar.remove();
  delete doc.elsewhere;
}

type Reread = { path: string; modified: number; text?: string; cells?: CellData[]; next_cell?: number; hash?: string | null };

/** The document read again from its file: a script's text in place (its cursor and scroll kept), a notebook's
 *  cells as they are now. */
async function reloadDoc(doc: Doc): Promise<void> {
  const found = await api<Reread>("/workbench/open", "POST", { path: doc.path });
  if (doc.script) doc.script.replaceText(found.text ?? "");
  else if (doc.notebook) {
    const open = docs.indexOf(doc) >= 0;
    if (open) {
      close(doc, true);
      void openNotebook(found.path, found.cells ?? [], found.modified, found.next_cell);
      if (current) current.hash = found.hash ?? null;
      return;
    }
  }
  doc.modified = found.modified;
  doc.hash = found.hash ?? null;
  doc.dirty = false;
  clearElsewhere(doc);
  drawTabs();
  remember();
}

/** Its file and this window's text side by side (Monaco's diff editor). */
async function compareDoc(doc: Doc): Promise<void> {
  const found = await api<Reread>("/workbench/open", "POST", { path: doc.path });
  const mine = doc.script?.text() ?? JSON.stringify(doc.notebook?.cells().map((c) => c.source) ?? [], null, 1);
  const theirs = found.text ?? JSON.stringify((found.cells ?? []).map((c) => c.source), null, 1);
  const { dialog, body } = openDialog(`${doc.title}: the file, and yours`, true);
  const host = h("div", { class: "wb-compare", style: { height: "60vh" } });
  body.append(host);
  const lib = (await import(/* external */ "/static/build/lazy/codeEditor.js" as string)) as typeof import("./lazy/codeEditor");
  const viewer = lib.createDiffViewer(host, effectiveTheme());
  viewer.show(theirs, mine, doc.path ?? doc.title);
  dialog.addEventListener("close", () => viewer.dispose());
}

/** The bar over a document whose file changed elsewhere while it was edited here (or went away). */
function elsewhereBar(doc: Doc, hash: string | null): void {
  clearElsewhere(doc);
  const guard = (act: () => Promise<unknown>) => (): void => void act().catch((e: Error) => errorHere(e));
  const bar = h(
    "div",
    { class: "wb-elsewhere", role: "status" },
    icon("warning"),
    h("span", {}, hash === null ? "This file is gone." : "Changed elsewhere."),
    ...(hash === null
      ? [button("Save as…", () => void save(doc, true), { class: "line" }), button("Close", () => close(doc), { class: "ghost" })]
      : [
          button("Reload", guard(() => reloadDoc(doc)), { class: "primary" }),
          button(
            "Keep mine",
            guard(async () => {
              const found = await api<Reread>("/workbench/open", "POST", { path: doc.path });
              doc.modified = found.modified; // Save writes this window's text over it
              doc.hash = found.hash ?? null;
              clearElsewhere(doc);
            }),
            { class: "line" },
          ),
          button("Compare", guard(() => compareDoc(doc)), { class: "ghost" }),
        ]),
  );
  doc.elsewhere = { hash, bar };
  doc.element.prepend(bar);
}

/** A file_changed notice: each document of that file follows (in place when unchanged here). */
function fileChanged(path: string, hash: string | null): void {
  for (const doc of docs.filter((d) => d.path === path)) {
    if (hash !== null && hash === doc.hash) continue; // this window's own save, or the same text
    if (hash === null || doc.dirty || !doc.script) elsewhereBar(doc, hash);
    else void reloadDoc(doc).catch((e: Error) => errorToast(e));
  }
  codexHooks.refresh();
}

/** Save a document (true: it is saved). */
async function save(doc: Doc | null, as = false): Promise<boolean> {
  if (doc?.workbook) {
    if (!as) return doc.workbook.save();
    const where = await chooseFile({ title: "Save workbook design as", mode: "save", start: doc.path ?? project?.folder ?? homeFolder, name: `workbook${WORKBOOK_ENDING}` });
    return where ? doc.workbook.save(where.toLowerCase().endsWith(".json") ? where : where + WORKBOOK_ENDING) : false;
  }
  if (doc?.codefile) {
    await doc.codefile.save();
    doc.dirty = false;
    drawTabs();
    toast(`Saved ${doc.title}.`);
    return true;
  }
  if (!doc || (doc.kind !== "notebook" && doc.kind !== "script" && doc.kind !== "app")) return false;
  // Changed elsewhere while edited here: never written over until the user chooses (Reload, Keep mine).
  if (doc.elsewhere && !as) {
    errorHere(`${doc.title} changed elsewhere: Reload, Keep mine or Compare first.`);
    return false;
  }
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
  const body = doc.kind === "notebook" ? { cells: doc.notebook!.cells(), next_cell: doc.notebook!.nextCell(), ...dataBody(doc) } : doc.kind === "app" ? { pages: doc.canvas!.pages(), settings: doc.canvas!.settings() } : { text: doc.script!.text() };
  const send = async (force: boolean): Promise<void> => {
    const saved = await api<{ path: string; modified: number; hash?: string | null }>("/workbench/save", "POST", { path, ...body, modified: as ? null : doc.modified, force });
    const first = doc.path === null;
    doc.hash = saved.hash ?? null;
    clearElsewhere(doc);
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
        (err: Error) => (errorHere(err), false),
      );
    }
    errorHere(e);
    return false;
  }
}

// The open project's documents (no recent files: the owner, 2026-11-16, "objects are project scoped").
let recent: { path: string; exists: boolean }[] = [];
async function refreshHome(): Promise<void> {
  try {
    const [home, listed] = await Promise.all([
      api<{ folder: string }>("/workbench/home"),
      api<{ documents: { full: string; made: boolean }[] }>("/project/documents"),
    ]);
    homeFolder = home.folder;
    recent = listed.documents.filter((d) => !d.made).map((d) => ({ path: d.full, exists: true }));
  } catch {
    /* the server will say so on the next action */
  }
}

/** Import…: notebooks, scripts and apps from another project (or a loose file), copied in and opened. */
async function importDocuments(): Promise<void> {
  const done = await openImport("documents");
  if (!done) return;
  for (const d of done.documents) await open(d.full);
  void refreshHome();
}

function recentMenu(anchor: HTMLElement): void {
  openMenu(
    anchor,
    "In this project",
    recent.length
      ? recent.map((r) => ({ label: baseName(r.path), icon: kindIcon(kindOfPath(r.path), r.path), mark: kindOfPath(r.path) ?? undefined, title: r.path, run: () => void open(r.path) }))
      : [{ label: "No documents", heading: true }],
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
  if (doc.path) void api("/workbench/environment", "POST", { path: doc.path, python }).catch((e: Error) => errorHere(e));
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
const saveButton = button("Save", () => void saveFront().catch((e: Error) => errorHere(e)), { icon: "save", title: "Save (Ctrl+S)" });
const topProject = menuButton(button("Project", () => undefined, { icon: "project", class: "ghost wb-project" }), "Project", () => projectEntries());
const saveAsButton = button("Save as…", () => void save(current, true), { icon: "save", title: "Save as (Ctrl+Shift+S)" });
// New and Open… beside them (the owner, 2026-11-16: "new script and open should be in the bar above along
// with the save and save as"): New makes the kind on show (the landing's, else the document's in front's).
const topNew = button("New notebook", () => topStart(), { icon: "plus", class: "wb-top-new" });
const topOpen = button("Open…", () => void open(), { icon: "folder", title: "Open a notebook, script or Streamlit app (Ctrl+O)" });
const topMenu = menuButton(button("Workbench menu", () => undefined, { icon: "more", iconOnly: true, class: "ghost", title: "More" }), "Workbench menu", () => topEntries(), { align: "right" });
// The app's mark: the window's icon, drawn small, a link home (it brings the home window forward).
top.append(topProject, topName, saveButton, saveAsButton, topNew, topOpen, h("span", { class: "wb-grow" }), topMenu);

/** The kind the top bar's New makes: the landing's on show, else the document's in front (a data or app
 *  notebook makes a notebook), else the address's, else a notebook. */
function topKind(): Kind {
  return landing.kind() ?? docKindOf(current) ?? codeKindOf(new URLSearchParams(location.search).get("kind")) ?? "notebook";
}

/** The top bar's New: that kind's start. From a landing page the move is pushed, so Back returns to it. */
function topStart(): void {
  const k = topKind();
  const own = k === "script" ? scriptLanguage() : null;
  if (own) {
    void newModeFile(own);
    return;
  }
  const start = tabKinds().find((t) => t.mark === k && t.start)?.start;
  if (!start) return;
  if (landing.kind()) {
    hideLanding();
    void go(withParams({ view: null, kind: k }), "push");
  }
  if (k === "app") appPanes();
  start.run();
}

function drawTop(): void {
  const doc = current;
  const makes = tabKinds().find((t) => t.mark === topKind() && t.start);
  const own = topKind() === "script" ? scriptLanguage() : null;
  const making = own ? `New ${LANGUAGE_WORDS[own] ?? own} file` : makes ? startLabel(makes) : "";
  const newLabel = topNew.querySelector(".btn-label");
  if (newLabel && making) newLabel.textContent = making;
  topNew.title = making;
  topNew.setAttribute("aria-label", making || "New");
  if (making) codexHooks.label(making); // the explorer's New says the same
  topNew.dataset.kind = topKind();
  clear(topName, h("span", { class: "wb-name-text" }, doc?.title ?? "Workbench"), doc?.dirty ? h("span", { class: "wb-name-dot", role: "img", "aria-label": "Unsaved changes", title: "Unsaved changes" }) : null);
  topName.title = doc?.path ?? doc?.title ?? "";
  // The open project's name, with its unsaved mark (●): its menu saves, saves as, closes.
  const opened = projectState().project;
  topProject.hidden = !opened;
  const label = topProject.querySelector(".btn-label");
  if (opened && label) label.textContent = projectLabel(opened);
  topProject.title = opened?.path ?? opened?.name ?? "";
  for (const b of [saveButton, saveAsButton]) {
    b.disabled = !saves() && !(b === saveButton && opened);
    b.title = saves() ? (b === saveButton ? "Save (Ctrl+S)" : "Save as (Ctrl+Shift+S)") : "Nothing that saves is in front";
  }
}

/** The top bar's "…": what makes a document, opens one, splits the groups, and every command. */
function topEntries(): MenuEntry[] {
  const shown = explorerPane.isOpen();
  return [
    ...newEntries(topMenu),
    null,
    { label: "Split right", icon: "splitRight", keys: "Ctrl+\\", disabled: !canSplit(current), title: canSplit(current) ? undefined : SPLIT_WHY, run: () => splitDoc(current, "right") },
    { label: "Split down", icon: "splitDown", disabled: !canSplit(current), title: canSplit(current) ? undefined : SPLIT_WHY, run: () => splitDoc(current, "down") },
    null,
    ...(panelOn("workbench.explorer") ? [{ label: shown ? "Close the Data Explorer" : "Data Explorer", icon: "zoom", keys: "Ctrl+Shift+E", run: () => void runCommand("view.explorer") }] : []),
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
    // The open project's mode's own cell kinds (a code app: TypeScript and TSX): run where its routes say;
    // a kind with no route yet is offered as coming.
    ...activeMode().mode.cell_kinds
      .filter((k) => !["code", "python", "sql", "dax", "html", "markdown"].includes(k))
      .map((k) =>
        cellRoute(k) && (k === "typescript" || k === "tsx")
          ? { label: cellRoute(k)!.name || (LANGUAGE_WORDS[k] ?? k), icon: k === "tsx" ? "image" : "code", title: k === "tsx" ? "A React component, drawn" : "Run in the data notebook's kernel", run: add(k) }
          : { label: `${LANGUAGE_WORDS[k] ?? k} (coming)`, icon: "code", disabled: true, title: "Coming: a later version runs these cells", run: () => undefined },
      ),
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
    { label: "Import…", icon: "import", title: "Notebooks, scripts and apps from another project", disabled: !sabOpen(), run: () => void importDocuments() },
    { label: "In this project…", icon: "more", run: () => recentMenu(anchor) },
    ...(doc.notebook || doc.script
      ? [
          { label: "Save", icon: "save", keys: "Ctrl+S", run: () => void save(doc) },
          { label: "Save as…", icon: "save", keys: "Ctrl+Shift+S", run: () => void save(doc, true) },
        ]
      : []),
    ...(doc.notebook || doc.script
      ? [
          { label: "Export as one Python script…", icon: "export", title: "One .py that runs with plain python: its connections, vault lookups and grid steps written out", run: () => void exportDocument(doc, "script").catch((e: Error) => errorHere(e)) },
          { label: "Export as one notebook…", icon: "export", title: "One linear .ipynb that runs top to bottom in any Jupyter (nbconvert, papermill)", run: () => void exportDocument(doc, "notebook").catch((e: Error) => errorHere(e)) },
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
  const guarded = (act: () => Promise<unknown>) => (): void => void act().catch((e: Error) => errorHere(e));
  const mark = docMark(doc);
  return [
    { label: "Open in its own window", icon: "popout", mark, run: guarded(() => popOut(doc)) },
    ...(isMainWindow() ? [] : [{ label: "Move to the main window", icon: "back", mark, run: guarded(() => moveToMain(doc)) }]),
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
  // Its own Save in its row (no top bar: the owner, 2026-11-21); Save as… is its "…" or Ctrl+Shift+S.
  const saveHere = button("Save", () => void saveFront().catch((e: Error) => errorHere(e)), { icon: "save", iconOnly: true, class: "ghost wb-save", title: "Save (Ctrl+S)" });
  const fullButton = button(full ? "Leave full screen" : "Full screen", () => void fullScreen(), { icon: full ? "restore" : "max", iconOnly: true, class: "ghost wb-full-toggle", title: full ? "Leave full screen (Escape)" : "Full screen (F11)", pressed: full });
  if (doc.canvas) return void host.replaceChildren(doc.canvas.tools, saveHere, more);
  if (doc.workbook) return void host.replaceChildren(doc.workbook.tools, saveHere, more);
  if (!doc.notebook && !doc.script) return void host.replaceChildren(more);
  const addCell = h("button", { type: "button", class: "btn line wb-add-cell", "aria-label": "Add cell", title: "Add cell" }, icon("plus"), h("span", { class: "btn-label" }, "Cell"), icon("down")) as HTMLButtonElement;
  menuButton(addCell, "Cell kinds", () => cellEntries(doc));
  const run = doc.notebook
    ? button("Run all", () => void doc.notebook!.runAll(), { icon: "play", class: "primary", title: "Run all (F5)" })
    : button("Run file", () => void doc.script!.runFile(), { icon: "play", class: "primary", title: "Run file (F5)" });
  // Script mode: Run as scheduled (a fresh process with no app); Notebook and Data mode: the view's switch.
  const scheduled = doc.script ? button("Run as scheduled", () => void runScheduled(doc), { icon: "clock", class: "wb-run-scheduled", title: "The script as a schedule runs it: a fresh process with no app" }) : null;
  if (scheduled && scheduling.has(doc)) markBusy(scheduled, "Running…"); // loading.ts
  const view = dataViews.get(doc)?.view ?? "cells";
  // No "+ Cell" on a script (the owner, 2026-11-17: "cell insert is available on the script page and it
  // shouldnt be"): cells are a notebook's.
  host.replaceChildren(...[modeSwitch(doc), tablesHost, view === "cells" && doc.notebook ? addCell : null, scheduled, view === "cells" ? run : null, saveHere, more, fullButton].filter((e): e is HTMLElement => e !== null));
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
installZoomInput();
const explorerToggle = button("Data Explorer", () => void runCommand("view.explorer").catch((e: Error) => errorHere(e)), { class: "ghost wb-toggle wb-explorer-toggle", pressed: false, title: "Data Explorer (Ctrl+Shift+E)" });
// The lint's count for the document in front (errors and warnings; unused names are faded, not counted):
// a click lists every problem, and goes to the one picked. Nothing shows while there is none.
const problemsButton = menuButton(
  button("Problems", () => undefined, { icon: "warning", class: "ghost wb-problems" }),
  "Problems",
  () => {
    const found = problemsOf(problemsKey(current));
    const entries: MenuEntry[] = found.flatMap((s) =>
      s.problems.map((p) => ({
        label: `${s.place ? `${s.place}, ` : ""}line ${p.line}: ${p.message.replace(/`/g, "")}${p.code ? ` (${p.code})` : ""}`,
        icon: p.severity === "error" ? "problem" : p.severity === "warning" ? "warning" : "info",
        run: () => s.reveal(p.line, p.col),
      })),
    );
    const listed: MenuEntry[] = entries.length ? entries : [{ label: "No problems", disabled: true }];
    // Ruff, offered here only (quietly: never a prompt by itself): into the document's own Python.
    const doc = current;
    const ruff = doc ? ruffOffer(problemsKey(doc)) : null;
    if (ruff && doc) listed.push(null, { label: "Check with Ruff too: install ruff…", icon: "import", run: () => void promptInstall(ruff, { force: true, install: kernelInstall(doc), then: () => relint(doc) }) });
    return listed;
  },
  { above: true },
);
problemsButton.hidden = true;
/** The key the editors' problems are kept under for a document (workbenchIntel.ts's document). */
function problemsKey(doc: Doc | null): string {
  if (!doc) return "\u0000none";
  return doc.path ?? (doc.kind === "notebook" ? "Untitled notebook" : "Untitled script");
}
function drawProblems(): void {
  const doc = current;
  const found = doc && (doc.notebook || doc.script) ? problemsOf(problemsKey(doc)).flatMap((s) => s.problems) : [];
  const errors = found.filter((p) => p.severity === "error").length;
  const warnings = found.filter((p) => p.severity === "warning").length;
  problemsButton.hidden = errors + warnings === 0;
  const words = [errors ? `${errors} ${errors === 1 ? "error" : "errors"}` : "", warnings ? `${warnings} ${warnings === 1 ? "warning" : "warnings"}` : ""].filter(Boolean).join(", ");
  const label = problemsButton.querySelector(".btn-label");
  if (label) label.textContent = words;
  problemsButton.setAttribute("aria-label", words ? `Problems: ${words}` : "Problems");
  problemsButton.title = words;
  problemsButton.classList.toggle("has-errors", errors > 0);
}
onProblems(drawProblems);
/** Check a document's editors again (Ruff came in). */
function relint(doc: Doc): void {
  doc.script?.relint();
  doc.notebook?.relint();
}
// The app's one footer (appFooter.ts), the Workbench's own parts in its middle: the panes' switches on the right.
mountAppFooter(layout.status, [explorerToggle, kernelHost, envHost, cursorHost, problemsButton, inlineStatus()], [consoleToggle, modeToggles, variablesToggle]);

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
  drawProblems();
  explorerToggle.setAttribute("aria-pressed", String(explorerPane.isOpen() || explorerPane.popped()));
  const state = layout.state();
  consoleToggle.setAttribute("aria-pressed", String(state.console));
  variablesToggle.setAttribute("aria-pressed", String(state.right));
  consoleToggle.disabled = !doc?.console;
  consoleToggle.title = doc?.console ? "Console (Ctrl+2)" : "No console for what is in front";
  // App mode: State and Properties take the place of the console and Variables.
  consoleToggle.hidden = doc?.kind === "app";
  variablesToggle.hidden = doc?.kind === "app" || doc?.kind === "script";
  drawModeToggles(doc);
}

// ===== the Data Explorer: one search over what holds data; the catalog and the blades beside it =====

function bladeDoc(name: string | null): void {
  const doc = makeDoc("blade", name ?? "New blade", null, null);
  editingBlade = true;
  const done = (): void => { editingBlade = false; close(doc); };
  const saved = (savedName: string): void => { editingBlade = false; rail.bladeSaved(savedName); void loadConnections(); };
  if (name !== null) void editBlade(doc.element, name, null, "other" as BladeKind, saved, done);
  else
    void showTemplatePicker(doc.element, (made) => {
      saved(made);
      void editBlade(doc.element, made, null, "other" as BladeKind, saved, done);
    });
  show(doc);
}

/** Where the Explorer's Insert goes: the focused document's selected cell (a script's cursor). */
function explorerTarget(): { document: string | null; cell: number | null; kind: string | null } {
  if (current?.notebook) return { document: current.title, cell: current.notebook.selectedNumber(), kind: "notebook" };
  if (current?.script) return { document: current.title, cell: current.script.cursorCell(), kind: "script" };
  return { document: null, cell: null, kind: null };
}

/** A Data Explorer result's code into the focused document: a notebook's selected cell (in its language:
 *  a SQL cell's SQL, a Python cell's Python; else a new cell below), a script's cursor (Python). */
function explorerInsert(insert: { sql?: string; python?: string }): { document: string; cell: number | null } {
  if (current?.notebook) {
    const done = current.notebook.insertCode(insert);
    return { document: current.title, cell: done.cell };
  }
  if (current?.script) {
    const code = insert.python ?? (insert.sql ? `sab.sql(${JSON.stringify(insert.sql)})` : "");
    current.script.insertText(code);
    return { document: current.title, cell: current.script.cursorCell() };
  }
  throw new Error("Open a notebook or a script to insert into.");
}

const explorerPane = mountExplorerPane({
  insert: (r: ExplorerResult) => {
    const done = explorerInsert(r.insert);
    return Promise.resolve(done.cell ? `cell ${done.cell} of ${done.document}` : done.document);
  },
  target: () => {
    const t = explorerTarget();
    return t.document ? (t.cell ? `cell ${t.cell} of ${t.document}` : t.document) : "a notebook or a script (none is in front)";
  },
  showGrid: (grid) => showGridAtHome(grid),
  openVariable: () => openVariables(),
  addTable: (anchor) => void openMenu(anchor, "Add a table", tableEntries()),
  toggled: () => {
    remember();
    drawStatus();
    window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize"))); // the editors measure again
  },
  popOut: () => void popExplorer().catch((e: Error) => errorHere(e)),
});
(document.querySelector(".wb-layout") as HTMLElement).prepend(explorerPane.element);

/** What the app generates, read-only (a table's transformations as one DuckDB query), with Fine-tune. */
function showGenerated(file: TreeFile): void {
  const { body, foot, close } = openDialog(`${file.name}: its transformations (read-only)`, true);
  body.append(h("pre", { class: "mono wb-generated" }, file.text ?? ""));
  foot.append(button("Fine-tune as a script", () => (close(), void fineTune(file.name)), { class: "primary" }), button("Close", () => close(), { class: "ghost" }));
}

/** Fine-tune as a script: the table's transformations as a new script in scripts/, opened here. */
async function fineTune(table: string): Promise<void> {
  try {
    const made = await api<{ path: string }>("/scripts/fine-tune", "POST", { table });
    await codex.refresh();
    await open(made.path);
  } catch (e) {
    errorHere(e);
  }
}

/** The page's New: a script here, a notebook on the Notebooks page (the creator's and the explorer's). */
function newHere(): void {
  const k: Kind = PAGE === "scripts" ? "script" : "notebook";
  const own = k === "script" ? scriptLanguage() : null;
  if (own) return void newModeFile(own);
  const start = tabKinds().find((t) => t.mark === k && t.start)?.start;
  if (!start) return;
  if (landing.kind()) {
    hideLanding();
    void go(withParams({ view: null, kind: k }), "push");
  }
  start.run();
}

// The Scripts page's Blades, under the files (the owner, 2026-11-21: "navigation on top, blade on bottom"): the
// blades list (catalogRail.ts) drawn here; a blade opens as a tab (bladeDoc). Elsewhere the Data Explorer's.
const bladesPane = PAGE === "scripts" ? h("section", { class: "rail-section wb-blades-pane", id: "blades", "aria-labelledby": "blades-title" }) : null;

// The page's own explorer on the left, always there (codeExplorer.ts): the project's scripts by module, or its
// notebooks; a click opens the file as a tab here.
const codex = mountCodeExplorer({
  page: PAGE,
  open: (file) => (file.item ? showGenerated(file) : void open(file.full)),
  action: (file, id) => {
    if (id === "fine-tune") void fineTune(file.name);
  },
  openAt: (file, line) => void openAt(file.full, line),
  newDocument: newHere,
  menu: topMenu, // the page's "…" (no top bar: the owner, 2026-11-21)
  lower: bladesPane ? { id: "blades", title: "Blades", element: bladesPane } : undefined,
  openNow: () => ({ paths: docs.map((d) => d.path ?? "").filter(Boolean), dirty: docs.filter((d) => d.dirty && d.path).map((d) => d.path!), front: current?.path ?? null }),
});
(document.querySelector(".wb-layout") as HTMLElement).prepend(codex.element);
codexHooks.mark = codex.mark;
// The rail's Blades (rail.ts) on this page, and an address that names the pane: the Blades pane, focused.
window.addEventListener("sab-blades", () => codex.showLower());
if (new URLSearchParams(location.search).get("pane") === "blades") window.setTimeout(() => codex.showLower(), 0);

// ===== full screen (the owner, 2026-11-21: "the ide pane should be fullscreenable") =====
const FULL_KEY = `wb-fullscreen:${PAGE}`;
let full = false;
/** The tabs and the editor fill the window (the rail, the explorer, the panels gone); remembered for the
 *  session, per page. */
function fullScreen(on?: boolean): boolean {
  full = on ?? !full;
  document.body.classList.toggle("wb-full", full);
  try {
    sessionStorage.setItem(FULL_KEY, full ? "1" : "0");
  } catch {
    /* storage refused: it lasts until a reload */
  }
  drawControls();
  window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  return full;
}
try {
  if (sessionStorage.getItem(FULL_KEY) === "1") fullScreen(true);
} catch {
  /* nothing kept */
}
document.addEventListener("keydown", (e) => {
  // Escape leaves full screen when nothing else took it (a member list, a dialog, a menu).
  if (e.key !== "Escape" || !full || e.defaultPrevented || document.querySelector("dialog[open], .wb-menu, .suggest-widget.visible")) return;
  fullScreen(false);
});
codexHooks.label = codex.setNewLabel;
codexHooks.typed = codex.typed;
codexHooks.refresh = () => void codex.refresh();
/** App mode's Streamlit cells panel: one list, shown in the canvas in front's panel. */
const streamlitCells = cellsPane((document, title, cell) => void goToCell(document, title, cell).catch((e: Error) => errorHere(e)));
paneReady = true;

/** An open table's grid, shown in the home window (the grids are its). */
function showGridAtHome(grid: string): void {
  const opened = window.open(`/g/${encodeURIComponent(grid)}#token=${encodeURIComponent(token)}`, HOME_WINDOW);
  if (!opened) errorHere("The browser blocked the grid's window. Allow pop-ups for this address.");
}

// ----- the Data Explorer popped out: the Data page in a window of its own (dataPage.ts; the owner,
// 2026-11-17: the pop-out and the Data page are not two pages doing one job). Its search goes with it in
// the address; the pane closes here (Ctrl+Shift+E opens it again).
if (explorerPane.popped()) explorerPane.setPopped(false); // a pop-out window from before: the pane is this window's

/** Pop the Explorer out: the Data page in a window of its own, with the pane's search; the pane closes here. */
async function popExplorer(): Promise<{ popped: boolean; page: string }> {
  openDataWindow(explorerPane.explorer.state());
  explorerPane.toggle(false);
  return { popped: true, page: "data" };
}

/** An Explorer's search handed to this window's pane (an older window's Move back). */
function explorerBack(state: ExplorerState): void {
  explorerPane.setPopped(false);
  explorerPane.toggle(true);
  explorerPane.explorer.setState(state);
}

/** Add API: API_<name>.py beside data.py when a project is open (else in the Workbench's folder). */
function addApi(): Promise<void> {
  const data = docs.find(isData);
  const folder = data?.path ? folderOf(data.path) : project?.folder;
  return openConnections({ addApi: true, folder }).then(() => void rail.loadBlades());
}

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
    { label: "Add API…", icon: "plus", run: () => void addApi() },
  ];
}

/** The catalog beside the Data Explorer: a connection's tables (or the search, without one). */
function browse(connection?: string): void {
  if (!explorerPane.isOpen()) explorerPane.toggle(true);
  explorerPane.flyout("catalog");
  if (connection) void rail.loadCatalogs(connection);
}

/** A Streamlit cells pane entry's click: its document in front (opened when it is not), the cell shown. */
async function goToCell(document: string | null, title: string, cell: number, line?: number | null): Promise<void> {
  let doc = docs.find((d) => (document ? d.path === document : !d.path && d.title === title));
  if (!doc && document) {
    await open(document);
    doc = docs.find((d) => d.path === document);
  }
  if (!doc) throw new Error(`${title} is not open here.`);
  show(doc);
  if (!viewOf(doc)?.goTo(cell, line)) throw new Error(`${title} has no cell ${cell} now.`);
}

/** A change to a cell's code from the canvas's property pane (a plan: the cell's code before and after,
 *  only the characters it names changed): made in the open document like typing, so the editor's Undo
 *  takes it back. The document is opened when it is not; the canvas stays in front. Refused when the
 *  cell is no longer what the plan was made from. */
async function applyCode(app: Doc | null, plan: CodePlan, history = true): Promise<boolean> {
  const same = (a: string | null, b: string): boolean => !!a && a.replace(/\\/g, "/") === b.replace(/\\/g, "/");
  let held = docs.find((d) => same(d.path, plan.document));
  if (!held) {
    await open(plan.document);
    held = docs.find((d) => same(d.path, plan.document));
    if (app) show(app);
  }
  if (!held) throw new Error(`${baseName(plan.document)} could not be opened.`);
  const tidy = (text: string): string => text.replace(/\n+$/, "");
  if (held.notebook) {
    const now = held.notebook.sourceOf(plan.cell);
    if (now === null) throw new Error(`${baseName(plan.document)} has no cell ${plan.cell} now.`);
    if (tidy(now) !== tidy(plan.before)) throw new Error(`${plan.where} changed since: nothing was written. Try again.`);
    held.notebook.editSource(plan.cell, tidy(plan.code));
  } else if (held.script) held.script.setSource(plan.cell, plan.code);
  else throw new Error(`${baseName(plan.document)} is not a notebook or a script.`);
  await held.streamlit?.sync().catch(() => null); // the server knows the cell as it is now
  if (history) app?.canvas?.codeChanged(plan);
  return true;
}

// ----- the Streamlit cells pane (App mode's panel): every cell that calls Streamlit, by document

/** The canvas the pane's marks are for: the one in front, else the last one that was. */
function markedCanvas(): Doc | null {
  return current?.canvas ? current : lastCanvas && docs.includes(lastCanvas) ? lastCanvas : (docs.find((d) => d.canvas) ?? null);
}

/** The pane drawn from what the server last said, each cell on the marked canvas's page marked. */
function drawPane(): void {
  if (!paneReady) return; // the pane is not made yet
  const canvasDoc = markedCanvas();
  const state = canvasDoc?.canvas?.state();
  const front = canvasDoc?.canvas?.report() as { page?: string | null } | undefined;
  const page = state?.pages.find((p) => p.id === front?.page) ?? state?.pages[0];
  streamlitCells.set(paneDocuments, new Set((page?.blocks ?? []).map((b) => `${b.document}#${b.cell}`)));
  // The canvas in front shows the list in its Streamlit cells panel.
  if (current?.canvas) current.modes?.redraw("cells");
}

/** The pane's entries from the server, soon (the open documents', and the project's files). */
function refreshPane(): void {
  if (paneTimer !== null) window.clearTimeout(paneTimer);
  paneTimer = window.setTimeout(() => {
    paneTimer = null;
    if (!canvasAnywhere("streamlit")) return; // no Streamlit cells without the extension
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

const waitFor = async <T>(found: () => T | null | undefined, ms = 8000): Promise<T | null> => {
  const until = Date.now() + ms;
  for (;;) {
    const value = found();
    if (value) return value;
    if (Date.now() > until) return null;
    await new Promise((r) => window.setTimeout(r, 100));
  }
};

/** A table's transformations, read-only (the Scripts and Notebooks pages' cards; the agent's
 *  tables.transformations): its cell, opened and in view, in the document that holds it; in a project
 *  data.ipynb opened when it is not. With no document for it, the grid's steps window. */
async function showTransformations(name: string): Promise<{ table: string; document: string | null; cell: number | null }> {
  const info = (tables.length ? tables : (tables = await fetchTables())).find((t) => t.name === name);
  if (!info) throw new Error(`No table named ${name} is open.`);
  const from = landing.kind();
  assignTables();
  let owner = tableOwner.get(name) ?? docs.find(isData);
  if (!owner && project?.data) {
    await open(project.data);
    assignTables();
    owner = tableOwner.get(name) ?? docs.find(isData);
  }
  const view = owner ? viewOf(owner) : undefined;
  if (!owner || !view) {
    // No notebook or script holds it: the grid's own steps window.
    if (!info.grid) throw new Error(`${name} has no grid open.`);
    const page = `/g/${encodeURIComponent(info.grid)}`;
    if (!window.open(`${page}?panel=steps#token=${encodeURIComponent(token)}`, `steps-${page}`, "popup,width=460,height=820")) errorHere("The browser blocked the steps window.");
    return { table: name, document: null, cell: null };
  }
  if (from) {
    hideLanding();
    void go(withParams({ view: null, kind: docKindOf(owner) ?? from }), "push");
  }
  show(owner);
  const line = await waitFor(() => view.tables().find((t) => t.name === name && t.cell));
  if (!line?.cell) throw new Error(`${name} has no cell in ${owner.title} yet.`);
  view.foldTables(false, name);
  view.goTo(line.cell);
  return { table: name, document: owner.path ?? owner.title, cell: line.cell };
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
  bladesHost: bladesPane ?? explorerPane.bladesHost,
  catalogHost: explorerPane.catalogHost,
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
  settings?: AppSettings;
  dictionary?: Descriptions;
}
// Per page (the owner, 2026-11-21): the Notebooks page's and the Scripts page's documents each their own; a
// session from before, both kinds in one, is split by kind once (workbenchPages.ts splitSession).
const SESSION_KEY = `workbench-documents:${PAGE}`;
try {
  splitSession(sessionStorage, "workbench-documents");
} catch {
  /* storage refused: nothing to split */
}
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
        ...(d.dirty || !d.path ? (d.notebook ? { cells: d.notebook.cells().map((c) => (withOutputs ? c : { ...c, outputs: [] })), next_cell: d.notebook.nextCell(), ...dataBody(d) } : d.canvas ? { pages: d.canvas.pages(), settings: d.canvas.settings() } : { text: d.script!.text() }) : {}),
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
  if (rememberTimer === null)
    rememberTimer = window.setTimeout(() => {
      rememberNow();
      void reportSab(); // the open project keeps this window's documents and groups for its next save
    }, 800);
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
    if (wrongPage(r.kind, PAGE)) continue; // the other page's
    const doc = r.kind === "notebook" ? openNotebook(r.path, r.cells ?? [], r.modified, r.next_cell, r.dictionary) : r.kind === "app" ? openApp(r.path, r.pages ?? [], r.modified, r.settings) : openScript(r.path, r.text ?? "", r.modified);
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

// ===== the rail's Notebooks, Scripts and Apps (rail.ts) =====

const KIND_WORDS: Record<Kind, { name: string; ending: string }> = {
  notebook: { name: "Notebooks", ending: ".ipynb" },
  script: { name: "Scripts", ending: ".py" },
  app: { name: "Apps", ending: APP_ENDING },
};
function codeKindOf(word: string | null): Kind | null {
  return word === "notebook" || word === "script" || word === "app" ? word : null;
}
function docKindOf(doc: Doc | null): Kind | null {
  return codeKindOf(doc?.kind ?? null);
}

/** The focused document's kind is the address's (replaced: a tab click is no rail move), so the rail
 *  marks Notebooks, Scripts or Apps; a blade's or a table's tab leaves it as it was. */
function followKind(doc: Doc | null): void {
  const k = docKindOf(doc);
  const here = new URLSearchParams(location.search);
  // A landing page in the address is the page on show (a reload's documents come back under it): its
  // kind stays (show() sets the document's kind as the landing makes way).
  if (here.get("view") === "list") return;
  if (k && here.get("kind") !== k) void go(withParams({ kind: k }), "replace");
}

/** A kind's document in front (the one in front already, else the last opened), in its mode. None
 *  open: that kind's landing page (its address: view=list). Apps: the canvas's Streamlit cells panel
 *  pane open beside the canvas, the cells to build its page from. */
function showKind(k: Kind): void {
  if (k === "app") appPanes();

  const mine = docKindOf(current) === k ? current : [...docs].reverse().find((d) => docKindOf(d) === k);
  if (mine) {
    show(mine);
    return;
  }
  void go(withParams({ kind: k, view: "list" }), "replace");
  showLanding(k);
}

/** An app comes forward from the rail's Apps: its Streamlit cells panel beside the canvas, the cells to
 *  build its page from (the owner: "do we still get a cell navigator"). */
function appPanes(): void {
  window.setTimeout(() => {
    if (current?.canvas && panelOn("workbench.streamlit")) current.modes?.toggle("cells", true);
  });
}

/** A reference's click on the Connections page (connectionsWindow.ts): its document here, at its cell. */
async function openCell(path: string, cell: number | null): Promise<void> {
  if (cell) await goToCell(path, baseName(path), cell);
  else await open(path);
}
setCellOpener(openCell);

// ===== start =====

/** Nothing open: the empty state has the area (Start a notebook; Start an app once app pages exist). */
function drawEmpty(): void {
  const none = docs.length === 0;
  // Nothing open: the page's creator (the landing's New and Try it with sample data), as the rail lands.
  if (none && PAGE === "scripts") {
    groups.element.hidden = true;
    empty.hidden = true;
    layout.empty(true);
    layout.status.hidden = true;
    if (!landing.kind()) landing.show("script");
    return;
  }
  if (landing.kind()) {
    // The landing is on show: it has the area (never the empty state over it).
    empty.hidden = true;
    return;
  }
  groups.element.hidden = none;
  empty.hidden = !none;
  layout.empty(none);
  layout.status.hidden = none;
  if (!none || empty.childElementCount) return;
  const app = tabKinds().find((k) => k.mark === "app" && k.start);
  clear(
    empty,
    h("div", { class: "wb-empty-choice" }, h("span", { class: "wb-empty-icon" }, icon("notebook")), button("Start a notebook", () => void openNotebook(null, [], null), { icon: "plus", class: "primary" })),
    h(
      "div",
      { class: "wb-empty-choice app" },
      h("span", { class: "wb-empty-icon app" }, icon(app?.icon ?? "page")),
      app
        ? button(app.id === "page" ? "Start an app" : app.start!.label, () => app.start!.run(), { icon: "plus", class: "primary" })
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
const saves = (): boolean => isCode() || !!current?.canvas || !!current?.workbook || !!current?.codefile;
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
/** A swap's code (connection_swap.py's repoint): the open document's ticked cells name another connection,
 *  the name only (the server's rules, on the window's own unsaved text); an edit like any other. */
async function repointDocument(a: Record<string, unknown>): Promise<{ cells: (number | null)[] }> {
  const path = text(a, "path");
  const from = text(a, "from");
  const to = text(a, "to");
  if (!path || !from || !to) throw new Error("Send path, from and to.");
  const key = (p: string): string => p.replace(/\\/g, "/").toLowerCase();
  const doc = docs.find((d) => d.path && key(d.path) === key(path));
  if (!doc) throw new Error(`${path} is not open here.`);
  const wanted = Array.isArray(a.cells) ? (a.cells as unknown[]) : null;
  const done: (number | null)[] = [];
  if (doc.notebook) {
    for (const cell of doc.notebook.cells()) {
      const number = cell.number ?? null;
      if (number === null || (wanted && !wanted.includes(number)) || (cell.role && cell.role !== "maker")) continue;
      if ((cell.kind === "sql" || cell.kind === "dax") && cell.connection) {
        const line = `%%${cell.kind} ${cell.connection}`;
        const answer = await api<{ text: string }>("/connections/rewrite", "POST", { kind: "line", text: line, from, to });
        if (answer.text === line) continue;
        const named = answer.text.replace(/^%%\w+\s+/, "").replace(/^'(.*)'$/, "$1");
        doc.notebook.setCellConnection(number, named);
        done.push(number);
      } else if (cell.kind === "code") {
        const answer = await api<{ text: string; changed: number }>("/connections/rewrite", "POST", { kind: "python", text: cell.source, from, to });
        if (!answer.changed) continue;
        doc.notebook.setSource(number, answer.text);
        done.push(number);
      }
    }
  } else if (doc.script) {
    const answer = await api<{ text: string; cells: (number | null)[] }>("/connections/rewrite", "POST", { kind: "script", text: doc.script.text(), from, to, cells: wanted });
    if (answer.cells.length) doc.script.replaceText(answer.text);
    done.push(...answer.cells);
  } else {
    throw new Error(`${path} is not a notebook or a script.`);
  }
  return { cells: done };
}

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
      // A notebook's kind: data (the project's data.ipynb), app (any other in a project), "" (plain).
      ...(d.notebook ? { role: notebookRole(d.path) } : {}),
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
    panes: { ...layout.state(), data_explorer: explorerPane.popped() ? "popped" : explorerPane.isOpen() ? "open" : "closed" },
    cursor: current?.script || current?.notebook ? cursor : null,
  };
}

const COMMANDS: Command[] = [
  // File
  { id: "file.newNotebook", group: "File", title: "New notebook", keys: inApp() ? "Ctrl+N" : undefined, run: () => void openNotebook(null, [], null) },
  { id: "file.newScript", group: "File", title: "New script", run: () => void openScript(null, "", null) },
  { id: "file.newApp", group: "File", title: "New Streamlit app", when: () => canvasAnywhere("streamlit"), whyNot: "the Streamlit extension is not installed (Extensions: Install)", run: () => {
    const doc = openApp(null, [], null);
    return { document: doc.title };
  } },
  { id: "file.open", group: "File", title: "Open a notebook, script or Streamlit app…", keys: "Ctrl+O", args: "path: the file (without it, the file chooser opens)", run: (a) => open(text(a, "path")) },
  { id: "file.openCell", agentOnly: true, group: "File", title: "Open a document at a cell (a connection's reference)", args: "path: the file; cell: the cell's own number (none: the document)", run: (a) => {
    const path = text(a, "path");
    if (!path) throw new Error("Name the file: path.");
    return openCell(path, num(a, "cell") ?? null);
  } },
  { id: "file.save", group: "File", title: "Save (the open project, when it is in front)", keys: "Ctrl+S", when: () => saves() || sabOpen(), whyNot: "nothing that saves is in front", run: () => saveFront() },
  { id: "project.save", group: "Project", title: "Save the project (its .sab/ state)", when: sabOpen, whyNot: "no project is open", run: () => saveProject() },
  { id: "project.saveAs", group: "Project", title: "Copy the project to another folder…", when: sabOpen, whyNot: "no project is open", run: () => copyProject() },
  { id: "project.outline", group: "Project", title: "Export outline (ARCHITECTURE.md)", when: sabOpen, whyNot: "no project is open", run: () => exportOutline() },
  { id: "project.close", group: "Project", title: "Close the project", when: sabOpen, whyNot: "no project file is open", run: () => closeProject() },
  { id: "project.saveDocuments", agentOnly: true, group: "Project", title: "Save the project's documents that have unsaved changes", args: "folder: the project's folder", run: (a) => saveProjectDocuments(text(a, "folder")) },
  { id: "file.saveAs", group: "File", title: "Save a copy as…", keys: "Ctrl+Shift+S", when: saves, whyNot: "nothing that saves is in front", run: () => save(current, true) },
  { id: "file.exportScript", group: "File", title: "Export as one Python script…", args: "path: where it goes (without it, the file chooser opens)", when: isCode, whyNot: "no notebook or script is in front", run: (a, from) => exportDocument(current, "script", text(a, "path"), from.agent) },
  { id: "file.exportNotebook", group: "File", title: "Export as one notebook…", args: "path: where it goes (without it, the file chooser opens)", when: isCode, whyNot: "no notebook or script is in front", run: (a, from) => exportDocument(current, "notebook", text(a, "path"), from.agent) },
  { id: "project.new", group: "Project", title: "New project…", args: "name: its name; folder: where it goes (default: the projects folder); notebooks: names of notebooks to make; app: true for a Streamlit app; type: a project type (project_types) (without a name, New project's dialog opens)", run: (a, from) => newProject(text(a, "folder"), text(a, "name"), Array.isArray(a.notebooks) ? (a.notebooks as string[]) : [], typeof a.app === "boolean" ? a.app : undefined, from.agent, text(a, "type")) },
  { id: "workbook.new", group: "Workbook", title: "New Excel workbook", args: "(the Excel canvas: offered while the open project's mode names it)", when: () => offersCanvas("excel"), whyNot: "the open project's mode has no Excel canvas", run: () => openWorkbook(null).workbook!.report() },
  { id: "workbook.play", group: "Workbook", title: "Play the workbook", when: () => !!current?.workbook, whyNot: "no workbook is in front", run: () => workbookInFront().play() },
  { id: "workbook.edit", group: "Workbook", title: "Edit the workbook's blocks", when: () => !!current?.workbook, whyNot: "no workbook is in front", run: () => (workbookInFront().edit(), workbookInFront().report()) },
  { id: "workbook.report", group: "Workbook", title: "The workbook in front, as it stands", when: () => !!current?.workbook, whyNot: "no workbook is in front", run: () => workbookInFront().report() },
  { id: "project.open", group: "Project", title: "Open project…", args: "folder: the project's folder (without it, the file chooser opens)", run: (a) => openProject(text(a, "folder")) },
  { id: "project.exportData", group: "Project", title: "Export data.py (from data.ipynb)", when: () => docs.some(isData) || !!project, whyNot: "no project is open", run: () => exportData() },
  // The desktop app's Ctrl+W (desktopApp.ts): the document in front, and the window once none is left.
  { id: "file.closeTab", group: "File", title: "Close the document in front (the window when none is open)", keys: inApp() ? "Ctrl+W" : undefined, run: () => (current ? close(current) : closeWindow()) },
  { id: "tabs.reopen", group: "Tabs", title: "Reopen the last closed table (in the home window)", keys: inApp() ? "Ctrl+Shift+T" : undefined, run: () => api("/grids/reopen", "POST").catch((e: ApiError) => (e.status === 404 ? toast("No closed table to reopen.") : errorHere(e))) },
  { id: "file.close", group: "File", title: "Close the document", args: "index: a document (default: the one in front)", when: () => docs.length > 0, whyNot: "nothing is open", run: (a) => {
    const at = num(a, "index");
    const doc = at === undefined ? current : docs[at];
    if (!doc) throw new Error(`There is no document ${at}.`);
    close(doc);
  } },
  // Documents
  { id: "documents", agentOnly: true, group: "Documents", title: "What is open", run: () => documents() },
  { id: "doc.read", agentOnly: true, group: "Documents", title: "The front document's text or cells", when: isCode, whyNot: "no notebook or script is in front", run: () => (current?.notebook ? { kind: "notebook", cells: current.notebook.cells() } : { kind: "script", text: script().text() }) },
  { id: "doc.repoint", agentOnly: true, group: "Documents", title: "Point an open document's cells at another connection (unsaved until Save)", args: "path; from; to; cells: the cells' own numbers (null: a script's main code)", run: (a) => repointDocument(a) },
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
  { id: "lineage.open", group: "Cell", title: "Lineage: the cell back to the data, with its values", args: "number: a cell's own number (default: the selected cell, or the cursor's); block: a block of the canvas in front", when: () => isCode() || isCanvas(), whyNot: "no notebook, script or Streamlit app is in front", run: async (a) => {
    const graph = await showLineage({ number: num(a, "number"), block: text(a, "block") });
    return { target: graph.nodes.find((n) => n.target)?.label ?? null, nodes: graph.nodes.length, mermaid: graph.mermaid };
  } },
  { id: "cell.approve", group: "Cell", title: "Approve the cell's output", args: "number: the cell's own number (default: the selected cell); remove: true takes the approval away", when: isNotebook, whyNot: "the document in front is not a notebook", run: (a) => notebook().approve(num(a, "number"), a.remove === true) },
  { id: "cell.unapprove", group: "Cell", title: "Remove the cell's approval", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().approve(undefined, true) },
  { id: "approvals.list", agentOnly: true, group: "Cell", title: "The approved cells and how each output differs now", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => ({ document: current!.title, approvals: notebook().approvals() }) },
  { id: "cell.goTo", group: "Cell", title: "Go to a cell by its number", args: "number: the cell's own number (as @cell7 links to it)", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
    const number = num(a, "number");
    if (number === undefined) throw new Error("Send the cell's number.");
    if (!tablesView().goTo(number)) throw new Error(`There is no cell ${number} in the document in front.`);
    return { cell: number };
  } },
  // Tables: every table open in the grid has a read-only cell in its document
  { id: "tables.list", agentOnly: true, group: "Tables", title: "The document's tables and each cell's state", when: isCode, whyNot: "no notebook or script is in front", run: () => ({ document: current!.title, tables: tablesView().tables() }) },
  { id: "tables.add", group: "Tables", title: "Add a table open in Grids to the document in front (its read-only cell)", args: "table: the table's name", when: isCode, whyNot: "no notebook or script is in front", run: async (a) => {
    const table = text(a, "table");
    if (!table) throw new Error("Send the table's name.");
    return { table: await giveTable(current!, table), document: current!.title };
  } },
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
  // The Workbench's modes (2026-11-15): App, Notebook, Script and Data
  { id: "mode.panel", group: "View", title: "Show or hide a panel of the document in front (Properties, State, Outline, Run settings, Run history)", args: 'panel: "properties", "state", "outline", "runSettings" or "runHistory"; show: true or false (default: the other way)', when: () => !!current?.modes, whyNot: "the document in front has no panels", run: (a) => {
    const panel = text(a, "panel");
    const doc = current!;
    const names: Record<string, string> = { properties: "Properties", state: "State", outline: "Outline", runSettings: "Run settings", runHistory: "Run history" };
    if (panel && names[panel] && !panelOn(`workbench.${panel}`)) throw new Error(turnedOff(names[panel]));
    if (!panel || !doc.modes!.panels().some((p) => p.id === panel)) throw new Error(`The document in front has these panels: ${doc.modes!.panels().map((p) => p.id).join(", ") || "none (turned off in Settings)"}.`);
    const show = a.show === undefined ? undefined : a.show === true;
    const open = doc.modes!.toggle(panel, show);
    drawStatus();
    return { panel, open };
  } },
  { id: "canvas.select", group: "Streamlit app", title: "Select a block (Properties shows it; none: the page settings)", args: "block: its id (canvas.state lists them; none: no block)", when: isCanvas, whyNot: NO_CANVAS, run: (a) => {
    canvas().select(text(a, "block") ?? null);
    return { selected: canvas().selected()?.id ?? null };
  } },
  { id: "canvas.properties", agentOnly: true, group: "Streamlit app", title: "Properties: the selected block (name, size, source cell, makes, reads, feeds, widget values) or the page settings", when: isCanvas, whyNot: NO_CANVAS, run: () => {
    const block = canvas().selected();
    if (!block) return { settings: canvas().settings() };
    const rows = current!.app?.rows() ?? [];
    return { block: { id: block.id, name: block.name, w: block.w, h: block.h, source: block.where, document: block.document, cell: block.cell, makes: block.makes, reads: [...block.tables, ...block.reads] }, feeds: canvas().feeds(block.id).map((b) => b.name ?? b.where), widget_values: rows.filter((r) => r.block === block.name) };
  } },
  { id: "canvas.settings", group: "Streamlit app", title: "The page settings: title, icon, layout, logo, theme colours", args: 'title, icon, layout ("wide" or "centered"), logo (a path), colours ({"primary": "#c8102e"}); a part is enough', when: isCanvas, whyNot: NO_CANVAS, run: async (a) => {
    const sent = Object.fromEntries(Object.entries(a).filter(([k]) => ["title", "icon", "layout", "logo", "colours"].includes(k)));
    if (Object.keys(sent).length && !(await canvas().setSettings(sent))) throw new Error("The page settings were not changed.");
    return canvas().settings();
  } },
  { id: "canvas.session", agentOnly: true, group: "Streamlit app", title: "State: what the live page's session holds (each key, its value, its block)", when: isCanvas, whyNot: NO_CANVAS, run: () => canvas().session() },
  { id: "canvas.resetState", group: "Streamlit app", title: "Reset state: the live page again with a fresh session", when: isCanvas, whyNot: NO_CANVAS, run: () => current!.app?.resetState() },
  { id: "canvas.add", group: "Streamlit app", title: "Add a Toolbox element or container to the page", args: "element: its id (slider, selectbox, columns, tabs...); parent, slot: a container to put it in; row, column: where", when: isCanvas, whyNot: NO_CANVAS, run: async (a) => {
    const tool = text(a, "element");
    if (!tool) throw new Error("Send element: a Toolbox item's id.");
    const where: Where = { ...(text(a, "parent") ? { parent: text(a, "parent"), slot: num(a, "slot") ?? 0 } : {}), ...(num(a, "row") !== undefined ? { row: num(a, "row") } : {}), ...(num(a, "column") !== undefined ? { column: num(a, "column") } : {}) };
    const kind = ["columns", "tabs", "expander", "container", "form", "sidebar", "popover"].includes(tool) ? "container" : "element";
    return canvas().addTool(tool, kind, Object.keys(where).length ? where : undefined);
  } },
  { id: "canvas.selectMany", group: "Streamlit app", title: "Select several blocks (the first is the one the others follow)", args: "blocks: their ids", when: isCanvas, whyNot: NO_CANVAS, run: (a) => {
    canvas().selectMany(Array.isArray(a.blocks) ? a.blocks.map(String) : []);
    return { selected: canvas().selectedIds() };
  } },
  { id: "canvas.arrange", group: "Streamlit app", title: "Arrange the selected blocks: align, same size, distribute; or reset the layout", args: 'how: "left", "right", "centre", "top", "bottom", "same_width", "same_height", "distribute" or "reset"; blocks: their ids (default: the selected ones)', when: isCanvas, whyNot: NO_CANVAS, run: (a) => canvas().arrange((text(a, "how") ?? "left") as Arrange, Array.isArray(a.blocks) ? a.blocks.map(String) : undefined) },
  { id: "canvas.view", group: "Streamlit app", title: "The design surface: snaplines, the ruler, sample rows, its width", args: 'snaplines, rulers, sampleRows: true or false; width: "wide", "centered" or "phone"', when: isCanvas, whyNot: NO_CANVAS, run: async (a) => {
    const width = text(a, "width");
    if (width) await canvas().designWidth(width as DesignWidth);
    const next = Object.fromEntries(["snaplines", "rulers", "sampleRows"].filter((k) => typeof a[k] === "boolean").map((k) => [k, a[k]]));
    return canvas().view(next);
  } },
  { id: "canvas.panel", group: "Streamlit app", title: "Open the Toolbox or the Document Outline", args: 'panel: "toolbox" or "outline"', when: isCanvas, whyNot: NO_CANVAS, run: (a) => ({ open: current!.modes?.toggle(text(a, "panel") === "outline" ? "outline" : "toolbox", true) ?? false }) },
  { id: "streamlit.addToApp", group: "Streamlit app", title: "Add to app: the selected cell onto the canvas's page", args: "number: the cell's own number (default: the selected cell)", when: () => !!current?.notebook && !!markedCanvas()?.canvas, whyNot: "Open a Streamlit app and select a notebook's cell first.", run: async (a) => {
    const from = current!;
    const view = from.notebook!;
    const number = num(a, "number") ?? view.cells()[view.selected()]?.number;
    if (typeof number !== "number") throw new Error("Select a cell of yours first.");
    if (!from.path || from.dirty) {
      if (!(await save(from))) throw new Error(`Save ${from.title} first: a block links to a cell in a saved file.`);
    }
    const app = markedCanvas()!;
    await from.streamlit?.sync().catch(() => null);
    show(app);
    return { placed: await app.canvas!.place({ document: from.path, cell: number, title: from.title }) };
  } },
  { id: "canvas.undo", group: "Streamlit app", title: "Undo the last layout change", when: isCanvas, whyNot: NO_CANVAS, run: () => canvas().undo() },
  { id: "canvas.redo", group: "Streamlit app", title: "Redo the layout change undone", when: isCanvas, whyNot: NO_CANVAS, run: () => canvas().redo() },
  { id: "canvas.duplicate", group: "Streamlit app", title: "Duplicate a block (another block linked to the same cell)", args: "block: its id (default: the selected one)", when: isCanvas, whyNot: NO_CANVAS, run: (a) => canvas().duplicate(text(a, "block")) },
  { id: "canvas.align", group: "Streamlit app", title: "Align a block: left edge, centre, right edge or full width", args: 'how: "left", "centre", "right" or "full"; block: its id (default: the selected one)', when: isCanvas, whyNot: NO_CANVAS, run: (a) => {
    const how = text(a, "how") ?? "left";
    if (!["left", "centre", "right", "full"].includes(how)) throw new Error('how is "left", "centre", "right" or "full".');
    return canvas().align(how as Align, text(a, "block"));
  } },
  { id: "canvas.zoom", group: "Streamlit app", title: "Zoom the board", args: "percent: 50 to 150 (default: 100)", when: isCanvas, whyNot: NO_CANVAS, run: (a) => ({ percent: canvas().zoom(num(a, "percent") ?? 100) }) },
  { id: "canvas.preview", group: "Streamlit app", title: "Play's preview: Desktop, Tablet or Phone; Light or Dark (the app only)", args: 'device: "desktop", "tablet" or "phone"; theme: "light", "dark" or null (as the Workbench)', when: isCanvas, whyNot: NO_CANVAS, run: (a) => {
    const device = text(a, "device");
    if (device !== undefined && !["desktop", "tablet", "phone"].includes(device)) throw new Error('device is "desktop", "tablet" or "phone".');
    const theme = a.theme === null ? null : text(a, "theme");
    if (theme !== undefined && theme !== null && theme !== "light" && theme !== "dark") throw new Error('theme is "light", "dark" or null.');
    return canvas().preview(device as Device | undefined, theme as "light" | "dark" | null | undefined);
  } },
  { id: "canvas.addStarter", group: "Streamlit app", title: "Add a starter: a named cell of the mockups notebook, placed on the page", args: "name: a Streamlit starter (data.starterList); values: its blanks, as blades_snippet names them (without them, its form opens); row, column: where", when: isCanvas, whyNot: NO_CANVAS, run: async (a) => {
    const name = text(a, "name");
    if (!name) throw new Error("Send name: a starter (data.starterList lists them).");
    const row = num(a, "row");
    const column = num(a, "column");
    const values = a.values && typeof a.values === "object" ? (a.values as Record<string, unknown>) : undefined;
    return addStarter(current!, name, row !== undefined ? { row, column: column ?? 1 } : undefined, values);
  } },
  { id: "data.starters", group: "Data", title: "The Starters panel beside the canvas (the starter gallery)", args: "show: true or false (default: the other way)", when: isCanvas, whyNot: NO_CANVAS, run: (a) => {
    if (!panelOn("workbench.starters")) throw new Error(turnedOff("Starters"));
    return { starters: current!.modes!.toggle("starters", a.show === undefined ? undefined : a.show === true) };
  } },
  { id: "data.starterList", agentOnly: true, group: "Data", title: "The starter gallery: the Streamlit starters by family", run: () => gallery.list() },
  { id: "notebook.runOrder", agentOnly: true, group: "Notebook", title: "The run order: each cell's makes, reads and state (notRun, edited, outOfDate with the names, current)", when: isNotebook, whyNot: "the document in front is not a notebook", run: async () => (await refreshFlow(current!))?.cells ?? [] },
  { id: "notebook.outline", agentOnly: true, group: "Notebook", title: "The Outline: the Markdown headings and the named cells", when: isNotebook, whyNot: "the document in front is not a notebook", run: async () => (await refreshFlow(current!))?.outline ?? [] },
  { id: "run.upToHere", group: "Run", title: "Run up to here: every cell from the top to the selected one", args: "number: a cell's own number (default: the selected cell)", when: isNotebook, whyNot: "the document in front is not a notebook", run: async (a) => {
    await notebook().runUpTo(num(a, "number"));
    return (await refreshFlow(current!))?.cells ?? [];
  } },
  { id: "notebook.present", group: "Notebook", title: "Present: the notebook as a document (no code)", args: "on: true or false (default: the other way)", when: () => isNotebook() && !dataViews.has(current!), whyNot: "the document in front is not a notebook (data.ipynb has its own views)", run: (a) => ({ presenting: present(current!, a.on === undefined ? undefined : a.on === true) }) },
  { id: "script.runScheduled", group: "Run", title: "Run as scheduled: the script as a fresh process with no app", when: isScript, whyNot: "the document in front is not a script", run: () => runScheduled(current!) },
  { id: "script.history", agentOnly: true, group: "Run", title: "The script's run history", when: isScript, whyNot: "the document in front is not a script", run: async () => (current!.path ? runHistory(current!.path) : []) },
  { id: "data.view", group: "Data", title: "data.ipynb's view: Cells, Lineage or Dictionary", args: 'view: "cells", "lineage" or "dictionary"', when: () => !!current && dataViews.has(current), whyNot: "the document in front is not a project's data.ipynb", run: (a) => {
    const view = text(a, "view") ?? "cells";
    if (view !== "cells" && view !== "lineage" && view !== "dictionary") throw new Error('view is "cells", "lineage" or "dictionary".');
    return { view: setDataView(current!, view) };
  } },
  { id: "dictionary.list", agentOnly: true, group: "Data", title: "The data dictionary: each table's columns, plain types, descriptions, where each comes from", when: () => !!current && dataViews.has(current), whyNot: "the document in front is not a project's data.ipynb", run: () => dictionaryTables(current!) },
  { id: "dictionary.describe", group: "Data", title: "Describe a table or a column in the data dictionary (kept in data.ipynb, written into data.py)", args: "table; column (none: the table itself); text (empty: no description)", when: () => !!current && dataViews.has(current), whyNot: "the document in front is not a project's data.ipynb", run: (a) => {
    const table = text(a, "table");
    if (!table) throw new Error("Send table.");
    const said = describe(current!, table, text(a, "column") ?? null, text(a, "text") ?? "");
    void drawDictionaryView(current!);
    return said;
  } },
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
  // Full screen (the owner, 2026-11-21: "the ide pane should be fullscreenable"): the tabs and the editor fill
  // the window; the rail, the explorer and the bottom panels go; Escape or the same button comes back.
  { id: "view.fullScreen", group: "View", title: "Full screen", keys: "F11", args: "on: true or false (default: the other way)", run: (a) => ({ on: fullScreen(typeof a.on === "boolean" ? a.on : undefined) }) },
  { id: "view.files", group: "View", title: "Show or hide the explorer", keys: "Ctrl+B", args: "show: true or false (default: the other way)", run: (a) => ({ open: codex.toggle(typeof a.show === "boolean" ? a.show : undefined) }) },
  ...(PAGE === "scripts"
    ? [{ id: "search.scripts", group: "Find", title: "Search in scripts…", keys: "Ctrl+Shift+F", run: () => (searchScripts({ openAt: (p: string, line: number) => void openAt(p, line) }, () => (current?.script ? { path: () => current!.path, text: () => current!.script!.text(), python: () => current!.python, replaceText: (t: string) => current!.script!.replaceText(t), reveal: (line: number) => current!.script!.reveal(line) } : null)), { opened: true }) }]
    : []),
  { id: "view.explorer", group: "View", title: "Show or hide the Data Explorer", keys: "Ctrl+Shift+E", args: "show: true or false (default: the other way)", when: () => panelOn("workbench.explorer"), whyNot: turnedOff("The Data Explorer"), run: (a) => {
    const show = typeof a.show === "boolean" ? a.show : undefined;
    return { open: explorerPane.toggle(show), popped: false };
  } },
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
  // The open tables and the blades' variables (once the Data panel's; the Data Explorer finds them)
  { id: "data.list", agentOnly: true, group: "Data", title: "The open tables and the blades' variables (the Data Explorer finds more: explorer.search)", run: () => ({ tables: tables.map((t) => ({ name: t.name, rows: t.rows ?? null, source: t.source ?? "", steps: t.steps })), variables: bladeVariables.map((b) => ({ name: b.variable ?? b.name, blade: b.name, description: b.description })), explorer: explorerPane.popped() ? "popped" : explorerPane.isOpen() ? "open" : "closed" }) },
  // The Data Explorer (workbenchExplorer.ts, dataExplorer.ts): its search, its Insert, popping out and back
  { id: "explorer.search", group: "Data", title: "Search the Data Explorer (it opens): its results as data", args: "text; kinds: a list of connections, tables, columns, structures, apis, variables, blades; connection; column: a column's exact name", when: () => panelOn("workbench.explorer"), whyNot: turnedOff("The Data Explorer"), run: async (a) => {
    const kinds = Array.isArray(a.kinds) ? a.kinds.map(String) : typeof a.kinds === "string" ? a.kinds.split(",") : [];
    const state: ExplorerState = { text: text(a, "text") ?? "", kinds, connection: text(a, "connection") ?? "", column: text(a, "column") ?? "", scroll: 0 };
    explorerPane.toggle(true);
    explorerPane.explorer.setState(state);
    const params = new URLSearchParams({ q: state.text, kinds: state.kinds.join(","), connection: state.connection, column: state.column });
    return api(`/explorer/search?${params.toString()}`);
  } },
  { id: "explorer.insert", group: "Data", title: "Insert a Data Explorer result's code into the focused document (a notebook's selected cell, a script's cursor)", args: "insert: {sql, python} (a result's insert); name: the result's name", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
    const insert = (a.insert && typeof a.insert === "object" ? a.insert : {}) as { sql?: string; python?: string };
    if (typeof insert.sql !== "string" && typeof insert.python !== "string") throw new Error("Send insert: {sql, python}, as explorer_search's result has it.");
    return explorerInsert({ ...(typeof insert.sql === "string" ? { sql: insert.sql } : {}), ...(typeof insert.python === "string" ? { python: insert.python } : {}) });
  } },
  { id: "explorer.target", agentOnly: true, group: "Data", title: "Where the Data Explorer's Insert goes: the focused document and its cell", run: () => explorerTarget() },
  { id: "explorer.popOut", group: "Data", title: "Pop the Data Explorer out: the Data page in a window of its own, with its search", when: () => panelOn("workbench.explorer"), whyNot: turnedOff("The Data Explorer"), run: () => popExplorer() },
  { id: "tables.transformations", group: "Tables", title: "Show a table's transformations (its read-only cell, wherever it lives)", args: "table: the table's name", run: (a) => {
    const table = text(a, "table");
    if (!table) throw new Error("Send the table's name.");
    return showTransformations(table);
  } },
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
  { id: "data.blades", group: "Data", title: "Show the blades and connections", run: () => {
    if (!explorerPane.isOpen()) explorerPane.toggle(true);
    explorerPane.flyout("blades");
  } },
  { id: "data.closeFlyout", group: "Data", title: "Close the catalog or the blades beside the Data Explorer", when: () => explorerPane.flyoutShown() !== null, whyNot: "neither is open", run: () => explorerPane.flyout(null) },
  { id: "data.addConnection", group: "Data", title: "Add connection…", run: () => openConnections().then(() => void rail.loadBlades()) },
  { id: "data.addApi", group: "Data", title: "Add API…", run: () => addApi() },
  { id: "view.variablesRefresh", group: "View", title: "Read the variables again", when: isCode, whyNot: "no notebook or script is in front", run: () => variables.refresh().then(() => variables.snapshot()) },
  // Getting around (nav.ts): the mark's Home, and the browser's Back and Forward inside the app
  { id: "nav.home", group: "Go", title: "Home: Projects, in the home window", keys: "Alt+Home", run: () => goHome() },
  { id: "nav.back", group: "Go", title: "Back", keys: "Alt+Left", when: canGoBack, whyNot: "nothing to go back to in this window", run: () => back() },
  { id: "nav.forward", group: "Go", title: "Forward", keys: "Alt+Right", run: () => forward() },
  // Help
  { id: "help.shortcuts", group: "Help", title: "Keyboard shortcuts", keys: "?", run: () => openShortcuts() },
  { id: "help.atCursor", group: "Help", title: "Help on the name at the cursor", keys: "F1", when: isCode, whyNot: "no notebook or script is in front", run: () => showHelp() },
  { id: "commands", agentOnly: true, group: "Help", title: "Every command and its arguments", run: () => allCommands().map((c) => ({ id: c.id, title: c.title, group: c.group, keys: c.keys ?? null, args: c.args ?? null, available: c.when ? c.when() : true })) },
];
registerCommands(COMMANDS);
mountShortcutKeys(); // ? and Ctrl+/ (outside an editor): the keyboard shortcuts
registerCommands(betaCommands()); // beta mode on or off, Leave a note…, Export beta log…
registerCommands(updateCommands()); // Update to X, What's new
registerCommands(claudeCommands()); // Launch Claude (Claude Code, Claude Desktop)
// No token and no good cookie (a bookmark after a restart): the page says how to open the app.
void requireSession();
// A file opened with the app (`swissarmybench open <file>`, Open with, a drop: server/desktop.py file_page) and
// no Workbench window to take it: /workbench?file=<path> opens it here, and the address forgets it.
const fileAsked = (() => {
  const url = new URL(location.href);
  const file = url.searchParams.get("file");
  if (!file) return null;
  url.searchParams.delete("file");
  history.replaceState(history.state, "", url);
  return file;
})();
// Getting around: Back closes a dialog and moves inside Connections; a dialog the address names opens.
// The rail's Notebooks, Scripts and Apps (?kind= in the address): Back and Forward bring that kind's
// document forward again.
mountNav("workbench", {
  show: (url) => {
    const k = codeKindOf(url.searchParams.get("kind"));
    if (k && url.searchParams.get("view") === "list") showLanding(k);
    else {
      hideLanding();
      if (k) showKind(k);
    }
  },
});
mountNavRail("workbench");
startNav();
if (fileAsked) void open(fileAsked);
// Beta mode (the beta log and Leave a note…) in this window too; nothing while it is off.
mountBeta("workbench", { window: POPPED ? "popout" : "main", tabs: () => docs.map((d) => kindOf(d)) });
// What is sent to the agent or Analyze names the document it came from.
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
  "Ctrl+Shift+E": "view.explorer",
  F11: "view.fullScreen",
  "Ctrl+B": "view.files",
  ...(PAGE === "scripts" ? { "Ctrl+Shift+F": "search.scripts" } : {}),
  "Ctrl+1": "view.source",
  "Ctrl+2": "console.focus",
  "Ctrl+3": "view.variables",
  "Ctrl+Shift+1": "view.focus",
  "Ctrl+\\": "group.splitRight",
  "Ctrl+Alt+PageDown": "doc.next",
  "Ctrl+Alt+PageUp": "doc.previous",
};
/** In the desktop app the browser's keys are the window's too (desktopApp.ts); in a browser, the browser's. */
const APP_KEYS: Record<string, string> = inApp()
  ? { "Ctrl+W": "file.closeTab", "Ctrl+T": "file.newNotebook", "Ctrl+N": "file.newNotebook", "Ctrl+Tab": "doc.next", "Ctrl+Shift+Tab": "doc.previous", "Ctrl+Shift+T": "tabs.reopen" }
  : {};

function keyName(e: KeyboardEvent): string {
  const key = /^Digit\d$/.test(e.code) ? e.code.slice(5) : e.key.length === 1 ? e.key.toUpperCase() : e.key;
  return [e.ctrlKey || e.metaKey ? "Ctrl" : "", e.altKey ? "Alt" : "", e.shiftKey ? "Shift" : "", key].filter(Boolean).join("+");
}

document.addEventListener(
  "keydown",
  (e) => {
    const id = WINDOW_KEYS[keyName(e)] ?? APP_KEYS[keyName(e)];
    if (!id) return;
    // F5 would reload the window (stopping every kernel), F1 open the browser's help: the window's own.
    e.preventDefault();
    e.stopPropagation();
    if (document.querySelector(".wb-palette-shade") && id !== "palette") return;
    void runCommand(id).catch((error: Error) => errorHere(error));
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
}, { catalog: "1", workbench: "1", window: WINDOW_ID, page: PAGE });
// The Session page's link to the agent's change, and Follow the agent: the cell it changed, scrolled to.
setAgentHooks({
  place: () => ({ path: current?.path ?? null, title: current?.title ?? null, cell: current?.notebook?.selectedNumber() ?? null }),
  busy: userBusy,
  ran: (command, wasBusy) => {
    if (wasBusy || !following() || !/^(cell\.|html\.(add|resize)|snippet\.)/.test(command)) return;
    window.requestAnimationFrame(() => {
      const cell = [...document.querySelectorAll<HTMLElement>(".wb-cell.selected, .wb-tcell.selected")].find((c) => c.offsetParent !== null);
      if (!cell) return;
      cell.scrollIntoView({ block: "nearest" });
      pulse(cell);
    });
  },
});
// The agent's workbench_window goes to the Workbench window the user was last in.
window.addEventListener("focus", tellFocus);
onNotice((notice) => {
  handleAgentNotice(notice);
  // The project's documents changed (opened, closed, an import): "In this project" follows.
  if (notice.type === "project_changed" || notice.type === "project_documents_changed") {
    void refreshHome();
    void codex.refresh(); // the explorer follows the project's files
  }
  if (notice.type === "project_changed") void refreshMode();
  if (notice.type === "workbook_changed") for (const d of docs) d.workbook?.noticed(String((notice as unknown as { id: string }).id));
  // The agent's workbench_window: a command run here, as the palette would, and answered.
  // A document moved back to this (the main) window from one it was popped out into.
  const handed = notice as unknown as { to: string; page?: string | null };
  // A document of the other page's kind is that page's window's (never taken here).
  const handedTo = notice.type === "workbench_handoff" && (!handed.page || handed.page === PAGE) ? handed.to : null;
  if (handedTo !== null && (handedTo === WINDOW_ID || (handedTo === "main" && isMainWindow()))) void takeDocument((notice as unknown as { id: string }).id).catch((e: Error) => {
      if (!(e instanceof ApiError && e.status === 409)) errorToast(e); // another main window took it
    });
  if (notice.type === "file_changed" && typeof (notice as unknown as { path?: unknown }).path === "string") {
    const said = notice as unknown as { path: string; hash: string | null };
    fileChanged(said.path, said.hash ?? null);
  }
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
  if (["grid_updated", "dataset_updated", "streamlit_changed"].includes(notice.type)) lineageNoticed();
  // The agent changed a cell's code through the canvas's pane (canvas_set_default...): the window that
  // holds the app makes it in the open document, like typing.
  if (notice.type === "streamlit_code") {
    const sent = notice as unknown as { window: string; plan: CodePlan };
    const app = sent.window === WINDOW_ID ? docs.find((d) => d.canvas?.app() === sent.plan.app) : undefined;
    if (app) void applyCode(app, sent.plan).catch((e: Error) => errorHere(e));
  }
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

watchConnectionColours(); // everything tied to a connection wears its colour (connectionColours.ts)
// The open project's mode changed (a project opened or closed): New's language and the cell kinds follow.
onNotice((notice) => {
  if (notice.type === "mode_changed") void refreshMode();
});
// Another window of this app asks for a code app's file here (the Code App page's Open in the Workbench).
window.addEventListener("message", (e: MessageEvent) => {
  const said = e.data as { sab?: unknown; path?: unknown } | null;
  if (e.origin === location.origin && said?.sab === "codefile" && typeof said.path === "string") void openCodeFileDoc(said.path);
  // A document by its path (the Code App page's data notebook).
  if (e.origin === location.origin && said?.sab === "open" && typeof said.path === "string") void open(said.path).catch((err: Error) => errorToast(err));
});
void Promise.all([
  loadPanels(),
  loadKindColours(),
  refreshHome(),
  loadConnections(),
  whenMode(),
  api<{ pythons: PythonChoice[] }>("/workbench/pythons").then((r) => (pythons = r.pythons), () => undefined),
]).then(() => {
  drawEmpty();
  refreshPane();
  // A document popped out into this window starts it fresh (a new window copies its opener's session).
  const fresh = openedWith.get("fresh") === "1";
  if (fresh) sessionStorage.removeItem(SESSION_KEY);
  void (fresh ? Promise.resolve(false) : restore()).then(() => {
    const codefile = openedWith.get("codefile"); // a code app's file (the Code App page)
    if (codefile) void openCodeFileDoc(codefile);
    const wanted = openedWith.get("open"); // the address as opened (the page clears it once the token is read)
    // At a reference's cell too (the Connections page, with no Workbench window yet).
    const cell = Number(openedWith.get("cell"));
    if (wanted && cell > 0) void openCell(wanted, cell).catch((e: Error) => errorHere(e));
    else if (wanted) void open(wanted);
    // A document popped out of another window: this window was opened to take it.
    const handed = openedWith.get("take");
    if (handed) void takeDocument(handed).catch((e: Error) => errorHere(e));
    // Opened for a kind (the rail's Notebooks, Scripts, Apps): its landing page, or with none of it open
    // that page too. (A reload's documents came back as they were, the one in front too.)
    const here = new URLSearchParams(location.search);
    const k = handed || wanted ? null : codeKindOf(here.get("kind"));
    if (k && here.get("view") === "list") showLanding(k);
    else if (k && !docs.some((d) => docKindOf(d) === k)) showKind(k);
    // The open project: its documents here (once), its name and unsaved mark in the top row.
    onProject((state) => void followProject(state).catch((e: Error) => errorHere(e)));
    onBeforeSave(reportSab);
    mountProject();
  });
});
