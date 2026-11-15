/**
 * workbenchData.ts: the Workbench's Data panel, on the left (the redesign of 2026-11-15). [WIRE]
 *
 *   [TABLES]     the tables open in the grid: each one's rows, where it came from (a file or a
 *                connection) and its steps. A click goes to its read-only cell in the focused document;
 *                a drag gives its name to code. "+ Table": Open file…, a connection's tables, the
 *                catalog's search, Add connection… (the page's menu)
 *   [VARIABLES]  the blades that are not connections (a value, a secret, an analysis): a click opens one,
 *                a drag gives its sag.blade line. "+ Blade": the saved blades and connections, New blade
 *   [FLYOUT]     what "+ Table" and "+ Blade" open beside the panel: the catalog (a connection's tables,
 *                search) or the saved blades, the side bar the Workbench had before (catalogRail.ts)
 *   [STREAMLIT]  every Python cell that calls Streamlit (the owner, 2026-11-15), from the open notebooks
 *                and scripts and the project's files, grouped by document, each by its name (else its
 *                first comment line), its @cell and what it makes and reads. A drag places its link on
 *                a canvas (as dragging the cell itself does); a click goes to the cell. A cell already
 *                on the canvas page in front has a mark. It folds like the files
 *   [FILES]      at the bottom, folded: a project's files. Hidden until a project exists (setFiles)
 *   [COLLAPSE]   the arrow (or Ctrl+B) folds the panel to a narrow bar; remembered in this browser
 */
import type { BladeSummary } from "./bladeEditor";
import { DROP_TYPE } from "./catalogRail";
import { button, h, icon } from "./dom";
import { CELL_DRAG, type PaneDocument, partsOf } from "./workbenchStreamlit";

export interface DataTable {
  name: string;
  /** Its name as a Python variable. */
  variable: string;
  rows: number;
  /** The file's or connection's name ("" when not known). */
  source: string;
  /** python, file, dropped, paste, connection, query or unknown. */
  origin: string;
  steps: number;
}

/** A project's file, as the files section lists it. */
export interface ProjectFile {
  path: string;
  icon?: string;
  /** Made from another file (data.py from data.ipynb): muted, set in. */
  derived?: boolean;
  /** A short word beside it ("Out of date"), shown only when it needs action. */
  note?: string;
  open?: () => void;
}

export interface ProjectFiles {
  /** The project's folder, as shown: "sales/". */
  root: string;
  files: ProjectFile[];
}

export interface DataPanelHost {
  /** A table's click: its read-only cell in the focused document. */
  goToTable(name: string): void;
  /** "+ Table": what can bring a table in. */
  addTable(anchor: HTMLElement): void;
  openBlade(name: string): void;
  /** Folded or opened (the page redraws what depends on it). */
  toggled(collapsed: boolean): void;
  /** A Streamlit cells pane entry's click: the cell, its document opened when it is not. */
  goToCell(document: string | null, title: string, cell: number): void;
}

export interface DataPanel {
  element: HTMLElement;
  setTables(tables: DataTable[]): void;
  setBlades(blades: BladeSummary[]): void;
  /** A project's files (null: no project, and the section is hidden). */
  setFiles(files: ProjectFiles | null): void;
  /** The Streamlit cells pane: its documents and cells, and the links on the canvas page in front
   *  ("path#cell"), which get a mark. */
  setStreamlitCells(documents: PaneDocument[], placed: Set<string>): void;
  /** Fold or open the panel (no argument: the other way); true when folded. */
  toggle(collapsed?: boolean): boolean;
  collapsed(): boolean;
  /** The hosts the catalog and the blades are mounted in (catalogRail.ts). */
  bladesHost: HTMLElement;
  catalogHost: HTMLElement;
  /** Show the flyout with the catalog or the blades (null: close it). */
  flyout(which: "catalog" | "blades" | null): void;
  flyoutShown(): "catalog" | "blades" | null;
}

const COLLAPSED_KEY = "workbench-data-collapsed";
const FILES_KEY = "workbench-files-folded";
const STREAMLIT_KEY = "workbench-streamlit-folded";

