/**
 * workbenchNotebookCell.ts: one cell of a notebook made and drawn: its parts (the output area, the pickers,
 * the name box, the design pane), its head (a user's cell's, a table's read-only cell's), a heading's line,
 * what its element listens for (the pickers, the drag of its `@cell` link, right-click, a dropped snippet,
 * the two faces of an HTML or Markdown cell), its editor with the Workbench's intelligence, and its More
 * menu. A part of workbenchNotebook.ts's notebookView (workbenchNotebookState.ts says how the parts fit).
 * [VIEW]
 */
import { cleanName, MAX_CELL_NAME } from "./cellClipboard";
import { button, clear, h, type MenuItem, showMenu } from "./dom";
import { inlineSource } from "./inlineCompletion";
import { loadEditors } from "./lazyLoad";
import { hasSource, isApp, isHeading, snippetLanguage, sqlLine, twoFaced } from "./notebookCells";
import { openRoutedTable } from "./routedCells";
import { draggedSnippet, SNIPPET_DRAG } from "./starters";
import { codeItem, currentDocument, sendToAgent } from "./workbenchAgent";
import { datasetsWanted, daxCompleter, isWorkspace, sqlCompleter } from "./workbenchCompletion";
import { runFromOutputs } from "./workbenchHtml";
import { pythonIntel, showProblems } from "./workbenchIntel";
import { clearOutput, copy, drawName, duplicate, edit, editName, insertAt, moveCell, next, paste, removeCell, setKind, setName, toggleOutput } from "./workbenchNotebookEdits";
import { hooksOf } from "./workbenchNotebookErrors";
import { knowTypes, run, runEach, runUpTo } from "./workbenchNotebookRuns";
import { dropSnippet, insertSnippetInto } from "./workbenchNotebookSnippets";
import { byNumber, type Cell, type CellData, type CellKind, connectionsSoon, drawNamed, edited, FIRST_HINT, focusEditor, indexOf, isText, KIND_NAMES, LANGUAGE, type Notebook, offeredKinds, relabel, ROUTED, routeOf, select, sourceOf, sources, toCommandMode } from "./workbenchNotebookState";
import { goTo, redraw, typedSoon } from "./workbenchNotebookTables";
import { drawHtmlState, editHtml, editMarkdown, pane, showDesign, showMarkdown } from "./workbenchNotebookText";
import { type OutputArea, outputArea, resultName } from "./workbenchOutputs";
import { firstLine } from "./workbenchTables";

/** A cell's More menu: run above and below, insert, name, lineage, a snippet, copy and paste, its output. */
export function cellMenu(nb: Notebook, cell: Cell, anchor: HTMLElement): void {
  document.querySelector(".menu")?.remove();
  const item = (text: string, act: () => void): HTMLElement =>
    h("button", { type: "button", role: "menuitem", onclick: () => { menu.remove(); select(nb, cell); act(); } }, text);
  const at = (): number => indexOf(nb, cell);
  const menu = h(
    "div",
    { class: "menu", role: "menu", "aria-label": "Cell actions" },
    item("Run the cells above", () => void runEach(nb, nb.cells.slice(0, at()))),
    item("Run this cell and the ones below", () => void runEach(nb, nb.cells.slice(at()))),
    item("Insert a cell above", () => insertAt(nb, at(), cell.kind === "markdown" ? "code" : cell.kind)),
    item("Insert a cell below", () => insertAt(nb, at() + 1, cell.kind === "markdown" ? "code" : cell.kind)),
    item("Name…", () => editName(nb, cell)),
    ...(nb.hooks.lineage && !isHeading(cell.role) ? [item("Lineage", () => nb.hooks.lineage!(cell.number))] : []),
    ...(snippetLanguage(cell) ? [item("Insert a snippet…", () => void insertSnippetInto(nb, cell))] : []),
    item("Copy", () => void copy(cell)),
    item("Paste below", () => void paste(nb, cell)),
    item("Duplicate", () => duplicate(nb, cell)),
    item("Clear the output", () => clearOutput(nb, cell)),
    item(cell.element.classList.contains("output-hidden") ? "Show the output" : "Hide the output", () => toggleOutput(cell)),
  );
  document.body.append(menu);
  const box = anchor.getBoundingClientRect();
  menu.style.top = `${box.bottom + 4}px`;
  menu.style.left = `${Math.max(8, Math.min(box.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 8))}px`;
  (menu.querySelector("button") as HTMLButtonElement | null)?.focus();
  setTimeout(() => document.addEventListener("mousedown", function away(e) { if (!menu.contains(e.target as Node)) { menu.remove(); document.removeEventListener("mousedown", away); } }));
  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      menu.remove();
      anchor.focus();
    }
  });
}

