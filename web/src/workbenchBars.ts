/**
 * workbenchBars.ts: the Workbench's top bar and a group's row (the focused document's controls), and the
 * Python session's entries both they and the status bar offer. Moved out of workbenchPage.ts along its own
 * headings (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [TOP]      the open project's menu, the focused document's name (a dot while unsaved), Save, Save as…,
 *              New (the kind on show), Open… and "…" (hidden on both pages since 2026-11-21: its "…" is the
 *              Files pane's menu)
 *   [ROW]      the focused group's row, right side: Run tables (only while one waits), "+ Cell", the main
 *              Run (Run all, Run file, Run API), Start debugging, Save, "…", Full screen
 *   [SESSION]  Interrupt and Restart: a loose file's kernel, or (asked first) the project's one session
 */
import { askYesNo, button, clear, h, icon, toast } from "./dom";
import { openEnvironment } from "./environmentPage";
import { errorHere } from "./errorNote";
import { betaOn, exportBetaLog, setBeta } from "./betaNotes";
import { type Kind } from "./kindColours";
import { busyClick } from "./loading";
import { activeMode, cellRoute } from "./modes";
import { go, withParams } from "./nav";
import { projectLabel, projectState } from "./projectFile";
import { projectPython } from "./projectSession";
import { openSettings } from "./settingsWindow";
import { openPalette, runCommand } from "./workbenchCommands";
import { type Side, type TabKind, tabKinds } from "./workbenchGroups";
import type { Kernel } from "./workbenchKernel";
import { menuButton, type MenuEntry } from "./workbenchMenu";
import type { CellKind } from "./workbenchNotebook";
import type { Doc } from "./workbenchPage";

/** What the bars ask of the page: the top bar's host, the focused group's row, the landing page, the
 *  document in front, and the page's own actions (open, save, split, move, run, export). */
export interface BarsHost {
  top: HTMLElement;
  controls: () => HTMLElement;
  landingKind: () => Kind | null;
  hideLanding: () => void;
  docKindOf: (doc: Doc | null) => Kind | null;
  codeKindOf: (word: string | null) => Kind | null;
  scriptLanguage: () => string | null;
  newModeFile: (language: string) => Promise<void>;
  languageWords: Record<string, string>;
  startLabel: (kind: TabKind) => string;
  newLabel: (label: string) => void;
  newEntries: (anchor: HTMLElement) => MenuEntry[];
  projectEntries: () => MenuEntry[];
  saves: () => boolean;
  explorerOpen: () => boolean;
  canSplit: (doc: Doc | null) => boolean;
  splitDoc: (doc: Doc | null, side: Side) => void;
  splitWhy: string;
  open: (path?: string) => Promise<void>;
  save: (doc: Doc | null, as?: boolean) => Promise<boolean>;
  saveFront: (as?: boolean) => Promise<unknown>;
  firstDataset: () => Promise<string>;
  sabOpen: () => boolean;
  importDocuments: () => Promise<void>;
  recentMenu: (anchor: HTMLElement) => void;
  exportDocument: (doc: Doc | null, format: "script" | "notebook") => Promise<unknown>;
  inSession: (doc: Doc | null | undefined) => boolean;
  kernelOf: () => Kernel;
  moves: (doc: Doc) => boolean;
  docMark: (doc: Doc) => "notebook" | "script" | undefined;
  popOut: (doc: Doc) => Promise<unknown>;
  moveToMain: (doc: Doc) => Promise<unknown>;
  isMainWindow: () => boolean;
  close: (doc: Doc) => void;
  fullScreen: () => unknown;
  isApiFile: (doc: Doc) => boolean;
  runApi: (doc: Doc, from?: HTMLElement) => Promise<void>;
  dataView: (doc: Doc) => string;
  modeSwitch: (doc: Doc) => HTMLElement | null;
  tablesHost: HTMLElement;
  drawTablesTool: () => void;
  readonly current: Doc | null;
}