function recall(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function keep(key: string, on: boolean): void {
  try {
    localStorage.setItem(key, on ? "1" : "0");
  } catch {
    /* storage blocked: it lasts until the window closes */
  }
}

const plural = (n: number, word: string): string => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;

const SOURCE_ICONS: Record<string, string> = { file: "file", dropped: "file", connection: "sql", query: "sql", python: "code", paste: "copy" };

export function mountDataPanel(host: DataPanelHost): DataPanel {
  let folded = recall(COLLAPSED_KEY);
  let filesFolded = recall(FILES_KEY);
  let tables: DataTable[] = [];
  let blades: BladeSummary[] = [];
  let files: ProjectFiles | null = null;
  let streamlitFolded = recall(STREAMLIT_KEY);
  let paneDocs: PaneDocument[] = [];
  let placed = new Set<string>();

  const tableList = h("ul", { class: "wb-data-list", "aria-label": "Tables" });
  const bladeList = h("ul", { class: "wb-data-list", "aria-label": "Blade variables" });
  const addTable = button("Table", (e) => host.addTable(e.currentTarget as HTMLElement), { icon: "plus", class: "ghost wb-data-add", title: "Add a table" });
  addTable.setAttribute("aria-label", "Add a table");
  addTable.setAttribute("aria-haspopup", "menu");
  const addBlade = button("Blade", () => flyout(shown === "blades" ? null : "blades"), { icon: "plus", class: "ghost wb-data-add", title: "Blades and connections" });
  addBlade.setAttribute("aria-label", "Add a blade");
  const filesHead = h("button", { type: "button", class: "wb-files-head", "aria-expanded": String(!filesFolded) });
  const fileList = h("ul", { class: "wb-files-list" });
  const filesSection = h("section", { class: "wb-files", "aria-label": "Project files", hidden: true }, filesHead, fileList);
  filesHead.addEventListener("click", () => {
    filesFolded = !filesFolded;
    keep(FILES_KEY, filesFolded);
    drawFiles();
  });
  const streamlitHead = h("button", { type: "button", class: "wb-data-fold-head", id: "wb-data-streamlit", "aria-expanded": String(!streamlitFolded) });
  const streamlitList = h("div", { class: "wb-st-list", "aria-labelledby": "wb-data-streamlit" });
  const streamlitSection = h("section", { class: "wb-data-section wb-st", "aria-label": "Streamlit cells" }, h("h3", {}, streamlitHead), streamlitList);
  streamlitHead.addEventListener("click", () => {
    streamlitFolded = !streamlitFolded;
    keep(STREAMLIT_KEY, streamlitFolded);
    drawStreamlit();
  });

  const fold = button("Collapse the Data panel", () => toggle(), { icon: "collapse", iconOnly: true, class: "ghost wb-data-fold", title: "Collapse the Data panel (Ctrl+B)" });
  const body = h(
    "div",
    { class: "wb-data-body" },
    h("section", { class: "wb-data-section", "aria-labelledby": "wb-data-tables" }, h("h3", {}, h("span", { id: "wb-data-tables" }, "Tables"), addTable), tableList),
    // Named apart from the Variables pane (what the kernel holds): these are the blades' values.
    h("section", { class: "wb-data-section", "aria-label": "Blade variables" }, h("h3", {}, h("span", {}, "Variables"), addBlade), bladeList),
    streamlitSection,
    filesSection,
  );

  // ----- the flyout: the catalog (a connection's tables, search) or the saved blades
  const bladesHost = h("section", { class: "rail-section", id: "blades", "aria-labelledby": "blades-title" });
  const catalogHost = h("section", { class: "rail-section grow", id: "catalog", "aria-labelledby": "catalog-title" });
  const flyoutTitle = h("h2", {}, "");
  const flyoutEl = h(
    "aside",
    { class: "wb-flyout cat-rail", hidden: true, "aria-label": "Tables and blades" },
    h("div", { class: "wb-flyout-head" }, flyoutTitle, button("Close", () => flyout(null), { icon: "close", iconOnly: true, class: "ghost", title: "Close (Escape)" })),
    bladesHost,
    catalogHost,
  );
  let shown: "catalog" | "blades" | null = null;
  const element = h(
    "aside",
    { class: "wb-data", "aria-label": "Data" },
    h("div", { class: "wb-data-head" }, h("h2", {}, icon("sql"), h("span", { class: "wb-data-title" }, "Data")), fold),
    body,
    flyoutEl,
  );

  function flyout(which: "catalog" | "blades" | null): void {
    shown = which;
    flyoutEl.hidden = which === null;
    bladesHost.hidden = which !== "blades";
    catalogHost.hidden = which !== "catalog";
    flyoutTitle.textContent = which === "blades" ? "Blades" : "Tables";
    addBlade.setAttribute("aria-expanded", String(which === "blades"));
    if (which === "catalog") (catalogHost.querySelector("input[type=search]") as HTMLElement | null)?.focus();
  }
  // Escape, or a click outside (a dialog, a menu or the file chooser it opened aside), closes it.
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && shown && flyoutEl.contains(document.activeElement)) {
      const was = shown;
      flyout(null);
      (was === "blades" ? addBlade : addTable).focus();
    }
  });
  document.addEventListener("mousedown", (e) => {
    const at = e.target as HTMLElement | null;
    if (!shown || !at?.closest || flyoutEl.contains(at) || at.closest(".menu, dialog, .file-chooser, .toasts, .wb-palette-shade, .wb-data-add")) return;
    flyout(null);
  });

  // ----- tables
  function drawTables(): void {
    tableList.replaceChildren(
      ...tables.map((t) => {
        const item = h(
          "li",
          { class: "wb-data-item" },
          h(
            "button",
            {
              type: "button",
              class: "wb-data-card",
              title: `Go to ${t.name}'s cell`,
              draggable: "true",
              onclick: () => host.goToTable(t.name),
              ondragstart: (event: DragEvent) => {
                event.dataTransfer?.setData("text/plain", t.variable);
                event.dataTransfer?.setData(DROP_TYPE, JSON.stringify({ code: t.variable, imports: [] }));
              },
            },
            h("span", { class: "wb-data-name" }, h("span", { class: "wb-data-label" }, t.name), h("span", { class: "wb-data-count" }, plural(t.rows, "row"))),
            h("span", { class: "wb-data-meta" }, icon(SOURCE_ICONS[t.origin] ?? "rows"), h("span", {}, [t.source, t.steps ? plural(t.steps, "step") : ""].filter(Boolean).join(" · "))),
          ),
        );
        return item;
      }),
    );
    if (!tables.length) tableList.append(h("li", { class: "wb-data-empty" }, "No tables"));
  }

  // ----- variables (blades)
  function drawBlades(): void {
    bladeList.replaceChildren(
      ...blades.map((b) => {
        const name = b.variable ?? b.name;
        const line = b.kind === "vault" || b.kind === "secret" || !b.variable ? `sag.blade(${JSON.stringify(b.name)})` : `${b.variable} = sag.blade(${JSON.stringify(b.name)})`;
        return h(
          "li",
          { class: "wb-data-item" },
          h(
            "button",
            {
              type: "button",
              class: "wb-data-card",
              title: `Open ${b.name}`,
              draggable: "true",
              onclick: () => host.openBlade(b.name),
              ondragstart: (event: DragEvent) => {
                event.dataTransfer?.setData("text/plain", line);
                event.dataTransfer?.setData(DROP_TYPE, JSON.stringify({ code: line, imports: ["import swissarmygrid as sag"] }));
              },
            },
            h("span", { class: "wb-data-name" }, h("span", { class: "wb-data-label" }, name)),
            h("span", { class: "wb-data-meta" }, icon("bolt"), h("span", {}, b.description || b.name)),
          ),
        );
      }),
    );
    if (!blades.length) bladeList.append(h("li", { class: "wb-data-empty" }, "No blades"));
  }

  // ----- the Streamlit cells pane
  function drawStreamlit(): void {
    const count = paneDocs.reduce((n, d) => n + d.cells.length, 0);
    streamlitHead.setAttribute("aria-expanded", String(!streamlitFolded));
    streamlitHead.replaceChildren(icon(streamlitFolded ? "expand" : "down"), h("span", {}, "Streamlit cells"), ...(count ? [h("span", { class: "wb-data-count" }, String(count))] : []));
    streamlitList.hidden = streamlitFolded;
    if (streamlitFolded) return;
    streamlitList.replaceChildren(
      ...paneDocs.map((d) =>
        h(
          "div",
          { class: "wb-st-doc" },
          h("div", { class: "wb-st-doc-name", title: d.document ?? d.title }, d.title),
          h(
            "ul",
            { class: "wb-data-list", "aria-label": d.title },
            ...d.cells.map((c) => {
              const on = d.document !== null && placed.has(`${d.document}#${c.cell}`);
              const parts = partsOf(c);
              return h(
                "li",
                { class: "wb-data-item" },
                h(
                  "button",
                  {
                    type: "button",
                    class: `wb-data-card wb-st-cell${on ? " placed" : ""}${c.named ? " named" : ""}`,
                    title: `Go to ${c.where}`,
                    draggable: "true",
                    dataset: { document: d.document ?? "", cell: String(c.cell) },
                    onclick: () => host.goToCell(d.document, d.title, c.cell),
                    ondragstart: (event: DragEvent) => {
                      // The same link a cell's own drag carries: a canvas places it.
                      event.dataTransfer?.setData(CELL_DRAG, JSON.stringify({ document: d.document, cell: c.cell, title: d.title }));
                      event.dataTransfer?.setData("text/plain", `@cell${c.cell}`);
                      if (event.dataTransfer) event.dataTransfer.effectAllowed = "copyLink";
                    },
                  },
                  h("span", { class: "wb-data-name" }, h("span", { class: "wb-data-label" }, c.name), on ? h("span", { class: "wb-st-placed", title: "On the canvas page in front", "aria-label": "On the canvas page in front" }, icon("check")) : null),
                  h("span", { class: "wb-data-meta" }, h("span", { class: "wb-st-where" }, `@cell${c.cell}`), parts ? h("span", {}, parts) : null),
                ),
              );
            }),
          ),
        ),
      ),
    );
    if (!paneDocs.length) streamlitList.append(h("p", { class: "wb-data-empty" }, "No cells call Streamlit"));
  }

  // ----- a project's files
  function drawFiles(): void {
    filesSection.hidden = !files;
    if (!files) return;
    filesHead.setAttribute("aria-expanded", String(!filesFolded));
    filesHead.replaceChildren(icon(filesFolded ? "expand" : "down"), h("span", {}, files.root));
    fileList.hidden = filesFolded;
    fileList.replaceChildren(
      ...files.files.map((f) =>
        h(
          "li",
          { class: `wb-file${f.derived ? " derived" : ""}` },
          f.open
            ? h("button", { type: "button", class: "link wb-file-open", onclick: () => f.open?.() }, f.icon ? icon(f.icon) : null, h("span", {}, f.path))
            : h("span", { class: "wb-file-name" }, f.icon ? icon(f.icon) : null, h("span", {}, f.path)),
          f.note ? h("span", { class: "wb-file-note" }, f.note) : null,
        ),
      ),
    );
  }

  function toggle(collapsed?: boolean): boolean {
    folded = collapsed ?? !folded;
    keep(COLLAPSED_KEY, folded);
    draw();
    host.toggled(folded);
    return folded;
  }

  function draw(): void {
    element.classList.toggle("collapsed", folded);
    body.hidden = folded;
    fold.replaceChildren(icon(folded ? "expand" : "collapse"));
    const label = folded ? "Expand the Data panel" : "Collapse the Data panel";
    fold.setAttribute("aria-label", label);
    fold.setAttribute("aria-expanded", String(!folded));
    fold.title = `${label} (Ctrl+B)`;
  }

  draw();
  drawTables();
  drawBlades();
  drawStreamlit();
  drawFiles();
  flyout(null);

  return {
    element,
    setTables: (list) => {
      tables = list;
      drawTables();
    },
    setBlades: (list) => {
      blades = list;
      drawBlades();
    },
    setFiles: (list) => {
      files = list;
      drawFiles();
    },
    setStreamlitCells: (documents, onPage) => {
      paneDocs = documents;
      placed = onPage;
      drawStreamlit();
    },
    toggle,
    collapsed: () => folded,
    bladesHost,
    catalogHost,
    flyout,
    flyoutShown: () => shown,
  };
}