/** A cell before it has its element: everything its record holds but that. */
type Parts = Omit<Cell, "element">;

/** A cell's data as this version reads it. */
function asOpened(given: CellData): CellData {
  // A SQL cell saved on a Power BI connection (before DAX cells) is a DAX cell.
  const old = given.kind === "sql" && !!given.connection && isWorkspace(given.connection.split("/")[0]!.trim());
  // A window that still holds a Streamlit cell from before the canvas: a Python cell, shown live.
  const once = (given.kind as string) === "streamlit";
  return old ? { ...given, kind: "dax" } : once ? { ...given, kind: "code", live: true } : given;
}

/** A cell's output area. Its hooks need the cell, made after it: they look it up when an error comes. */
function cellOutputs(nb: Notebook, self: () => Cell | null): OutputArea {
  return outputArea(nb.dark, () => undefined, {
    shown: (d) => {
      const cell = self();
      return cell && hooksOf(nb, cell).shown?.(d);
    },
    fix: (f, d) => {
      const cell = self();
      return cell && hooksOf(nb, cell).fix(f, d);
    },
    goTo: (f) => {
      const cell = self();
      return cell ? hooksOf(nb, cell).goTo(f) : false;
    },
    openGrid: nb.hooks.openGrid,
    openResult: (n) => nb.hooks.openResult?.(n, resultName(self()?.editor?.value() ?? self()?.source ?? "")),
    openTable: (id) => {
      const cell = self();
      const route = cell ? routeOf(cell) : null;
      if (route) void openRoutedTable(route, nb.kernel.intel().path, id, cell?.name ? cell.name.replace(/\W+/g, "_") : undefined);
    },
  });
}

/** The cell's name, typed in place (or More: Name…). Without one, the area shows only on hover. */
function nameBox(nb: Notebook, cell: () => Cell): HTMLInputElement {
  const box = h("input", { type: "text", class: "wb-cell-name", maxlength: MAX_CELL_NAME, placeholder: "Name", "aria-label": "Cell name", spellcheck: "false" }) as HTMLInputElement;
  box.addEventListener("keydown", (e) => {
    e.stopPropagation(); // Jupyter's keys stay out of the name
    if (e.key === "Enter" || e.key === "Escape") {
      e.preventDefault();
      if (e.key === "Escape") box.value = cell().name ?? "";
      box.blur();
    }
  });
  box.addEventListener("change", () => setName(nb, cell(), box.value));
  box.addEventListener("blur", () => setName(nb, cell(), box.value));
  box.addEventListener("click", (e) => e.stopPropagation());
  return box;
}

/** Everything a cell's record holds but its element. `cell` is the cell once made; `self` is null until then. */
function cellParts(nb: Notebook, data: CellData, number: number, cell: () => Cell, self: () => Cell | null): Parts {
  const role = data.role ?? "";
  // A Markdown cell with names: its state above its text, as an HTML cell's design bar.
  const textStatus = h("span", { class: "wb-design-state", role: "status" });
  const textRun = button("Run", () => void run(nb, cell()), { icon: "play", class: "ghost wb-design-run", title: "Run: fill the names from the kernel (Ctrl+Enter)" });
  const bar = isHeading(role) ? h("div", { class: "wb-group-bar" }) : null;
  return {
    kind: data.kind,
    source: data.source,
    connection: data.connection,
    execution_count: data.execution_count,
    editor: null,
    area: cellOutputs(nb, self),
    view: h("div", { class: "wb-markdown-view" }),
    textBar: { element: h("div", { class: "wb-design-bar wb-text-bar" }, textStatus, h("span", { class: "spacer" }), textRun), status: textStatus, run: textRun },
    count: h("span", { class: "wb-count" }, data.execution_count ? `[${data.execution_count}]` : "[ ]"),
    kindPicker: h("select", { "aria-label": "Cell kind" }, ...offeredKinds(data.kind).map((k) => h("option", { value: k, selected: k === data.kind }, KIND_NAMES[k]))) as HTMLSelectElement,
    connectionPicker: h("select", { "aria-label": "Connection", class: "wb-connection", title: "Connection" }) as HTMLSelectElement,
    wantsFocus: false,
    number,
    role,
    table: data.table ?? null,
    grouped: data.grouped ?? false,
    steps: data.steps ?? null,
    bar,
    status: role === "transformations" ? h("span", { class: "wb-table-state", role: "status" }) : null,
    part: h("span", { class: "wb-part hint" }),
    design: bar ? null : pane(nb, data.kind, data.height ?? null, cell).design,
    editorHost: h("div", { class: "wb-editor" }),
    name: data.name ? cleanName(data.name) || null : null,
    nameButton: role === "transformations" || bar ? null : nameBox(nb, cell),
    htmlRun: data.kind === "html" ? runFromOutputs(data.outputs) : undefined,
    htmlNotes: [],
    drawn: 0,
    flow: h("span", { class: "wb-flow", role: "status" }),
    ranSource: null,
    runOrder: null,
  };
}

