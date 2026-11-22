/**
 * workbenchCommandList.ts: every action of a Workbench window by one name (the palette, the keys and the
 * agent's workbench_window run the same list). Moved out of workbenchPage.ts along its own heading (the
 * craft review of 2026-11-22), unchanged: a command's `run` calls the page's own functions, handed in as the
 * host (the page's names, typed from the page itself: CommandHost). The page's changing state (the
 * document in front, the open project) is read through the host each time, never copied. [WIRE]
 *
 *   workbenchCommands(h)  the list (registered by the page with workbenchCommands.ts registerCommands)
 */
import { searchScripts } from "./workbenchIde";
import { api, ApiError } from "./api";
import type { FilledSnippet } from "./starters";
import { openConnections } from "./connectionsWindow";
import { h, toast } from "./dom";
import { closeWindow, inApp } from "./desktopApp";
import { openFile, tableName } from "./openFile";
import { allCommands, type Command, openPalette, openShortcuts } from "./workbenchCommands";
import { type ExplorerState } from "./dataExplorer";
import { type Side } from "./workbenchGroups";
import { type StructureView } from "./structureDoc";
import { back, canGoBack, forward, goHome } from "./nav";
import { type NotebookView } from "./workbenchNotebook";
import { type ScriptView } from "./workbenchScript";
import { canvasAnywhere, offersCanvas } from "./modes";
import { closeProject, copyProject, exportOutline, saveProject } from "./projectFile";
import { errorHere } from "./errorNote";
import type { CommandHost, Doc } from "./workbenchPage";

