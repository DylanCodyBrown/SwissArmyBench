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
 *   [EMPTY]    nothing open: Start a notebook (Notebooks) or the script creator (Scripts)
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
 *   [APPS]     no app here: a Streamlit app is built from widgets on the Canvas (canvasPage.ts, its own
 *              page); New canvas opens it. App notebooks and live Streamlit cells went (2026-11-21)
 *   [PROJECT]  a project is a folder that starts with data.ipynb (its export: data.py): New project,
 *              Open project (its files as tabs, and listed at the Data Explorer's foot), Export data.py
 *   [POP OUT]  a saved document moves into a Workbench window of its own (the group's "…")
 *
 * ROUTING: /workbench/home, /open, /save, /pythons (routes_workbench.py); kernels in workbenchKernel.ts.
 */
import "./shareApp"; // Share… a running app (globalThis.sabShare: the canvas wires it into Play's menu)
import { bringPage, type CodePage, isCanvasFile, loadPageRules, openCanvasFile, openOnPage, PAGE_WINDOW, PAGE_WORDS, pageOfKind, pageOfPath, thisPage, wrongPage } from "./workbenchPages";
import { ideMoves } from "./workbenchIde";
import { debugSession, type DebugSession, type DebugState } from "./workbenchDebug";
import type { CodeEditor } from "./lazy/codeEditor";
import { handleAgentNotice, loadApprovals } from "./agentAccess";
import { agentApi, api, ApiError, connect, onNotice, openedWith, requireSession, tellFocus, token } from "./api";
import { type BladeKind, type BladeSummary, editBlade, newBladeDialog } from "./bladeEditor";
import { mountRail, schemaDetails, tableDetails, watchTheme } from "./catalogRail";
import { openConnections, setCellOpener } from "./connectionsWindow";
import { askYesNo, button, clear, h, icon, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { openFile } from "./openFile";
import { effectiveTheme } from "./theme";
import { answerAgent, mountShortcutKeys, registerCommands, setAgentHooks } from "./workbenchCommands";
import { following, pulse, userBusy } from "./sessionPage";
import { consoleView, type ConsoleView } from "./workbenchConsole";
import { forgetCatalogs, listDatasets, pythonCompleter, setDialects } from "./workbenchCompletion";
import { pythonIntel } from "./workbenchIntel";
import type { Fix } from "./workbenchErrors";
import { mountExplorerPane } from "./workbenchExplorer";
import { type ExplorerResult, type ExplorerState, openDataWindow } from "./dataExplorer";
import { mountGroups, onTabKinds, registerTabKind, type SavedLayout, type Side, type TabKind, tabKinds } from "./workbenchGroups";
import { type CodeFileView } from "./workbenchCodeFile";
import { type StructureDoc } from "./structureDoc";
import { isStructurePath, structureSuffixes } from "./structurePaths";
import { workbenchCommands } from "./workbenchCommandList";
import { sessionMemory } from "./workbenchRestore";
import { fileChangedWatcher } from "./workbenchFileChanged";
import { BASE_FONT, codeZoom, fullScreen as makeFullScreen } from "./workbenchView";
import { windowKeys } from "./workbenchKeys";
import { workbenchBars } from "./workbenchBars";
import { statusBar } from "./workbenchStatusBar";
import { fileTabs } from "./workbenchFileTabs";
import { workbenchSides } from "./workbenchSides";
import { tableOwners } from "./workbenchTableOwners";
import { documentPanels } from "./workbenchDocPanels";
import { docName, documentLineage } from "./workbenchDocLineage";
import { documentMoves } from "./workbenchMove";
import { documentExports } from "./workbenchExport";
import type { Part } from "./structureTree";
import { mountLayout } from "./workbenchLayout";
import { type MenuEntry, openMenu } from "./workbenchMenu";
import { go, HOME_WINDOW, mountNav, setTitle, startNav, withParams } from "./nav";
import { mountNavRail } from "./rail";
import { type LandingDoc, mountLanding } from "./workbenchLanding";
import { watchConnectionColours } from "./connectionColours";
import { type Kind, kindIcon, kindOfPath, onProjectFolder, setProjectFolder } from "./kindColours";
import { areaOfKind, gatedRun } from "./gates";
import { type Missing, promptInstall } from "./missingPackages";
import { betaCommands, mountBeta } from "./betaNotes";
import { installZoomInput } from "./zoom";
import { updateCommands } from "./updates";
import { claudeCommands } from "./claudeLaunch";
import { setDocumentName } from "./workbenchAgent";
import { fetchTables } from "./workbenchTables";
import { openEnvironment, environmentPane } from "./environmentPage";
import { Kernel, sessionHeard, WINDOW_ID } from "./workbenchKernel";
import { heardProjectPython, inProject, loadProjectPython, offerMoved, projectPython, type Offer } from "./projectSession";
import { type CellData, notebookView, type NotebookView } from "./workbenchNotebook";
import { scriptView, type ScriptView } from "./workbenchScript";
import { lineageNoticed } from "./workbenchLineage";
import { type Descriptions } from "./workbenchDocModes";
import { excelView, type ExcelView, WORKBOOK_ENDING } from "./excelCanvas";
import { activeMode, modes, offersCanvas, onMode, refreshMode, whenMode } from "./modes";
import { closeProject, copyProject, exportOutline, loadProject, mountProject, newProject as newProjectFolder, onBeforeSave, onProject, openProject as openProjectFolder, projectState, type ProjectState, reportLayout, saveProject } from "./projectFile";
import { importFile, openImport } from "./projectImport";
import { type ModeFrame } from "./workbenchModes";
import { installVariableAnywhere } from "./variableAnywhere";
import { errorHere, errorToast } from "./errorNote";

// A variable in any box: typing ${ lists them, right-click inserts one (12.7).
installVariableAnywhere();

watchTheme();

export interface Doc {
  id: number;
  kind: "notebook" | "script" | "blade" | "table" | "workbook" | "codefile" | "library" | "structure";
  title: string;
  path: string | null;
  modified: number | null;
  dirty: boolean;
  /** A library's read-only tab: its editor to a line. */
  libraryAt?: (line: number) => void;
  /** A script's debugger on the Scripts page (workbenchDebug.ts). */
  debug?: DebugSession;
  kernel: Kernel | null;
  python: string | null;
  element: HTMLElement;
  notebook?: NotebookView;
  script?: ScriptView;
  /** Its console, on its kernel (notebooks and scripts). */
  console?: ConsoleView;
  /** A workbook's design on the Excel canvas (the Accounting extension's; excelCanvas.ts). */
  workbook?: ExcelView;
  /** Its mode's own panels (workbenchModes.ts): beside it in its group. */
  modes?: ModeFrame;
  /** A code app's file (workbenchCodeFile.ts, the Power Apps extension's plug-in): TypeScript or TSX. */
  codefile?: CodeFileView;
  /** A JSON, YAML, XML or TOML file beside the code (structureDoc.ts): its tree and its text, an IDE. */
  structure?: StructureDoc;
  /** Its file's text's hash as this window last read or wrote it (the file_changed notice is compared). */
  hash?: string | null;
  /** Its file changed elsewhere while it had unsaved edits (or is gone): Save waits for the choice. */
  elsewhere?: { hash: string | null; bar: HTMLElement };
}

export interface PythonChoice {
  python: string;
  version: string;
  ipykernel: boolean;
  swissarmybench: boolean;
}

const top = document.getElementById("wb-top") as HTMLElement;
// Notebooks and Scripts are two pages (the owner, 2026-11-21: "notebooks and scripts should not reuse the
// same page they are seperate things"): this window is one of them (its path says which, workbenchPages.ts).
await loadPageRules(); // which page a file or a kind opens on: the server's tables, before the first question
const PAGE: CodePage = thisPage();
document.body.dataset.page = PAGE;
document.title = PAGE_WORDS[PAGE]; // "Notebooks" or "Scripts" until a document says more
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
// The Environment (the owner, 2026-11-21/22): the same list as its page, in the right pane (it replaced the
// Variables pane); it follows the app's notices by itself.
const variables = environmentPane(
  () => {
    layout.toggle("right", false);
    drawStatus();
  },
  (code) => {
    try {
      explorerInsert(code);
      return true;
    } catch {
      return false; // no notebook or script in front: the code is copied instead
    }
  },
);
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
// The first load of the names: a default ("the first dataset") waits for it, never reads an empty list.
let namesLoaded: Promise<void> = Promise.resolve();
async function firstDataset(): Promise<string> {
  await namesLoaded;
  return datasetNames[0] ?? "";
}
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

// Which document holds each open table's cell, and the group row's Run tables (workbenchTableOwners.ts).
const tableCells = tableOwners({
  docs,
  isApiFile: (doc) => isApiFile(doc),
  isData: (doc) => isData(doc),
  get current() {
    return current;
  },
});
const { tableOwner, tablesSent, tablesHost, viewOf, assignTables, assignSoon, refreshTablesSoon, giveTable, drawTablesTool } = tableCells;

// ===== projects, and the canvases' New entries =====
// No app documents here (2026-11-21): an app is built from widgets on the Canvas (its own page). A file from
// before that is refused by the server's own open, in its one line.

const DATA_NOTEBOOK = "data.ipynb";
const isData = (doc: Doc): boolean => !!doc.notebook && !!doc.path && baseName(doc.path).toLowerCase() === DATA_NOTEBOOK;

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
  registerTabKind({ id: "page", label: "App page", icon: "page", mark: "app", ...(offersCanvas("streamlit") ? { start: { label: "New canvas", run: () => window.open("/streamlit/canvas", "_blank") } } : {}) });
  registerTabKind({ id: "workbook", label: "Workbook", icon: "excel", mark: "app", ...(offersCanvas("excel") ? { start: { label: "New Excel workbook", run: () => void openWorkbook(null) } } : {}) });
}

// ----- projects: a folder that starts with data.ipynb (docs/ideas.md, 2026-11-15) -----

export interface ProjectFiles {
  folder: string;
  name: string;
  data: string | null;
  files: string[];
}
let project: ProjectFiles | null = null;

// A project opened or closed: the notebooks' kinds (data, app, plain) follow: their tabs, the Data
// Explorer's files and the landing.
onProjectFolder(() => {
  drawTabs();
  if (project) listProject();
  landing.redraw();
  drawTop();
});

/** The project's files in the Data Explorer: data.ipynb, data.py set in as its output, the notebooks and
 *  scripts. */
function listProject(): void {
  setProjectFolder(project?.folder ?? null);
  if (!project) return void explorerPane.setFiles(null);
  const files = project.files.flatMap((path) => {
    const name = baseName(path);
    const file = { path: name, icon: kindIcon(kindOfPath(name), path), open: () => void open(path) };
    // data.py is data.ipynb's export: listed under it, greyed, never opened from here.
    return name.toLowerCase() === DATA_NOTEBOOK ? [file, { path: "data.py", icon: "code", derived: true }] : [file];
  });
  // The mode's own files a person edits (a code app's .ts and .tsx under src/), opened in the code editor.
  for (const path of modeFiles) files.push({ path, icon: "code", open: () => void openCodeFileDoc(path) });
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

// Export data.py, Export as one Python script… and as one notebook… (workbenchExport.ts).
const { exportData, exportDocument } = documentExports({
  docs,
  isData: (doc) => isData(doc),
  folderOf: (path) => folderOf(path),
  get project() {
    return project;
  },
  get homeFolder() {
    return homeFolder;
  },
});

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
  const mine = docs.filter((d) => (d.notebook || d.script) && inFolder(d.path, open.folder));
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
  const wanted = (saved?.documents?.length ? saved.documents.map((relative) => joinPath(opened.folder, relative)) : (listed?.files ?? [])).filter((p) => !isCanvasFile(p) && (pageOfPath(p) ?? PAGE) === PAGE);
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

// ----- Notebook mode: the run order (edited, out of date), the Outline, Run up to here, Present

// Each mode's own panels and views (workbenchDocPanels.ts): Notebook's Outline and Present, Script's Run settings,
// data.ipynb's Cells | Lineage | Dictionary, the status bar's toggles for them.
let vaultNames: string[] = [];
const { flows, flowSoon, refreshFlow, notebookModes, present, scriptModes, scriptArguments, readArguments, dataViews, dataBody, dataMode, setDataView, dictionaryTables, drawDictionaryView, describe, modeToggles, drawModeToggles, modeSwitch } =
  documentPanels({
    docs, drawStatus, drawControls, isData,
    isApiFile: (doc) => isApiFile(doc),
    markChanged: (doc) => markChanged(doc),
    dataLineage: (doc, into) => dataLineage(doc, into),
    explorer: { isOpen: () => explorerPane.isOpen(), toggle: (on) => void explorerPane.toggle(on) },
    get current() {
      return current;
    },
    get tables() {
      return tableCells.tables;
    },
    get vaultNames() {
      return vaultNames;
    },
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
const moves = (doc: Doc): boolean => !!(doc.notebook || doc.script);

// The move itself (workbenchMove.ts): handed over, taken, never two live copies.
const { popOut, moveToMain, takeDocument } = documentMoves({
  page: PAGE, moves, isMainWindow, close, explorerBack, openNotebook, openScript, show, drawTabs, drawStatus, remember,
  dataBody: (doc) => dataBody(doc),
  get pythons() {
    return pythons;
  },
});

const restoreSteps = (grid: string, steps: unknown[]): void => void api(`/grids/${encodeURIComponent(grid)}/steps`, "POST", { steps }).catch((e: Error) => errorHere(e));

/** One Python per project (projectSession.ts): a document of the open project holds the project's one
 *  session (taken at once while it runs: its variables and completions are live before its first Run). */
function joinSession(doc: Doc): void {
  const project = projectPython();
  if (!doc.kernel || !project?.session || !inProject(doc.path)) return;
  doc.kernel.join({ shared: true, words: project.session, kernel: project.kernel }, project.python);
}

/** Whether a document runs in the project's one session (said before its first Run, too). */
const inSession = (doc: Doc | null | undefined): boolean => Boolean(doc?.kernel && (doc.kernel.shared || (projectPython()?.session && inProject(doc.path))));

function makeDoc(kind: Doc["kind"], title: string, path: string | null, modified: number | null): Doc {
  const refused = wrongPage(kind, PAGE); // a notebook never opens on the Scripts page, nor a script here
  if (refused) throw new Error(refused);
  const doc: Doc = { id: ++counter, kind, title, path, modified, dirty: false, kernel: null, python: null, element: h("div", { class: `wb-doc-body kind-${kind}` }) };
  if (kind === "notebook" || kind === "script") {
    const kernel = new Kernel(() => doc.path, () => doc.python, true);
    doc.kernel = kernel;
    joinSession(doc); // a project's document runs in the project's one Python session
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

/** API.py, the project's local sandbox API (domain/local_api.py FILE): its Run is the API's, not a script's. */
const isApiFile = (doc: Doc | null): boolean => !!doc?.script && /(^|[\\/])API\.py$/.test(doc.path ?? "");

/** Run API (API.py's main Run, F5): saved first, then hosted as the APIs page's Run hosts it (POST
 *  /local-api/run: 127.0.0.1, only the sandbox). A start that failed is said here with its line; another
 *  project's API.py (not the open project's) runs as a plain file. */
async function runApi(doc: Doc, from?: HTMLElement): Promise<void> {
  try {
    if (doc.path && doc.dirty && !(await save(doc))) return;
    const now = await api<{ file?: string }>("/local-api");
    const same = (a: string, b: string): boolean => a.replace(/\\/g, "/") === b.replace(/\\/g, "/");
    if (!now.file || !doc.path || !same(now.file, doc.path)) return void (await doc.script!.runFile());
    const done = await api<{ running: { url: string; endpoints: number } | null; failed?: { error: string; line: number | null } | null }>("/local-api/run", "POST", {});
    if (done.failed) {
      const line = done.failed.line;
      if (line) doc.script!.reveal(line);
      errorHere(done.failed.error, { where: line ? `API.py line ${line}` : "API.py" }, from ?? null);
    } else if (done.running) {
      toast(`Running on ${done.running.url} · ${done.running.endpoints} ${done.running.endpoints === 1 ? "endpoint" : "endpoints"}`);
    }
  } catch (e) {
    errorHere(e, {}, from ?? null);
  }
}

/** F5 and the group row's main Run: the file, or every cell. */
async function runPrimary(doc: Doc | null): Promise<void> {
  if (isApiFile(doc)) await runApi(doc!);
  else if (doc?.script) await doc.script.runFile();
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
  doc.notebook = notebookOf(doc, cells, nextCell);
  doc.element.append(doc.notebook.element);
  notebookModes(doc);
  if (isData(doc)) dataMode(doc, dictionary ?? {});
  show(doc);
  // A new notebook is for typing: the cursor waits in its first cell.
  if (!path && !cells.length) doc.notebook.select(0, true);
  return doc;
}

/** Each script's editor once it has loaded (the debugger's gutter and paused line). */
const scriptEditors = new WeakMap<Doc, CodeEditor>();

/** A notebook document's view of its cells (its kernel the document's: a reload in place keeps its names). */
function notebookOf(doc: Doc, cells: CellData[], nextCell?: number): NotebookView {
  return notebookView(cells, doc.kernel!, () => connectionNames, () => effectiveTheme(), markChanged(doc), () => bladeNames, () => codeNames, {
    ...hooks,
    fix: pageFix(doc),
    openGrid: (name) => void openGrid(doc, name),
    openResult: (n, name) => void openResult(doc, n, name),
    nextCell,
    opened: cells.length > 0, // from a file or a reload: its tables' cells have not run since
    restoreSteps,
    tablesChanged: () => doc === current && drawTablesTool(),
    datasets: () => datasetNames,
    lineage: (number) => void showLineage({ document: docName(doc), cell: number }),
    ran: () => flowSoon(doc),
  });
}

function openScript(path: string | null, text: string, modified: number | null): Doc {
  const doc = makeDoc("script", path ? baseName(path) : `Untitled script ${counter + 1}`, path, modified);
  // The Scripts page's debugger: breakpoints in the gutter, Start debugging, the panel under the code.
  const debug =
    PAGE === "scripts"
      ? debugSession({
          kernel: () => doc.kernel!.ensure(),
          path: () => doc.path,
          text: () => doc.script!.text(),
          editor: () => scriptEditors.get(doc) ?? null,
          openAt: (p, line) => void openAt(p, line).catch(() => openLibraryDoc(p, line, null).catch((e: Error) => errorHere(e))),
          layout: () => window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize"))),
        })
      : undefined;
  doc.debug = debug;
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
    // No live Streamlit cells (2026-11-21): no streamlit host.
    lineage: (number) => void showLineage({ document: docName(doc), cell: number }),
    // Script mode: Run file takes the run settings' arguments.
    arguments: () => scriptArguments.get(doc) ?? "",
    breakpoints: debug?.gutter,
    editorReady: (editor) => {
      scriptEditors.set(doc, editor);
      debug?.attach(editor);
    },
    // The Scripts IDE's moves (workbenchIde.ts): F12, Shift+F12, F2, Shift+Alt+F.
    ide: ideMoves(
      { path: () => doc.path, text: () => doc.script!.text(), python: () => doc.python, replaceText: (t) => doc.script!.replaceText(t), reveal: (line) => doc.script!.reveal(line) },
      { openAt: (p, line) => void openAt(p, line), openLibrary: (p, line, module) => void openLibraryDoc(p, line, module).catch((e: Error) => errorHere(e)) },
    ),
  });
  doc.element.append(doc.script.element);
  if (debug) doc.script.element.append(debug.element);
  scriptModes(doc);
  if (path) void readArguments(doc);
  show(doc);
  return doc;
}

// ===== lineage: a cell or a block back to the data, with its values (workbenchLineage.ts) =====

// A cell's or a block's lineage, in the overlay or in data.ipynb's Lineage view (workbenchDocLineage.ts).
const { showLineage, dataLineage } = documentLineage({
  docs, open, show, viewOf,
  get current() {
    return current;
  },
  backToCells: (doc) => {
    if (dataViews.get(doc)?.view === "lineage") setDataView(doc, "cells");
  },
});

/** A run in a document's console: the console opens to show it. */
function useConsole(doc: Doc): void {
  if (doc !== current || layout.state().console) return;
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

/** The focused group's document changed: everything that follows the focused document follows. */
function focused(doc: Doc | null): void {
  current = doc;
  // A workbook's design runs no code of its own: its console's place says nothing.
  if (doc?.kind === "workbook") layout.console.replaceChildren();
  else layout.console.replaceChildren(doc?.console?.element ?? h("p", { class: "hint wb-pane-empty" }, "No console"));
  cursor = { line: 1, column: 1 };
  drawEmpty();
  drawControls();
  drawStatus();
  setTitle(PAGE_WORDS[PAGE], doc?.title ?? ""); // "Workbench · sales.ipynb": the page, then the place
  followKind(doc);
  remember();
  assignSoon(); // a table with no document yet goes to the one in front
}

function close(doc: Doc, moved = false): void {
  // (A document that moved to another window took its changes with it.)
  if (!moved && doc.dirty) {
    // Asked on the app's own dialog (dom.ts askYesNo): its yes closes the document, if it is still open.
    void askYesNo(`${doc.title} has changes that are not saved. Close it anyway?`, { ok: "Close it" }).then((yes) => {
      if (yes && docs.includes(doc)) close(doc, true);
    });
    return;
  }
  doc.kernel?.stop(); // its own kernel; the project's one session goes on for its other documents
  doc.kernel?.forget();
  doc.workbook?.close();
  // Its Monaco editors and design frames go too (they were kept alive, detached, before).
  doc.notebook?.dispose();
  doc.script?.dispose();
  doc.console?.dispose();
  doc.codefile?.dispose();
  if (doc.structure) {
    doc.structure.dispose();
    void api(`/structures/${encodeURIComponent(doc.structure.id)}`, "DELETE").catch(() => undefined); // closed there too
  }
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

/** A document's kind colour (kindColours.ts): notebooks blue, scripts green (app pages, violet, are the
 *  Canvas page's). */
function docMark(doc: Doc): "notebook" | "script" | undefined {
  return doc.kind === "notebook" ? "notebook" : doc.kind === "script" ? "script" : undefined;
}

/** A document's kind of tab: Notebook (every one, data.ipynb too: the owner, 2026-11-22, "we just have
 *  notebooks"), Script, Blade, Table, Workbook. */
function kindOf(doc: Doc): string {
  if (doc.kind === "workbook") return "workbook";
  return doc.kind === "table" ? "explorer" : doc.kind;
}

// Kind colours (kindColours.ts): notebooks blue, scripts green; a blade or a catalog table wears none.
registerTabKind({ id: "notebook", label: "Notebook", icon: "notebook", mark: "notebook", start: { label: "New notebook", run: () => void openNotebook(null, [], null) } });
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
registerTabKind({ id: "library", label: "Library source", icon: "key", mark: "plain" });
registerTabKind({ id: "structure", label: "Structure", icon: "json", mark: "plain" });

// ===== a structure's file, a library's source, a code app's file: tabs beside the code (workbenchFileTabs.ts) =====

const { openStructureTab, structureOf, openLibraryDoc, openCodeFileDoc, scriptLanguage, newModeFile, LANGUAGE_WORDS } = fileTabs({
  docs, makeDoc, show, close, drawTabs, remember,
  filesChanged: () => codexHooks.refresh(),
  editors: () => editors(),
  get current() {
    return current;
  },
});

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
  // Apps is the Canvas, a page of its own (2026-11-21): the old address goes there.
  if (k === "app") return void location.replace("/streamlit/canvas");
  // The other page's kind: that page's window, brought forward (never its tabs here).
  const page = pageOfKind(k);
  if (page && page !== PAGE) {
    bringPage(page, `/${page}?kind=${k}&view=list`);
    return;
  }
  // The creator shows only while none of the kind is open (the owner, 2026-11-21): else its tab comes forward.
  const mine = [...docs].reverse().find((d) => docKindOf(d) === k);
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

/** A kind's New (a new notebook is a plain notebook: app notebooks went, 2026-11-21). */
function startLabel(kind: TabKind): string {
  return kind.start?.label ?? "";
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
  let chosen = path ?? (await chooseFile({ title: "Open", mode: "file", suffixes: [...(PAGE === "scripts" ? [".py"] : [".ipynb", ...(offersCanvas("excel") ? [WORKBOOK_ENDING] : [])]), ...structureSuffixes()], start: sab.folder ?? current?.path ?? homeFolder }));
  if (!chosen) return;
  // A JSON, YAML, XML or TOML file: a structure's tab here, beside the code (where it is: never copied in).
  if (isStructurePath(chosen)) return void (await openStructureTab({ path: chosen }));
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
  // An app's canvas is the Canvas page's (asked for here from the project's files): it opens there.
  if (isCanvasFile(chosen)) return openCanvasFile(chosen);
  const already = docs.find((d) => d.path === chosen);
  if (already) return show(already);
  if (chosen.toLowerCase().endsWith(WORKBOOK_ENDING)) return void openWorkbook(chosen);
  try {
    const found = await api<{ path: string; kind: "notebook" | "script"; modified: number; cells?: CellData[]; text?: string; python: string | null; next_cell?: number; dictionary?: Descriptions; hash?: string | null; moved_environment?: Offer }>("/workbench/open", "POST", { path: chosen });
    if (found.kind === "notebook") openNotebook(found.path, found.cells ?? [], found.modified, found.next_cell, found.dictionary);
    else openScript(found.path, found.text ?? "", found.modified);
    if (current?.path === found.path) current.hash = found.hash ?? null;
    // Its own environment, as remembered (or the .venv beside it): the picker shows it, Run uses it.
    if (found.python && current) {
      current.python = found.python;
      if (!pythons.some((p) => p.python === found.python)) pythons.push({ python: found.python, version: "", ipykernel: true, swissarmybench: true });
      drawStatus();
    }
    // It had an environment of its own and now runs in the project's one Python: said once, in one line.
    offerMoved(found.moved_environment);
    void refreshHome();
  } catch (e) {
    errorHere(e);
  }
}

// ===== a file changed anywhere (workbenchFileChanged.ts: the document follows, or its bar asks) =====
const fileWatch = fileChangedWatcher({
  docs: () => docs,
  current: () => current,
  notebookOf,
  drawTablesTool,
  drawTabs,
  remember,
  save,
  close: (doc) => close(doc),
  refreshFiles: () => codexHooks.refresh(),
});
const clearElsewhere = fileWatch.clear;
const fileChanged = fileWatch.changed;

/** Save a document (true: it is saved). */
async function save(doc: Doc | null, as = false): Promise<boolean> {
  if (doc?.workbook) {
    if (!as) return doc.workbook.save();
    const where = await chooseFile({ title: "Save workbook design as", mode: "save", start: doc.path ?? project?.folder ?? homeFolder, name: `workbook${WORKBOOK_ENDING}` });
    return where ? doc.workbook.save(where.toLowerCase().endsWith(".json") ? where : where + WORKBOOK_ENDING) : false;
  }
  if (doc?.structure) return as ? doc.structure.saveAs() : doc.structure.save();
  if (doc?.codefile) {
    await doc.codefile.save();
    doc.dirty = false;
    drawTabs();
    toast(`Saved ${doc.title}.`);
    return true;
  }
  if (!doc || (doc.kind !== "notebook" && doc.kind !== "script")) return false;
  // Changed elsewhere while edited here: never written over until the user chooses (Reload, Keep mine).
  if (doc.elsewhere && !as) {
    errorHere(`${doc.title} changed elsewhere: Reload, Keep mine or Compare first.`);
    return false;
  }
  let path = doc.path;
  if (!path || as) {
    const suggested = doc.path ? baseName(doc.path) : doc.kind === "notebook" ? "analysis.ipynb" : "script.py";
    path = await chooseFile({ title: doc.kind === "notebook" ? "Save notebook" : "Save script", mode: "save", start: doc.path ?? project?.folder ?? homeFolder, name: suggested });
    if (!path) return false;
    const ending = doc.kind === "notebook" ? ".ipynb" : ".py";
    if (!path.toLowerCase().endsWith(ending)) path = path + ending;
  }
  // A notebook keeps the next cell number with it, so a deleted cell's number is never given again.
  const body = doc.kind === "notebook" ? { cells: doc.notebook!.cells(), next_cell: doc.notebook!.nextCell(), ...dataBody(doc) } : { text: doc.script!.text() };
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
    drawTabs(); // the tab's dot goes: that is the word for "saved"
    remember();
    void refreshHome();
  };
  try {
    await send(false);
    return true;
  } catch (e) {
    if (e instanceof ApiError && e.status === 409 && (await askYesNo(`${e.message}\n\nReplace the file on disk with this one?`))) {
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

function folderOf(path: string | null): string {
  if (!path) return homeFolder;
  const at = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return at > 0 ? path.slice(0, at) : homeFolder;
}

// ----- the top bar and a group's row (workbenchBars.ts)

const bars = workbenchBars({
  top, isMainWindow, open, save, saveFront, firstDataset, sabOpen, importDocuments, recentMenu, canSplit, splitDoc,
  docKindOf, codeKindOf, scriptLanguage, newModeFile, startLabel, newEntries, projectEntries, inSession, moves,
  docMark, popOut, moveToMain, close, isApiFile, runApi, modeSwitch, tablesHost, drawTablesTool,
  saves: () => saves(),
  kernelOf: () => kernelOf(),
  hideLanding: () => hideLanding(),
  controls: () => groups.controls(),
  landingKind: () => landing.kind(),
  languageWords: LANGUAGE_WORDS,
  splitWhy: SPLIT_WHY,
  newLabel: (label) => codexHooks.label(label),
  explorerOpen: () => explorerPane.isOpen(),
  exportDocument: (doc, format) => exportDocument(doc, format),
  fullScreen: () => fullScreen(),
  dataView: (doc) => dataViews.get(doc)?.view ?? "cells",
  get current() {
    return current;
  },
});
const { topMenu, restartKernel, stopSession, openProjectLibraries } = bars;
function drawTop(): void {
  bars.drawTop();
}
function topStart(): void {
  bars.topStart();
}
function drawControls(): void {
  bars.drawControls();
}
/** A tab's moves between windows (its "…" menu and its right-click menu). */
function moveEntries(doc: Doc): MenuEntry[] {
  return bars.moveEntries(doc);
}

// ----- the status bar: for the focused document (workbenchStatusBar.ts)

installZoomInput();
const status = statusBar({
  layout, variables, modeToggles, drawModeToggles, inSession, folderOf,
  sessionEntries: (kernel, shared) => bars.sessionEntries(kernel, shared),
  openProjectLibraries,
  kernelInstall: (doc) => kernelInstall(doc),
  explorer: { isOpen: () => explorerPane.isOpen(), popped: () => explorerPane.popped() },
  get current() {
    return current;
  },
  get cursor() {
    return cursor;
  },
  get pythons() {
    return pythons;
  },
});
const { sideToggles } = status;
function drawStatus(): void {
  status.drawStatus();
}
function drawCursor(): void {
  status.drawCursor();
}

// ===== the Data Explorer: one search over what holds data; the catalog and the blades beside it =====

function bladeDoc(name: string | null, fresh?: { line: number }): void {
  if (name === null) {
    // New blade (the owner, 2026-11-21): a name and a kind; the blank blade opens straight away, Properties open.
    void newBladeDialog().then((made) => {
      if (!made) return;
      rail.bladeSaved(made.name);
      bladeDoc(made.name, { line: made.line });
    });
    return;
  }
  const already = docs.find((d) => d.kind === "blade" && d.title === name);
  if (already) return void show(already); // one tab a blade
  const doc = makeDoc("blade", name, null, null);
  editingBlade = true;
  const done = (): void => { editingBlade = false; close(doc); };
  const saved = (savedName: string): void => { editingBlade = false; rail.bladeSaved(savedName); void loadConnections(); };
  void editBlade(doc.element, name, null, "other" as BladeKind, saved, done, undefined, fresh);
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
  // A Structures result: its tab here, beside the code, at its node (a structure with no file of its own by id).
  openStructure: (r: ExplorerResult) => {
    const at = Array.isArray(r.parts) ? (r.parts as Part[]) : null;
    const path = typeof r.file === "string" && isStructurePath(r.file) ? r.file : undefined;
    const id = typeof r.structure === "string" ? r.structure : undefined;
    void openStructureTab(path ? { path } : { id }, at).catch((e: unknown) => errorHere(e));
  },
  openVariable: (name?: string) => openEnvironment("setting", name),
  addTable: (anchor) => void openMenu(anchor, "Add a table", tableEntries()),
  toggled: () => {
    remember();
    drawStatus();
    window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize"))); // the editors measure again
  },
  popOut: () => void popExplorer().catch((e: Error) => errorHere(e)),
});
(document.querySelector(".wb-layout") as HTMLElement).prepend(explorerPane.element);

// ===== the Files and Blades panes on the right (workbenchSides.ts) =====

const { codex, sides, bladesPane, bladeAsked } = workbenchSides({
  page: PAGE, docs, open, openAt, scriptLanguage, newModeFile, bladeDoc, sideToggles,
  menu: topMenu, // the page's "…" (no top bar: the owner, 2026-11-21)
  landingKind: () => landing.kind(),
  hideLanding: () => hideLanding(),
  get current() {
    return current;
  },
});
codexHooks.mark = codex.mark;

// ===== the code's own zoom, and full screen (workbenchView.ts) =====
const editors = (): Promise<typeof import("./lazy/codeEditor")> => import(/* external */ "/static/build/lazy/codeEditor.js" as string) as Promise<typeof import("./lazy/codeEditor")>;
const setCodeFont = codeZoom(PAGE, layout.source, (px) => void editors().then((m) => m.setPageFontSize(px)));
const fullScreen = makeFullScreen(PAGE, () => drawControls()).toggle;
codexHooks.label = codex.setNewLabel;
codexHooks.typed = codex.typed;
codexHooks.refresh = () => void codex.refresh();

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
  const info = (tableCells.tables.length ? tableCells.tables : await tableCells.read()).find((t) => t.name === name);
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

// ===== restore after a reload (workbenchRestore.ts) =====
const session = sessionMemory({
  page: PAGE,
  docs: () => docs,
  current: () => current,
  groups,
  project: () => project,
  setProject: (found) => void (project = found),
  listProject,
  pythons: () => pythons,
  open: (path) => open(path),
  openNotebook,
  openScript,
  show: (doc) => show(doc),
  drawTabs,
  dataBody,
  reportSab,
});
const SESSION_KEY = session.key;
const rememberNow = session.rememberNow;
const restore = session.restore;
function remember(): void {
  session.remember();
}

// ===== the rail's Notebooks, Scripts and Apps (rail.ts) =====

const KIND_WORDS: Record<Kind, { name: string }> = {
  notebook: { name: "Notebooks" },
  script: { name: "Scripts" },
  app: { name: "Apps" },
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

  const mine = docKindOf(current) === k ? current : [...docs].reverse().find((d) => docKindOf(d) === k);
  if (mine) {
    show(mine);
    return;
  }
  void go(withParams({ kind: k, view: "list" }), "replace");
  showLanding(k);
}

/** A reference's click on the Connections page (connectionsWindow.ts): its document here, at its cell. */
async function openCell(path: string, cell: number | null): Promise<void> {
  if (cell) await goToCell(path, baseName(path), cell);
  else await open(path);
}
setCellOpener(openCell);

// ===== start =====

/** Nothing open: the status bar keeps only the panes' buttons (Files, Blades: they show or hide whatever is
 *  open), the document's own words gone. */
function bareStatus(on: boolean): void {
  layout.status.hidden = false;
  layout.status.classList.toggle("wb-status-bare", on);
}

/** Nothing open: the empty state has the area (Start a notebook; Start an app once app pages exist). */
function drawEmpty(): void {
  const none = docs.length === 0;
  // Nothing open: the page's creator (the landing's New and Try it with sample data), as the rail lands.
  if (none && PAGE === "scripts") {
    groups.element.hidden = true;
    empty.hidden = true;
    layout.empty(true);
    bareStatus(true);
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
  bareStatus(none);
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
// The list itself is workbenchCommandList.ts: it is given this page's own names (the host below; its type is
// read from it), and reads what changes (the document in front, the open project) through it each time.

const isCode = (): boolean => !!current?.notebook || !!current?.script;
const saves = (): boolean => isCode() || !!current?.workbook || !!current?.codefile;
const kernelOf = (): Kernel => {
  if (!current?.kernel) throw new Error("The document in front runs no code.");
  return current.kernel;
};
const commandHost = {
  addApi, BASE_FONT, bladeDoc, browse, canSplit, close, dataViews, describe,
  dictionaryTables, docs, drawDictionaryView, drawStatus, explorerInsert, explorerPane, explorerTarget, exportData,
  exportDocument, firstDataset, fullScreen, giveTable, goToTable, groups, isCode, isData, isMainWindow,
  kernelOf, layout, moves, moveToMain, newProject, open, openAt, openCell,
  openNotebook, openProject, openScript, openStructureTab, openWorkbook, PAGE, popExplorer, popOut,
  present, rail, refreshFlow, restartKernel, runPrimary, sabOpen, save, saveFront,
  saveProjectDocuments, saves, setCodeFont, setDataView, show, showHelp, showLineage, showTransformations,
  sides, SPLIT_WHY, splitDoc, stopSession, structureOf, variables, viewOf, workbookInFront,
  get bladeVariables() {
    return bladeVariables;
  },
  get current() {
    return current;
  },
  get cursor() {
    return cursor;
  },
  get project() {
    return project;
  },
  get sab() {
    return sab;
  },
  get tables() {
    return tableCells.tables;
  },
};
export type CommandHost = typeof commandHost;
const COMMANDS = workbenchCommands(commandHost);
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
    bladeAsked(url);
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
window.setTimeout(() => bladeAsked(new URL(location.href)), 0);
// Beta mode (the beta log and Leave a note…) in this window too; nothing while it is off.
mountBeta("workbench", { window: POPPED ? "popout" : "main", tabs: () => docs.map((d) => kindOf(d)) });
// What is sent to the agent or Analyze names the document it came from.
setDocumentName(() => current?.title ?? "the Workbench");

windowKeys(PAGE, () => current); // F5, Ctrl+S, the debugger's keys, Ctrl+Z outside an editor (workbenchKeys.ts)
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
  // One Python per project: the project's Python as it is made, and its one session's restart and end.
  if (heardProjectPython(notice as unknown as { type: string })) {
    for (const d of docs) joinSession(d);
    status.forgetPicker();
    drawStatus();
  }
  if (notice.type === "session_restarted" || notice.type === "session_ended") {
    const said = notice as unknown as { type: string; kernel?: string; python?: string; words?: string };
    if (sessionHeard(said) && said.words) toast(said.words);
    void loadProjectPython().then(() => drawStatus()); // the session's kernel as it is now
    drawStatus();
  }
  if (notice.type === "workbook_changed") for (const d of docs) d.workbook?.noticed(String((notice as unknown as { id: string }).id));
  // The agent's workbench_window: a command run here, as the palette would, and answered.
  // A document moved back to this (the main) window from one it was popped out into.
  const handed = notice as unknown as { to: string; page?: string | null };
  // A document of the other page's kind is that page's window's (never taken here).
  const handedTo = notice.type === "workbench_handoff" && (!handed.page || handed.page === PAGE) ? handed.to : null;
  if (handedTo !== null && (handedTo === WINDOW_ID || (handedTo === "main" && isMainWindow()))) void takeDocument((notice as unknown as { id: string }).id).catch((e: Error) => {
      if (!(e instanceof ApiError && e.status === 409)) errorToast(e); // another main window took it
    });
  if (notice.type === "debug_state") for (const d of docs) d.debug?.heard(notice as unknown as DebugState);
  if (notice.type === "code_file_moved") {
    // A module or package renamed (the explorer's Rename, the agent's workbench_file): its tabs follow it.
    const said = notice as unknown as { from: string; to: string | null };
    if (said.to) {
      for (const doc of docs.filter((d) => d.path && (d.path === said.from || d.path.startsWith(said.from + "/")))) {
        doc.path = said.to + doc.path!.slice(said.from.length);
        doc.title = baseName(doc.path);
      }
      drawTabs();
      remember();
    }
    codexHooks.refresh();
  }
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
  }
  if (["grid_updated", "dataset_updated"].includes(notice.type)) lineageNoticed();
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
namesLoaded = loadConnections();
void Promise.all([
  refreshHome(),
  namesLoaded,
  whenMode(),
  api<{ pythons: PythonChoice[] }>("/workbench/pythons").then((r) => (pythons = r.pythons), () => undefined),
  loadProjectPython(), // before any document opens: a project's document joins the project's one session
]).then(() => {
  drawEmpty();
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