/** A cell's head: a table's read-only cell says its part and its state; a user's cell has its name, its
 *  kind and connection, its connections as its SQL names them (`named`), and its buttons. */
function cellHead(nb: Notebook, parts: Parts, named: HTMLElement, draggable: boolean, cell: () => Cell): HTMLElement {
  const number = parts.number;
  const numberLabel = h("span", { class: "wb-number", title: `Cell ${number}: this number never changes. @cell${number} in a comment links here.` }, `#${number}`);
  // A Python cell of the user's is dragged by its number (or its head): it drops its `@cell` link as text.
  if (draggable) numberLabel.draggable = true;
  const runButton = button("Run cell", () => void run(nb, cell()), { icon: "play", iconOnly: true, class: "ghost", title: "Run cell (Ctrl+Enter)" });
  if (parts.role === "transformations") {
    return h("div", { class: "wb-cell-head" }, numberLabel, parts.count, parts.part, h("span", { class: "spacer" }), parts.status, runButton, button("Delete cell", () => removeCell(nb, cell()), { icon: "trash", iconOnly: true, class: "ghost wb-delete-table" }));
  }
  const more = button("More actions", () => cellMenu(nb, cell(), more), { icon: "more", iconOnly: true, class: "ghost" });
  const runTo = button("Run up to here", () => void runUpTo(nb, cell()), { icon: "runTo", class: "ghost wb-run-to", title: "Run every cell from the top to this one" });
  // An HTML cell that shows its design: back to its HTML.
  const editButton = button("Edit HTML", () => edit(nb, cell()), { icon: "edit", iconOnly: true, class: "ghost wb-edit-html", title: "Edit the HTML (Enter)" });
  return h(
    "div",
    { class: "wb-cell-head" },
    numberLabel,
    parts.nameButton,
    parts.count,
    parts.kindPicker,
    parts.connectionPicker,
    named,
    parts.part,
    parts.flow,
    h("span", { class: "spacer" }),
    runTo,
    editButton,
    runButton,
    button("Move up", () => moveCell(nb, cell(), -1), { icon: "up", iconOnly: true, class: "ghost" }),
    button("Move down", () => moveCell(nb, cell(), 1), { icon: "down", iconOnly: true, class: "ghost" }),
    more,
    button("Delete cell", () => removeCell(nb, cell()), { icon: "trash", iconOnly: true, class: "ghost" }),
  );
}

/** The sources a cell's picker offers: a DAX cell only Power BI workspaces' datasets, a SQL cell every
 *  other connection (and DuckDB, with no connection). */
function fillConnections(nb: Notebook, cell: Cell): void {
  const dax = cell.kind === "dax";
  const names = sources(nb, cell.kind);
  const current = cell.connection;
  const what = dax ? "Dataset" : "Connection";
  cell.connectionPicker.setAttribute("aria-label", what);
  cell.connectionPicker.title = what;
  clear(
    cell.connectionPicker,
    // No connection: DuckDB here, a connection's tables named by the connection ([Finance].Sales).
    dax ? (current ? null : h("option", { value: "" }, "")) : h("option", { value: "" }, "DuckDB"),
    ...names.map((n) => h("option", { value: n, selected: n === current }, n)),
    ...(current && !names.includes(current) ? [h("option", { value: current, selected: true }, `${current} (not found)`)] : []),
  );
}