export function workbenchCommands(h: CommandHost): Command[] {
  const {
    addApi, BASE_FONT, bladeDoc, browse, canSplit, close, dataViews, describe,
    dictionaryTables, docs, drawDictionaryView, drawStatus, explorerInsert, explorerPane, explorerTarget, exportData,
    exportDocument, fullScreen, giveTable, goToTable, groups, isCode, isData, isMainWindow,
    kernelOf, layout, moves, moveToMain, newProject, open, openAt, openCell,
    openNotebook, openProject, openScript, openStructureTab, openWorkbook, PAGE, popExplorer, popOut,
    present, rail, refreshFlow, restartKernel, runPrimary, sabOpen, save, saveFront,
    saveProjectDocuments, saves, setCodeFont, setDataView, show, showHelp, showLineage, showTransformations,
    sides, SPLIT_WHY, splitDoc, stopSession, structureOf, variables, viewOf, workbookInFront,
  } = h;

  const isScript = (): boolean => !!h.current?.script;
  const isNotebook = (): boolean => !!h.current?.notebook;
  const notebook = (): NotebookView => {
    if (!h.current?.notebook) throw new Error("The document in front is not a notebook.");
    return h.current.notebook;
  };
  const script = (): ScriptView => {
    if (!h.current?.script) throw new Error("The document in front is not a script.");
    return h.current.script;
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
    const view = h.current ? viewOf(h.current) : undefined;
    if (!view) throw new Error("No notebook or script is in front.");
    return view;
  };
  const kindArg = (args: Record<string, unknown>): "code" | "sql" | "dax" | "html" | "markdown" => {
    const kind = text(args, "kind") ?? "code";
    if (kind !== "code" && kind !== "sql" && kind !== "dax" && kind !== "html" && kind !== "markdown") throw new Error('kind is "code", "sql", "dax", "html" or "markdown".');
    return kind;
  };
  const step = (by: 1 | -1): void => {
    const order = groups.tabs(); // group by group, as the rows show them
    if (!h.current || order.length < 2) return;
    show(order[(order.indexOf(h.current) + by + order.length) % order.length]!);
  };
  /** A document named by `index` (from 0, as "documents" lists them), else the one in front. */
  const docArg = (args: Record<string, unknown>): Doc => {
    const at = num(args, "index");
    const doc = at === undefined ? h.current : docs[at];
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
        in_front: d === h.current,
        kernel: d.kernel ? { id: d.kernel.id, state: d.kernel.state, runs_waiting: Math.max(0, d.kernel.running - 1) } : null,
        python: d.python,
        selected_cell: d.notebook ? d.notebook.selected() : null,
        ...(d.structure ? { structure: d.structure.state() } : {}),
        group: groups.indexOf(d),
      })),
      // The tab groups in reading order: each one's documents (by index), the one in front, the focused one.
      groups: groups.list().map((g, index) => ({ index, documents: g.tabs.map((d) => docs.indexOf(d)), in_front: g.active ? docs.indexOf(g.active) : null, focused: g.focused })),
      panes: { ...layout.state(), data_explorer: explorerPane.popped() ? "popped" : explorerPane.isOpen() ? "open" : "closed" },
      cursor: h.current?.script || h.current?.notebook ? h.cursor : null,
    };
  }

  const COMMANDS: Command[] = [
    // File
    { id: "file.newNotebook", group: "File", title: "New notebook", keys: inApp() ? "Ctrl+N" : undefined, run: () => void openNotebook(null, [], null) },
    { id: "file.newScript", group: "File", title: "New script", run: () => void openScript(null, "", null) },
    { id: "file.newBlade", group: "File", title: "New blade", run: () => bladeDoc(null) },
    { id: "debug.start", group: "Debug", title: "Start debugging", keys: "Ctrl+Shift+D", when: () => !!h.current?.debug && !h.current.debug.active(), whyNot: "no script is in front on the Scripts page", run: () => void h.current!.debug!.start().catch((e: Error) => errorHere(e)) },
    { id: "debug.toggleBreakpoint", group: "Debug", title: "Toggle breakpoint", keys: "F9", when: () => !!h.current?.debug, whyNot: "no script is in front on the Scripts page", run: () => h.current!.debug!.toggleAtCursor() },
    { id: "debug.continue", group: "Debug", title: "Continue", keys: "F5", when: () => !!h.current?.debug?.paused(), whyNot: "not paused", run: () => void h.current!.debug!.step("continue") },
    { id: "debug.stepOver", group: "Debug", title: "Step over", keys: "F10", when: () => !!h.current?.debug?.paused(), whyNot: "not paused", run: () => void h.current!.debug!.step("over") },
    { id: "debug.stepInto", group: "Debug", title: "Step into", keys: "F11", when: () => !!h.current?.debug?.paused(), whyNot: "not paused", run: () => void h.current!.debug!.step("into") },
    { id: "debug.stepOut", group: "Debug", title: "Step out", keys: "Shift+F11", when: () => !!h.current?.debug?.paused(), whyNot: "not paused", run: () => void h.current!.debug!.step("out") },
    { id: "debug.stop", group: "Debug", title: "Stop debugging", keys: "Shift+F5", when: () => !!h.current?.debug?.active(), whyNot: "not debugging", run: () => void h.current!.debug!.stop() },
    // An app is widgets on the Canvas now (2026-11-21): the old name opens the Canvas page.
    { id: "file.newApp", group: "File", title: "New canvas (the Canvas page)", when: () => canvasAnywhere("streamlit"), whyNot: "the Streamlit extension is not installed (Extensions: Install)", run: () => {
      window.open("/streamlit/canvas", "sab-canvas");
      return { opened: "/streamlit/canvas" };
    } },
    { id: "file.open", group: "File", title: "Open a notebook or script…", keys: "Ctrl+O", args: "path: the file (without it, the file chooser opens)", run: (a) => open(text(a, "path")) },
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
    { id: "file.saveAs", group: "File", title: "Save a copy as…", keys: "Ctrl+Shift+S", when: saves, whyNot: "nothing that saves is in front", run: () => save(h.current, true) },
    { id: "file.exportScript", group: "File", title: "Export as one Python script…", args: "path: where it goes (without it, the file chooser opens)", when: isCode, whyNot: "no notebook or script is in front", run: (a, from) => exportDocument(h.current, "script", text(a, "path"), from.agent) },
    { id: "file.exportNotebook", group: "File", title: "Export as one notebook…", args: "path: where it goes (without it, the file chooser opens)", when: isCode, whyNot: "no notebook or script is in front", run: (a, from) => exportDocument(h.current, "notebook", text(a, "path"), from.agent) },
    { id: "project.new", group: "Project", title: "New project…", args: "name: its name; folder: where it goes (default: the projects folder); notebooks: names of notebooks to make; app: true for a Streamlit app; type: a project type (project_types) (without a name, New project's dialog opens)", run: (a, from) => newProject(text(a, "folder"), text(a, "name"), Array.isArray(a.notebooks) ? (a.notebooks as string[]) : [], typeof a.app === "boolean" ? a.app : undefined, from.agent, text(a, "type")) },
    { id: "workbook.new", group: "Workbook", title: "New Excel workbook", args: "(the Excel canvas: offered while the open project's mode names it)", when: () => offersCanvas("excel"), whyNot: "the open project's mode has no Excel canvas", run: () => openWorkbook(null).workbook!.report() },
    { id: "workbook.play", group: "Workbook", title: "Play the workbook", when: () => !!h.current?.workbook, whyNot: "no workbook is in front", run: () => workbookInFront().play() },
    { id: "workbook.edit", group: "Workbook", title: "Edit the workbook's blocks", when: () => !!h.current?.workbook, whyNot: "no workbook is in front", run: () => (workbookInFront().edit(), workbookInFront().report()) },
    { id: "workbook.report", group: "Workbook", title: "The workbook in front, as it stands", when: () => !!h.current?.workbook, whyNot: "no workbook is in front", run: () => workbookInFront().report() },
    { id: "project.open", group: "Project", title: "Open project…", args: "folder: the project's folder (without it, the file chooser opens)", run: (a) => openProject(text(a, "folder")) },
    { id: "project.exportData", group: "Project", title: "Export data.py (from data.ipynb)", when: () => docs.some(isData) || !!h.project, whyNot: "no project is open", run: () => exportData() },
    // The desktop app's Ctrl+W (desktopApp.ts): the document in front, and the window once none is left.
    { id: "file.closeTab", group: "File", title: "Close the document in front (the window when none is open)", keys: inApp() ? "Ctrl+W" : undefined, run: () => (h.current ? close(h.current) : closeWindow()) },
    { id: "tabs.reopen", group: "Tabs", title: "Reopen the last closed table (in the home window)", keys: inApp() ? "Ctrl+Shift+T" : undefined, run: () => api("/grids/reopen", "POST").catch((e: ApiError) => (e.status === 404 ? toast("No closed table to reopen.") : errorHere(e))) },
    { id: "file.close", group: "File", title: "Close the document", args: "index: a document (default: the one in front)", when: () => docs.length > 0, whyNot: "nothing is open", run: (a) => {
      const at = num(a, "index");
      const doc = at === undefined ? h.current : docs[at];
      if (!doc) throw new Error(`There is no document ${at}.`);
      close(doc);
    } },
    // Documents
    { id: "documents", agentOnly: true, group: "Documents", title: "What is open", run: () => documents() },
    // A structure's tab (structureDoc.ts): open, search and explore, as the user does.
    { id: "structure.open", group: "Structure", title: "Open a JSON, YAML, XML or TOML file beside the code…", args: "path: the file; at: a node to select ($.orders[3])", run: async (a) => {
      const path = text(a, "path");
      if (!path) return open();
      const doc = await openStructureTab({ path });
      if (!doc?.structure) throw new Error(`${path} did not open (a missing package says so on the screen).`);
      const at = text(a, "at");
      if (at) doc.structure.select(at);
      return doc.structure.state();
    } },
    { id: "structure.search", group: "Structure", title: "Search the structure in front", args: "words; path: its file (default: the one in front)", run: (a) => {
      const view = structureOf(a);
      view.search(text(a, "words") ?? "");
      return view.state();
    } },
    { id: "structure.next", group: "Structure", title: "Next match", keys: "Enter", args: "back: true for the previous one", run: (a) => structureOf(a).next(a.back === true ? -1 : 1) },
    { id: "structure.select", agentOnly: true, group: "Structure", title: "Select a node by its path (its way unfolded)", args: "at: $.orders[3].lines; path: its file", run: (a) => structureOf(a).select(text(a, "at") ?? "$") },
    { id: "structure.view", group: "Structure", title: "Tree, Text or Both", args: "view: tree, text or both", run: (a) => {
      const v = text(a, "view");
      if (v !== "tree" && v !== "text" && v !== "both") throw new Error("view is tree, text or both.");
      structureOf(a).setView(v as StructureView);
    } },
    { id: "structure.format", group: "Structure", title: "Format the structure in front", run: (a) => structureOf(a).format() },
    { id: "structure.state", agentOnly: true, group: "Structure", title: "The structure in front: its view, selection, search and problems", run: (a) => structureOf(a).state() },
    { id: "doc.read", agentOnly: true, group: "Documents", title: "The front document's text or cells", when: isCode, whyNot: "no notebook or script is in front", run: () => (h.current?.notebook ? { kind: "notebook", cells: h.current.notebook.cells() } : { kind: "script", text: script().text() }) },
    { id: "doc.repoint", agentOnly: true, group: "Documents", title: "Point an open document's cells at another connection (unsaved until Save)", args: "path; from; to; cells: the cells' own numbers (null: a script's main code)", run: (a) => repointDocument(a) },
    { id: "doc.show", group: "Documents", title: "Show a document", args: "index, or path", run: (a) => {
      const at = num(a, "index");
      const path = text(a, "path");
      const doc = at !== undefined ? docs[at] : docs.find((d) => d.path === path);
      if (!doc) throw new Error("No open document matches.");
      show(doc);
    } },
    { id: "doc.popOut", group: "Documents", title: "Open the document in its own window", when: () => !!h.current && moves(h.current), whyNot: "no notebook, script or Streamlit app is in front", run: () => popOut(h.current!) },
    { id: "doc.moveToMain", group: "Documents", title: "Move the document to the main window", when: () => !!h.current && moves(h.current) && !isMainWindow(), whyNot: "this is the main window, or nothing that moves is in front", run: () => moveToMain(h.current!) },
    { id: "doc.next", group: "Documents", title: "Next document", keys: "Ctrl+Alt+PageDown", run: () => step(1) },
    { id: "doc.previous", group: "Documents", title: "Previous document", keys: "Ctrl+Alt+PageUp", run: () => step(-1) },
    // Run
    { id: "run.primary", group: "Run", title: "Run the file, or every cell", keys: "F5", when: isCode, whyNot: "no notebook or script is in front", run: () => runPrimary(h.current) },
    { id: "run.statement", group: "Run", title: "Run the statement at the cursor, then the next", keys: "Ctrl+Enter", when: isScript, whyNot: "the document in front is not a script", run: () => script().runSelection() },
    { id: "run.toHere", group: "Run", title: "Run from the top to the cursor", when: isScript, whyNot: "the document in front is not a script", run: () => script().runToHere() },
    { id: "run.fromHere", group: "Run", title: "Run from the cursor to the end", when: isScript, whyNot: "the document in front is not a script", run: () => script().runFromHere() },
    { id: "run.cell", group: "Run", title: "Run the selected cell", keys: "Ctrl+Enter", args: "index: a cell, from 0 (default: the selected one)", when: isNotebook, whyNot: "the document in front is not a notebook", run: (a) => notebook().runCell(num(a, "index")) },
    { id: "run.above", group: "Run", title: "Run the cells above", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().runAbove() },
    { id: "run.below", group: "Run", title: "Run this cell and the ones below", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().runBelow() },
    { id: "run.stopSession", group: "Run", title: "Stop the Python session", when: isCode, whyNot: "no notebook or script is in front", run: () => stopSession() },
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
      const dataset = text(a, "dataset") ?? h.datasetNames[0] ?? "";
      if (h.current?.notebook) {
        h.current.notebook.insert("below", "dax", source);
        if (dataset) h.current.notebook.setConnection(dataset);
        return { document: h.current.title, index: h.current.notebook.selected(), dataset: dataset || null };
      }
      await script().addDax(dataset, source);
      return { document: h.current!.title, dataset: dataset || null };
    } },
    { id: "snippet.insert", group: "Cell", title: "Insert a snippet…", args: "name: a snippet (blades_starters); values: {placeholder: value} (with them, no form: the agent's); number: the cell's own number (default: the selected cell, else a new one)", when: isCode, whyNot: "no notebook or script is in front", run: async (a, from) => {
      const name = text(a, "name");
      const values = (a.values && typeof a.values === "object" ? a.values : {}) as Record<string, unknown>;
      const number = num(a, "number");
      if (h.current?.notebook) {
        if (!name && !from.agent) return void h.current.notebook.insertSnippetHere();
        if (!name) throw new Error("Send the snippet's name (blades_starters lists them).");
        return { document: h.current.title, ...(await h.current.notebook.insertSnippet(name, values, number)) };
      }
      if (!name) throw new Error("Send the snippet's name (blades_starters lists them).");
      const filled = await api<FilledSnippet>(`/blades/${encodeURIComponent(name)}/snippet`, "POST", { values });
      if (filled.language === "dax") await script().addDax(h.datasetNames[0] ?? "", filled.text);
      else if (filled.language === "html") await script().addHtml(filled.text);
      else await script().addCode(filled.text, filled.cell_name ?? "");
      return { document: h.current!.title, language: filled.language, name: filled.cell_name };
    } },
    { id: "cell.toHtml", group: "Cell", title: "Make it an HTML cell", keys: "H", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().setKind("html") },
    { id: "cell.copy", group: "Cell", title: "Copy the cell (for a paste into a notebook)", keys: "C", args: "number: the cell's own number (default: the selected cell, or the cursor's)", when: isCode, whyNot: "no notebook or script is in front", run: (a) => (h.current?.notebook ? notebook().copy(num(a, "number")) : script().copy(num(a, "number"))) },
    { id: "cell.paste", group: "Cell", title: "Paste the copied cell", keys: "V", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => {
      if (!notebook().paste()) throw new Error("No cell was copied.");
      return { index: notebook().selected() };
    } },
    { id: "cell.edit", group: "Cell", title: "Edit the cell (an HTML or Markdown cell that shows as drawn)", keys: "Enter", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().editSelected() },
    { id: "cell.duplicate", group: "Cell", title: "Duplicate the cell", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().duplicate() },
    { id: "cell.clearOutput", group: "Cell", title: "Clear the cell's output", args: "index (default: the selected one)", when: isNotebook, whyNot: "the document in front is not a notebook", run: (a) => notebook().clearOutput(num(a, "index")) },
    { id: "cell.clearAll", group: "Cell", title: "Clear every output", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().clearAll() },
    { id: "cell.toggleOutput", group: "Cell", title: "Hide or show the cell's output", keys: "O", when: isNotebook, whyNot: "the document in front is not a notebook", run: () => notebook().toggleOutput() },
    { id: "cell.name", group: "Cell", title: "Name the cell…", args: "number: the cell's own number (default: the selected cell, or the cursor's); name: one line (\"\" takes the name away; without it, the name is typed in place)", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
      const name = text(a, "name");
      const view = h.current?.notebook ?? script();
      if (name === undefined) return void view.editName();
      return view.nameCell(num(a, "number"), name);
    } },
    { id: "lineage.open", group: "Cell", title: "Lineage: the cell back to the data, with its values", args: "number: a cell's own number (default: the selected cell, or the cursor's)", when: isCode, whyNot: "no notebook or script is in front", run: async (a) => {
      const graph = await showLineage({ number: num(a, "number") });
      return { target: graph.nodes.find((n) => n.target)?.label ?? null, nodes: graph.nodes.length, mermaid: graph.mermaid };
    } },
    { id: "cell.goTo", group: "Cell", title: "Go to a cell by its number", args: "number: the cell's own number (as @cell7 links to it)", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
      const number = num(a, "number");
      if (number === undefined) throw new Error("Send the cell's number.");
      if (!tablesView().goTo(number)) throw new Error(`There is no cell ${number} in the document in front.`);
      return { cell: number };
    } },
    // Tables: every table open in the grid has a read-only cell in its document
    { id: "tables.list", agentOnly: true, group: "Tables", title: "The document's tables and each cell's state", when: isCode, whyNot: "no notebook or script is in front", run: () => ({ document: h.current!.title, tables: tablesView().tables() }) },
    { id: "tables.add", group: "Tables", title: "Add a table open in Grids to the document in front (its read-only cell)", args: "table: the table's name", when: isCode, whyNot: "no notebook or script is in front", run: async (a) => {
      const table = text(a, "table");
      if (!table) throw new Error("Send the table's name.");
      return { table: await giveTable(h.current!, table), document: h.current!.title };
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
      if (h.current?.notebook) {
        h.current.notebook.insert("below", "html", source);
        const added = h.current.notebook.htmlCells().find((c) => c.index === h.current!.notebook!.selected());
        if (added?.number != null && height !== null) h.current.notebook.resizeHtml(added.number, height);
        // With HTML it shows its design at once; an empty one waits for typing.
        if (source.trim()) h.current.notebook.commandMode();
        return { document: h.current.title, cell: h.current.notebook.htmlCells().find((c) => c.index === h.current!.notebook!.selected()) ?? null };
      }
      await script().addHtml(source, height);
      return { document: h.current!.title, cells: script().htmlCells() };
    } },
    { id: "html.list", agentOnly: true, group: "HTML", title: "The document's HTML cells (and Markdown cells with names): each one's text, names and state", when: isCode, whyNot: "no notebook or script is in front", run: () => ({ document: h.current!.title, cells: tablesView().htmlCells() }) },
    { id: "html.run", group: "HTML", title: "Run an HTML cell (or a Markdown cell with names): fill its names and draw it", args: "number: the cell's own number (default: every one not up to date)", when: isCode, whyNot: "no notebook or script is in front", run: async (a) => ({ document: h.current!.title, cells: await tablesView().runHtml(num(a, "number")) }) },
    { id: "html.resize", group: "HTML", title: "Size an HTML cell's pane", args: "number: the cell's own number; height: pixels (60 to 2000; without it: the design's own height)", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
      const number = num(a, "number");
      if (number === undefined) throw new Error("Send the cell's number.");
      tablesView().resizeHtml(number, num(a, "height") ?? null);
      return { cell: number, height: num(a, "height") ?? null };
    } },
    { id: "html.edit", group: "HTML", title: "Open an HTML cell's HTML", args: "number: the cell's own number", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
      const number = num(a, "number");
      if (number === undefined) throw new Error("Send the cell's number.");
      if (h.current?.notebook) {
        const at = h.current.notebook.htmlCells().find((c) => c.number === number);
        if (!at) throw new Error(`This notebook has no HTML cell ${number}.`);
        h.current.notebook.select(at.index, true);
      } else script().editHtml(number);
      return { cell: number };
    } },
    // The Workbench's modes (2026-11-15): Notebook, Script and Data (App mode went with app notebooks, 2026-11-21)
    { id: "mode.panel", group: "View", title: "Show or hide a panel of the document in front (Outline, Run settings)", args: 'panel: "outline" or "runSettings"; show: true or false (default: the other way)', when: () => !!h.current?.modes, whyNot: "the document in front has no panels", run: (a) => {
      const panel = text(a, "panel");
      const doc = h.current!;
      if (!panel || !doc.modes!.panels().some((p) => p.id === panel)) throw new Error(`The document in front has these panels: ${doc.modes!.panels().map((p) => p.id).join(", ") || "none"}.`);
      const show = a.show === undefined ? undefined : a.show === true;
      const open = doc.modes!.toggle(panel, show);
      drawStatus();
      return { panel, open };
    } },
    { id: "notebook.runOrder", agentOnly: true, group: "Notebook", title: "The run order: each cell's makes, reads and state (notRun, edited, outOfDate with the names, current)", when: isNotebook, whyNot: "the document in front is not a notebook", run: async () => (await refreshFlow(h.current!))?.cells ?? [] },
    { id: "notebook.outline", agentOnly: true, group: "Notebook", title: "The Outline: the Markdown headings and the named cells", when: isNotebook, whyNot: "the document in front is not a notebook", run: async () => (await refreshFlow(h.current!))?.outline ?? [] },
    { id: "run.upToHere", group: "Run", title: "Run up to here: every cell from the top to the selected one", args: "number: a cell's own number (default: the selected cell)", when: isNotebook, whyNot: "the document in front is not a notebook", run: async (a) => {
      await notebook().runUpTo(num(a, "number"));
      return (await refreshFlow(h.current!))?.cells ?? [];
    } },
    { id: "notebook.present", group: "Notebook", title: "Present: the notebook as a document (no code)", args: "on: true or false (default: the other way)", when: () => isNotebook() && !dataViews.has(h.current!), whyNot: "the document in front is not a notebook (data.ipynb has its own views)", run: (a) => ({ presenting: present(h.current!, a.on === undefined ? undefined : a.on === true) }) },
    { id: "data.view", group: "Data", title: "data.ipynb's view: Cells, Lineage or Dictionary", args: 'view: "cells", "lineage" or "dictionary"', when: () => !!h.current && dataViews.has(h.current), whyNot: "the document in front is not a project's data.ipynb", run: (a) => {
      const view = text(a, "view") ?? "cells";
      if (view !== "cells" && view !== "lineage" && view !== "dictionary") throw new Error('view is "cells", "lineage" or "dictionary".');
      return { view: setDataView(h.current!, view) };
    } },
    { id: "dictionary.list", agentOnly: true, group: "Data", title: "The data dictionary: each table's columns, plain types, descriptions, where each comes from", when: () => !!h.current && dataViews.has(h.current), whyNot: "the document in front is not a project's data.ipynb", run: () => dictionaryTables(h.current!) },
    { id: "dictionary.describe", group: "Data", title: "Describe a table or a column in the data dictionary (kept in data.ipynb, written into data.py)", args: "table; column (none: the table itself); text (empty: no description)", when: () => !!h.current && dataViews.has(h.current), whyNot: "the document in front is not a project's data.ipynb", run: (a) => {
      const table = text(a, "table");
      if (!table) throw new Error("Send table.");
      const said = describe(h.current!, table, text(a, "column") ?? null, text(a, "text") ?? "");
      void drawDictionaryView(h.current!);
      return said;
    } },
    // Console
    { id: "console.focus", group: "Console", title: "Go to the console", keys: "Ctrl+2", when: isCode, whyNot: "no notebook or script is in front", run: () => layout.focus("console") },
    { id: "console.run", group: "Console", title: "Run code in the console", args: "code", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
      const code = text(a, "code");
      if (!code?.trim()) throw new Error("Send the code to run.");
      return h.current!.console!.run({ code }, code.split("\n").map((l, i) => `${i ? "..." : ">>>"} ${l}`).join("\n"));
    } },
    { id: "console.read", agentOnly: true, group: "Console", title: "What the console shows", when: isCode, whyNot: "no notebook or script is in front", run: () => h.current!.console!.text() },
    { id: "console.clear", group: "Console", title: "Clear the console", when: isCode, whyNot: "no notebook or script is in front", run: () => h.current!.console!.clear() },
    // View
    { id: "palette", group: "View", title: "Show every command", keys: "Ctrl+Shift+P", run: () => openPalette() },
    { id: "view.source", group: "View", title: "Go to the source", keys: "Ctrl+1", run: () => layout.focus("source") },
    { id: "view.variables", group: "View", title: "Go to the Environment", keys: "Ctrl+3", run: () => layout.focus("variables") },
    { id: "view.nextPane", group: "View", title: "Next pane", keys: "F6", run: () => layout.cycle(1) },
    { id: "view.previousPane", group: "View", title: "Previous pane", keys: "Shift+F6", run: () => layout.cycle(-1) },
    // Full screen (the owner, 2026-11-21: "the ide pane should be fullscreenable"): the tabs and the editor fill
    // the window; the rail, the explorer and the bottom panels go; Escape or the same button comes back.
    { id: "view.fullScreen", group: "View", title: "Full screen", keys: "F11", args: "on: true or false (default: the other way)", run: (a) => ({ on: fullScreen(typeof a.on === "boolean" ? a.on : undefined) }) },
    { id: "view.codeSize", group: "View", title: "Code size", args: "px: 8 to 40 (13: as it was)", run: (a) => ({ px: setCodeFont(typeof a.px === "number" ? a.px : BASE_FONT) }) },
    { id: "view.files", group: "View", title: "Show or hide the Files pane", keys: "Ctrl+B", args: "show: true or false (default: the other way)", run: (a) => ({ open: sides.show("files", typeof a.show === "boolean" ? a.show : undefined) }) },
    { id: "view.blades", group: "View", title: "Show or hide the Blades pane", args: "show: true or false (default: the other way)", when: () => PAGE === "scripts", whyNot: "the Blades pane is on the Scripts page", run: (a) => ({ open: sides.show("blades", typeof a.show === "boolean" ? a.show : undefined) }) },
    ...(PAGE === "scripts"
      ? [{ id: "search.scripts", group: "Find", title: "Search in scripts…", keys: "Ctrl+Shift+F", run: () => (searchScripts({ openAt: (p: string, line: number) => void openAt(p, line) }, () => (h.current?.script ? { path: () => h.current!.path, text: () => h.current!.script!.text(), python: () => h.current!.python, replaceText: (t: string) => h.current!.script!.replaceText(t), reveal: (line: number) => h.current!.script!.reveal(line) } : null)), { opened: true }) }]
      : []),
    { id: "view.explorer", group: "View", title: "Show or hide the Data Explorer", keys: "Ctrl+Shift+E", args: "show: true or false (default: the other way)", run: (a) => {
      const show = typeof a.show === "boolean" ? a.show : undefined;
      return { open: explorerPane.toggle(show), popped: false };
    } },
    { id: "view.toggleRight", group: "View", title: "Show or hide the Environment", args: "show: true or false (default: the other way)", run: (a) => {
      const shown = layout.toggle("right", typeof a.show === "boolean" ? a.show : undefined);
      if (shown) void variables.refresh();
      drawStatus();
      return { shown };
    } },
    { id: "view.toggleConsole", group: "View", title: "Show or hide the console", args: "show: true or false (default: the other way)", run: (a) => {
      const shown = layout.toggle("console", typeof a.show === "boolean" ? a.show : undefined);
      drawStatus();
      return { shown };
    } },
    { id: "view.standard", group: "View", title: "Layout: standard", run: () => { layout.setLayout("standard"); drawStatus(); } },
    { id: "view.focus", group: "View", title: "Layout: source only", keys: "Ctrl+Shift+1", run: () => { layout.setLayout("focus"); drawStatus(); } },
    { id: "view.wide", group: "View", title: "Layout: wide data", run: () => { layout.setLayout("wide"); drawStatus(); } },
    // Groups: tabs side by side or stacked, as Visual Studio Code's editor groups
    { id: "group.splitRight", group: "Groups", title: "Split right: the tab moves to a new group on the right", keys: "Ctrl+\\", args: "index: a document (default: the one in front)", when: () => canSplit(h.current), whyNot: SPLIT_WHY, run: (a) => {
      splitDoc(docArg(a), "right");
      return { groups: groups.list().length, focused: groups.focusedIndex() };
    } },
    { id: "group.splitDown", group: "Groups", title: "Split down: the tab moves to a new group below", args: "index: a document (default: the one in front)", when: () => canSplit(h.current), whyNot: SPLIT_WHY, run: (a) => {
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
    { id: "data.list", agentOnly: true, group: "Data", title: "The open tables and the blades' variables (the Data Explorer finds more: explorer.search)", run: () => ({ tables: h.tables.map((t) => ({ name: t.name, rows: t.rows ?? null, source: t.source ?? "", steps: t.steps })), variables: h.bladeVariables.map((b) => ({ name: b.variable ?? b.name, blade: b.name, description: b.description })), explorer: explorerPane.popped() ? "popped" : explorerPane.isOpen() ? "open" : "closed" }) },
    // The Data Explorer (workbenchExplorer.ts, dataExplorer.ts): its search, its Insert, popping out and back
    { id: "explorer.search", group: "Data", title: "Search the Data Explorer (it opens): its results as data", args: "text; kinds: a list of connections, tables, columns, structures, apis, variables, blades; connection; column: a column's exact name", run: async (a) => {
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
    { id: "explorer.popOut", group: "Data", title: "Pop the Data Explorer out: the Data page in a window of its own, with its search", run: () => popExplorer() },
    { id: "tables.transformations", group: "Tables", title: "Show a table's transformations (its read-only cell, wherever it lives)", args: "table: the table's name", run: (a) => {
      const table = text(a, "table");
      if (!table) throw new Error("Send the table's name.");
      return showTransformations(table);
    } },
    { id: "data.goToTable", group: "Data", title: "Go to a table's cell in the focused document", args: "table: the table's name", when: isCode, whyNot: "no notebook or script is in front", run: (a) => {
      const table = text(a, "table");
      if (!table) throw new Error("Send the table's name.");
      const line = tablesView().tables().find((t) => t.name === table);
      if (!line?.cell) throw new Error(`${table} has no cell in ${h.current!.title}.`);
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
    { id: "view.variablesRefresh", group: "View", title: "Read the Environment again (its rows: tables, variables, structures, settings, libraries)", run: () => variables.refresh().then(() => variables.snapshot()) },
    // Getting around (nav.ts): the mark's Home, and the browser's Back and Forward inside the app
    { id: "nav.home", group: "Go", title: "Home: Projects, in the home window", keys: "Alt+Home", run: () => goHome() },
    { id: "nav.back", group: "Go", title: "Back", keys: "Alt+Left", when: canGoBack, whyNot: "nothing to go back to in this window", run: () => back() },
    { id: "nav.forward", group: "Go", title: "Forward", keys: "Alt+Right", run: () => forward() },
    // Help
    { id: "help.shortcuts", group: "Help", title: "Keyboard shortcuts", keys: "?", run: () => openShortcuts() },
    { id: "help.atCursor", group: "Help", title: "Help on the name at the cursor", keys: "F1", when: isCode, whyNot: "no notebook or script is in front", run: () => showHelp() },
    { id: "commands", agentOnly: true, group: "Help", title: "Every command and its arguments", run: () => allCommands().map((c) => ({ id: c.id, title: c.title, group: c.group, keys: c.keys ?? null, args: c.args ?? null, available: c.when ? c.when() : true })) },
  ];
  return COMMANDS;
}
