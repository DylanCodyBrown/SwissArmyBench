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
 *   [FILES]      at the bottom, folded: a project's files. Hidden until a project exists (setFiles)
 *   [COLLAPSE]   the arrow (or Ctrl+B) folds the panel to a narrow bar; remembered in this browser
 */
import type { BladeSummary } from "./bladeEditor";
import { DROP_TYPE } from "./catalogRail";
import { button, h, icon } from "./dom";

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
  /** A variable's value as the focused kernel holds it ("" when it does not). */
  valueOf(variable: string): string;
  /** Folded or opened (the page redraws what depends on it). */
  toggled(collapsed: boolean): void;
}

export interface DataPanel {
  element: HTMLElement;
  setTables(tables: DataTable[]): void;
  setBlades(blades: BladeSummary[]): void;
  /** A project's files (null: no project, and the section is hidden). */
  setFiles(files: ProjectFiles | null): void;
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

  const fold = button("Collapse the Data panel", () => toggle(), { icon: "collapse", iconOnly: true, class: "ghost wb-data-fold", title: "Collapse the Data panel (Ctrl+B)" });
  const body = h(
    "div",
    { class: "wb-data-body" },
    h("section", { class: "wb-data-section", "aria-labelledby": "wb-data-tables" }, h("h3", {}, h("span", { id: "wb-data-tables" }, "Tables"), addTable), tableList),
    // Named apart from the Variables pane (what the kernel holds): these are the blades' values.
    h("section", { class: "wb-data-section", "aria-label": "Blade variables" }, h("h3", {}, h("span", {}, "Variables"), addBlade), bladeList),
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
        const value = b.variable ? host.valueOf(b.variable) : "";
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
            h("span", { class: "wb-data-name" }, h("span", { class: "wb-data-label" }, name), value ? h("span", { class: "wb-data-count wb-data-value" }, value) : null),
            h("span", { class: "wb-data-meta" }, icon("bolt"), h("span", {}, b.description || b.name)),
          ),
        );
      }),
    );
    if (!blades.length) bladeList.append(h("li", { class: "wb-data-empty" }, "No blades"));
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
    toggle,
    collapsed: () => folded,
    bladesHost,
    catalogHost,
    flyout,
    flyoutShown: () => shown,
  };
}