/** A cell's pickers: its kind, and the connection (or dataset) it runs on. */
function wirePickers(nb: Notebook, cell: Cell): void {
  const { connectionPicker, kindPicker } = cell;
  connectionPicker.hidden = !hasSource(cell.kind);
  fillConnections(nb, cell);
  connectionPicker.addEventListener("focus", () => {
    // First use: a workspace whose datasets are not listed yet loads its catalog; the list follows.
    if (cell.kind === "dax") datasetsWanted();
    fillConnections(nb, cell);
  });
  connectionPicker.addEventListener("change", () => {
    cell.connection = connectionPicker.value || null;
    nb.changed();
    connectionsSoon(nb);
    drawNamed(nb, cell);
    cell.editor?.lint();
  });
  drawNamed(nb, cell);
  kindPicker.addEventListener("change", () => {
    setKind(nb, cell, kindPicker.value as CellKind);
    cell.editor?.lint();
  });
}

/** The head drags the cell too (its `@cell` link as text), but not from its buttons and pickers. */
function wireDrag(cell: Cell, head: HTMLElement): void {
  const element = cell.element;
  let pressed: HTMLElement | null = null;
  head.draggable = true;
  head.addEventListener("mousedown", (e) => (pressed = e.target as HTMLElement));
  head.addEventListener("dragstart", (e) => {
    if ((cell.kind !== "code" && !isText(cell.kind)) || (e.target === head && pressed?.closest("button, select, input, a"))) return e.preventDefault();
    e.dataTransfer?.setData("text/plain", `@cell${cell.number}`);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = "copyLink";
    element.classList.add("dragging");
  });
  head.addEventListener("dragend", () => element.classList.remove("dragging"));
}

/** What a cell's element listens for: the selection, right-click, a dropped snippet, its two faces. */
function wireCell(nb: Notebook, cell: Cell): void {
  const { element, editorHost } = cell;
  element.addEventListener("focusin", () => select(nb, cell));
  // Right-click the cell (its head, its output; the editor has its own menu): Lineage.
  element.addEventListener("contextmenu", (e) => {
    const at = e.target as HTMLElement;
    // An error panel, the editor, a box have menus of their own; selected text keeps the browser's.
    if (e.defaultPrevented || at.closest(".monaco-editor, .wb-err, input, textarea, select, iframe") || window.getSelection()?.toString()) return;
    e.preventDefault();
    select(nb, cell);
    const items: MenuItem[] = [];
    if (nb.hooks.lineage) items.push(["lineage", "Lineage", () => nb.hooks.lineage!(cell.number)]);
    showMenu(e.clientX, e.clientY, cell.name ?? `Cell ${cell.number}`, items);
  });
  // A snippet dragged from the blade list: taken before the editor's own drop (which would paste
  // its name), filled by its form, then put where it was dropped.
  element.addEventListener("dragover", (e) => {
    if (!e.dataTransfer?.types.includes(SNIPPET_DRAG)) return;
    e.preventDefault();
    e.stopPropagation();
    element.classList.add("snippet-over");
  }, true);
  element.addEventListener("dragleave", () => element.classList.remove("snippet-over"));
  element.addEventListener("drop", (e) => {
    const snippet = draggedSnippet(e.dataTransfer);
    element.classList.remove("snippet-over");
    if (!snippet) return;
    e.preventDefault();
    e.stopPropagation();
    void dropSnippet(nb, cell, snippet, e.clientX, e.clientY);
  }, true);
  element.addEventListener("dblclick", () => {
    if (cell.kind === "markdown" && element.classList.contains("rendered")) editMarkdown(cell);
  });
  // An HTML cell that shows its design: a click on the cell itself (its
  // head, not a button, and not the design, whose clicks are the design's own) opens its code.
  element.addEventListener("click", (e) => {
    const target = e.target as HTMLElement;
    if (!twoFaced(cell) || !element.classList.contains("rendered")) return;
    if (target.closest(".wb-design, button, select, a, input")) return;
    editHtml(cell);
  });
  // Left: it draws by itself. (Another window in front is not leaving: the HTML stays open.)
  editorHost.addEventListener("focusout", () => {
    setTimeout(() => {
      if (!twoFaced(cell) || element.classList.contains("rendered") || !nb.cells.includes(cell)) return;
      const now = document.activeElement as HTMLElement | null;
      if (!document.hasFocus() || (now && (editorHost.contains(now) || now.closest(".context-view, .monaco-menu, .overflowingContentWidgets")))) return;
      if (sourceOf(cell).trim()) showDesign(cell);
    }, 0);
  });
}