export function workbenchBars(host: BarsHost) {
  const { top, landingKind, hideLanding, docKindOf, codeKindOf, scriptLanguage, newModeFile, startLabel, newEntries, projectEntries, saves } = host;
  const { canSplit, splitDoc, open, save, saveFront, firstDataset, sabOpen, importDocuments, recentMenu, exportDocument, inSession, kernelOf } = host;
  const { moves, docMark, popOut, moveToMain, isMainWindow, close, fullScreen, isApiFile, runApi, modeSwitch, tablesHost, drawTablesTool } = host;
  const LANGUAGE_WORDS = host.languageWords;
  const SPLIT_WHY = host.splitWhy;
  const openProjectLibraries = (): void => openEnvironment("library");

  // ----- the top bar: the mark, the focused document's name, Save, Save as…, "…"

  const topName = h("span", { class: "wb-name" });
  const saveButton = button("Save", () => void saveFront().catch((e: Error) => errorHere(e)), { icon: "save", title: "Save (Ctrl+S)" });
  const topProject = menuButton(button("Project", () => undefined, { icon: "project", class: "ghost wb-project" }), "Project", () => projectEntries());
  const saveAsButton = button("Save as…", () => void save(host.current, true), { icon: "save", title: "Save as (Ctrl+Shift+S)" });
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
    return landingKind() ?? docKindOf(host.current) ?? codeKindOf(new URLSearchParams(location.search).get("kind")) ?? "notebook";
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
    if (landingKind()) {
      hideLanding();
      void go(withParams({ view: null, kind: k }), "push");
    }
    start.run();
  }

  function drawTop(): void {
    const doc = host.current;
    const makes = tabKinds().find((t) => t.mark === topKind() && t.start);
    const own = topKind() === "script" ? scriptLanguage() : null;
    const making = own ? `New ${LANGUAGE_WORDS[own] ?? own} file` : makes ? startLabel(makes) : "";
    const newLabel = topNew.querySelector(".btn-label");
    if (newLabel && making) newLabel.textContent = making;
    topNew.title = making;
    topNew.setAttribute("aria-label", making || "New");
    if (making) host.newLabel(making); // the explorer's New says the same
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
    const shown = host.explorerOpen();
    return [
      ...newEntries(topMenu),
      null,
      { label: "Split right", icon: "splitRight", keys: "Ctrl+\\", disabled: !canSplit(host.current), title: canSplit(host.current) ? undefined : SPLIT_WHY, run: () => splitDoc(host.current, "right") },
      { label: "Split down", icon: "splitDown", disabled: !canSplit(host.current), title: canSplit(host.current) ? undefined : SPLIT_WHY, run: () => splitDoc(host.current, "down") },
      null,
      { label: shown ? "Close the Data Explorer" : "Data Explorer", icon: "zoom", keys: "Ctrl+Shift+E", run: () => void runCommand("view.explorer") },
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
        { label: "DAX", icon: "group", title: "A query on a Power BI workspace's dataset", run: () => void firstDataset().then((d) => doc.script!.addDax(d)) },
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
      ...(kernel ? sessionEntries(kernel, inSession(doc)) : []),
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
    const row = host.controls();
    const doc = host.current;
    if (!doc) return void row.replaceChildren();
    const more = button("Document menu", () => undefined, { icon: "more", iconOnly: true, class: "ghost wb-more", title: "More" });
    menuButton(more, "Document menu", () => moreEntries(doc, more), { align: "right" });
    // Its own Save in its row (no top bar: the owner, 2026-11-21); Save as… is its "…" or Ctrl+Shift+S.
    const saveHere = button("Save", () => void saveFront().catch((e: Error) => errorHere(e)), { icon: "save", iconOnly: true, class: "ghost wb-save", title: "Save (Ctrl+S)" });
    const full = document.body.classList.contains("wb-full"); // workbenchView.ts fullScreen sets it first
    const fullButton = button(full ? "Leave full screen" : "Full screen", () => void fullScreen(), { icon: full ? "restore" : "max", iconOnly: true, class: "ghost wb-full-toggle", title: full ? "Leave full screen (Escape)" : "Full screen (F11)", pressed: full });
    if (doc.workbook) return void row.replaceChildren(doc.workbook.tools, saveHere, more);
    if (!doc.notebook && !doc.script) return void row.replaceChildren(more);
    const addCell = h("button", { type: "button", class: "btn line wb-add-cell", "aria-label": "Add cell", title: "Add cell" }, icon("plus"), h("span", { class: "btn-label" }, "Cell"), icon("down")) as HTMLButtonElement;
    menuButton(addCell, "Cell kinds", () => cellEntries(doc));
    const run = doc.notebook
      ? button("Run all", () => void doc.notebook!.runAll(), { icon: "play", class: "primary", title: "Run all (F5)" })
      : isApiFile(doc)
        ? button("Run API", busyClick("Starting…", (b) => runApi(doc, b)), { icon: "play", class: "primary", title: "Run the local sandbox API (F5)" })
        : button("Run file", () => void doc.script!.runFile(), { icon: "play", class: "primary", title: "Run file (F5)" });
    const debugButton = doc.debug ? button("Start debugging", () => void doc.debug!.start().catch((e: Error) => errorHere(e)), { icon: "bug", iconOnly: true, class: "ghost wb-debug-start", title: "Start debugging (Ctrl+Shift+D)" }) : null;
    const view = host.dataView(doc);
    // No "+ Cell" on a script (the owner, 2026-11-17: "cell insert is available on the script page and it
    // shouldnt be"): cells are a notebook's.
    row.replaceChildren(...[modeSwitch(doc), tablesHost, view === "cells" && doc.notebook ? addCell : null, view === "cells" ? run : null, debugButton, saveHere, more, fullButton].filter((e): e is HTMLElement => e !== null));
    drawTablesTool();
  }

  async function restartKernel(kernel: Kernel): Promise<boolean> {
    // The project's one session: every notebook's and script's variables go, so it is asked first.
    if (kernel.shared && kernel.id && !(await askYesNo("Restart the project's Python session? Every variable is cleared, for every notebook and script of the project."))) return false;
    const did = await kernel.restart();
    toast(did ? (kernel.shared ? "The project's Python session was restarted: every variable is cleared." : "Restarted") : "Nothing to restart");
    return did;
  }

  /** The session's entries (the status bar's menu and a document's "…"): for a project's document they say
   *  whose they are, and one more stops the session for all of them. */
  function sessionEntries(kernel: Kernel, shared: boolean): { label: string; icon: string; title?: string; run: () => void }[] {
    if (!shared) {
      return [
        { label: "Interrupt", icon: "stop", run: () => void kernel.interrupt() },
        { label: "Restart", icon: "back", run: () => void restartKernel(kernel) },
      ];
    }
    const words = kernel.sessionWords || projectPython()?.session || "";
    return [
      { label: "Interrupt the project's Python session", icon: "stop", title: words, run: () => void kernel.interrupt() },
      { label: "Restart the project's Python session", icon: "back", title: words, run: () => void restartKernel(kernel) },
      { label: "Libraries…", icon: "settings", title: "The project's Python and its libraries (the Environment page)", run: () => openProjectLibraries() },
    ];
  }

  /** Stop the document's Python: its own kernel, or (asked first) the project's one session for every
   *  document of the project. The next Run starts a new one. */
  async function stopSession(): Promise<{ stopped: boolean }> {
    const kernel = kernelOf();
    if (!kernel.id) return { stopped: false };
    if (kernel.shared && !(await askYesNo("Stop the project's Python session? Every variable is gone, for every notebook and script of the project. The next Run starts a new one."))) return { stopped: false };
    kernel.stop(false, kernel.shared);
    toast(kernel.shared ? "The project's Python session stopped" : "Kernel stopped");
    return { stopped: true };
  }

  return { topMenu, drawTop, topStart, drawControls, cellEntries, moveEntries, sessionEntries, restartKernel, stopSession, openProjectLibraries };
}