/** An empty editor's faint words: the cell's language, or a new notebook's first Python cell's hint. */
function placeholderOf(nb: Notebook, cell: Cell): string | undefined {
  if (cell.kind === "sql") return "SQL";
  if (cell.kind === "dax") return "DAX";
  if (cell.kind === "html") return "HTML";
  if (cell.kind === "typescript") return "TypeScript";
  if (cell.kind === "tsx") return "TSX: export default function ...";
  // The first Python cell of the user's own (no other with code in it) gets the starting hint.
  const another = nb.cells.some((c) => c !== cell && c.kind === "code" && c.role !== "transformations" && sourceOf(c).trim());
  return cell.kind === "code" && !another ? FIRST_HINT : undefined;
}

/** A cell's editor, once Monaco is there. The editors' intelligence: Jedi with the cells before this one
 *  (or the kernel's names once it runs), the cells after it for the lint (an import here they use is used). */
function mountEditor(nb: Notebook, cell: Cell): void {
  const sql = sqlCompleter(nb.kernel, () => cell.connection, nb.connections);
  const dax = daxCompleter(() => cell.connection);
  const codeOf = (list: Cell[]): string[] => list.filter((c) => c.kind === "code" || c.kind === "sql").map((c) => (c.kind === "sql" ? `${sqlLine(c.connection)}\n${sourceOf(c)}` : sourceOf(c)));
  const docName = (): string => nb.kernel.intel().path ?? "Untitled notebook";
  const intel = pythonIntel(nb.kernel, {
    notebook: true,
    before: () => codeOf(nb.cells.slice(0, Math.max(0, nb.cells.indexOf(cell)))),
    after: () => codeOf(nb.cells.slice(nb.cells.indexOf(cell) + 1)),
    language: () => (cell.kind === "code" && cell.role !== "transformations" ? "python" : cell.kind === "sql" ? "sql" : "other"),
    connection: () => cell.connection,
    document: docName,
    place: () => `cell ${cell.number}`,
  });
  const intelKey = `${Math.random()}`;
  void loadEditors().then((m) => {
    if (nb.disposed || !nb.cells.includes(cell)) return; // deleted (or the notebook closed) before its editor loaded
    cell.editor = m.createCodeEditor(cell.editorHost, {
      pageZoom: true, // the page's code zoom (Ctrl+wheel, Ctrl+= - 0)
      intel: {
        signature: (text, offset) => (cell.kind === "code" ? intel.signature(text, offset) : Promise.resolve(null)),
        hover: (text, offset) => (cell.kind === "code" ? intel.hover(text, offset) : Promise.resolve("")),
        lint: (text) => intel.lint(text),
        onLint: (problems) =>
          showProblems(`${docName()}\u0000${intelKey}`, nb.cells.includes(cell) ? { document: docName(), place: `cell ${cell.number}`, problems, reveal: (line, column) => { select(nb, cell); cell.editor?.reveal(line, column); } } : null),
      },
      language: LANGUAGE[cell.kind],
      value: cell.source,
      theme: nb.theme(),
      grow: true,
      // Ghost text: this cell with the notebook's other code cells (their text only, never outputs).
      inline: inlineSource(() => {
        const coded = (c: Cell): boolean => (c.kind === "code" || c.kind === "sql") && c.role !== "transformations";
        if (!coded(cell)) return null;
        const name = (nb.kernel.intel().path ?? "Untitled notebook.ipynb").split(/[\\/]/).pop() ?? "notebook.ipynb";
        return {
          key: nb.inlineKey,
          name,
          kind: "notebook",
          cells: nb.cells.filter(coded).map((c) => ({ id: String(c.number), text: sourceOf(c), language: c.kind === "sql" ? "sql" : "python" })),
          cell: String(cell.number),
        };
      }),
      readOnly: cell.role === "transformations",
      cellLinks: { first: (n) => (byNumber(nb, n) ? firstLine(sourceOf(byNumber(nb, n)!)) : null), go: (n) => void goTo(nb, n) },
      placeholder: placeholderOf(nb, cell),
      // By the cell's kind as it is now: Python from the kernel, SQL from the connection's catalog,
      // DAX from its dataset's part of the workspace's catalog.
      complete: (text, offset) =>
        cell.kind === "sql" ? sql(text, offset)
        : cell.kind === "dax" ? dax(text, offset)
        : cell.kind === "code" ? intel.complete(text, offset).then((found) => found ?? nb.python(text, offset))
        : Promise.resolve([]),
      help: (text, offset) => (cell.kind === "code" ? nb.kernel.help(text, offset) : Promise.resolve("")),
      sendToAgent: (what, ask) => sendToAgent(codeItem(`cell ${indexOf(nb, cell) + 1} of ${currentDocument()}${what.startLine === what.endLine ? `, line ${what.startLine}` : `, lines ${what.startLine} to ${what.endLine}`}`, what, LANGUAGE[cell.kind]), ask),
      actions: nb.hooks.lineage ? [{ id: "sab.lineage", label: "Lineage", run: () => nb.hooks.lineage!(cell.number) }] : [],
      keys: {
        shiftEnter: () => void run(nb, cell).then(() => next(nb, cell)),
        ctrlEnter: () => void run(nb, cell),
        escape: () => toCommandMode(nb, cell),
        f1: nb.hooks.help,
      },
    });
    cell.editor.onChange((change) => {
      edited(nb);
      drawNamed(nb, cell);
      // The uses line follows the typing, after a short pause (never an undo: that would undo the undo).
      if (!change.undo && !isApp(cell.role)) typedSoon(nb);
      if (cell.role === "transformations") redraw(nb);
      if (cell.kind === "html" || cell.kind === "markdown") drawHtmlState(cell);
    });
    if (nb.hooks.cursor) cell.editor.onCursor(nb.hooks.cursor);
    if (cell.wantsFocus) focusEditor(cell);
  });
}

/** Make a cell from its data and put it at `at` in the notebook: one of the user's, a table's read-only
 *  cell, or a heading's line of the Tables group. */
export function make(nb: Notebook, given: CellData, at: number): Cell {
  const data = asOpened(given);
  const number = data.number && !byNumber(nb, data.number) ? data.number : nb.nextNumber;
  nb.nextNumber = Math.max(nb.nextNumber, number + 1);
  const role = data.role ?? "";
  let self: Cell | null = null;
  const parts = cellParts(nb, data, number, () => cell, () => self);
  const draggable = (data.kind === "code" || isText(data.kind)) && !isApp(role);
  // A DuckDB cell's connections, as its SQL names them ([Finance Captive].Sales): each in its head.
  const named = h("span", { class: "wb-sql-named" });
  const head = cellHead(nb, parts, named, draggable, () => cell);
  const hiddenNote = h("button", { type: "button", class: "link wb-output-hidden", onclick: () => toggleOutput(cell) }, "Show output");
  // The app's own cells (a heading's line, a table's read-only cell) are `wb-tcell`; `wb-cell` is a
  // cell of the user's.
  const element = parts.bar
    ? h("section", { class: `wb-tcell wb-heading role-${role}`, tabindex: -1, role: "listitem" }, parts.bar)
    : h("section", { class: `${role === "transformations" ? "wb-tcell role-transformations" : "wb-cell"} kind-${data.kind}`, tabindex: -1, role: "listitem" }, head, parts.editorHost, parts.view, parts.design?.element ?? null, parts.area.element, hiddenNote);
  const cell: Cell = { ...parts, element };
  self = cell;
  drawName(cell);
  // A table's cell that came with the file (or a reload) has not run since.
  if (role === "transformations" && cell.table && nb.building && nb.hooks.opened && !nb.records.has(cell.table)) {
    nb.records.set(cell.table, { code: null, at: null, opened: true });
    nb.cameWithFile.add(cell.table);
  }
  if (parts.bar) element.addEventListener("focusin", () => select(nb, cell));
  else {
    nb.namedHosts.set(cell, named);
    wirePickers(nb, cell);
    if (draggable) wireDrag(cell, head);
    wireCell(nb, cell);
    if (role === "transformations") cell.kindPicker.hidden = true;
    mountEditor(nb, cell);
    if (ROUTED.includes(cell.kind)) knowTypes(cell.kind);
    if (cell.kind === "markdown" && cell.source.trim()) showMarkdown(nb, cell);
    else if (cell.kind === "html") {
      if (cell.source.trim()) showDesign(cell);
    } else cell.area.set(data.outputs);
  }
  nb.cells.splice(at, 0, cell);
  nb.list.insertBefore(element, nb.list.children[at] ?? null);
  relabel(nb);
  return cell;
}
