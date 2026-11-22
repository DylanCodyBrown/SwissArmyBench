/**
 * workbenchExplorer.ts: the Workbench's Data Explorer pane (the owner, 2026-11-17: "perhaps the data pane
 * can move to its own pane called Data Explorer"), on the left like VS Code's Explorer. It replaced the Data
 * panel: its tables and blade variables are Explorer results now (its Streamlit cells and Starters went with
 * app notebooks, 2026-11-21). [WIRE]
 *
 *   [PANE]     beside every document (notebooks, scripts, a landing page),
 *              off until opened: the status bar's Data Explorer, Ctrl+Shift+E; open or closed and its width
 *              remembered per window (this window's session storage). Resizable by its right edge
 *   [SEARCH]   dataExplorer.ts: one search over everything that holds data
 *   [ADD]      its head's "+ Table" (Open file…, a connection's tables, the catalog's search, Add
 *              connection…) and "+ Blade" (the saved blades and connections) open the flyout beside it
 *              (catalogRail.ts)
 *   [FILES]    at the bottom, folded: a project's files. Hidden until a project exists (setFiles)
 *   [POP OUT]  the Data page (dataPage.ts) in a window of its own, with its search; the pane closes here
 *              (Ctrl+Shift+E opens it again); the Data page is the one place to browse tables
 */
import { kindOfPath } from "./kindColours";
import { button, dragResize, h, icon } from "./dom";
import { type Explorer, type ExplorerHost, type ExplorerState, mountExplorer } from "./dataExplorer";

/** A project's file, as the files section lists it. */
export interface ProjectFile {
  path: string;
  icon?: string;
  /** Its kind's word: the tooltip. */
  word?: string;
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

export interface ExplorerPaneHost extends ExplorerHost {
  /** "+ Table": what can bring a table in. */
  addTable: (anchor: HTMLElement) => void;
  /** Opened or closed (the page redraws what depends on it). */
  toggled: (open: boolean) => void;
  /** Pop out pressed. */
  popOut: () => void;
}

export interface ExplorerPane {
  element: HTMLElement;
  explorer: Explorer;
  /** Open or close it (no argument: the other way); true when open. */
  toggle: (open?: boolean) => boolean;
  isOpen: () => boolean;
  /** A project's files (null: no project, and the section is hidden). */
  setFiles: (files: ProjectFiles | null) => void;
  /** Popped out into its own window (the pane stays closed here), or back. */
  setPopped: (popped: boolean) => void;
  popped: () => boolean;
  /** The hosts the catalog and the blades are mounted in (catalogRail.ts). */
  bladesHost: HTMLElement;
  catalogHost: HTMLElement;
  /** Show the flyout with the catalog or the blades (null: close it). */
  flyout: (which: "catalog" | "blades" | null) => void;
  flyoutShown: () => "catalog" | "blades" | null;
}

const OPEN_KEY = "workbench-explorer-open";
const WIDTH_KEY = "workbench-explorer-width";
const POPPED_KEY = "workbench-explorer-popped";
const STATE_KEY = "workbench-explorer-state";
const FILES_KEY = "workbench-files-folded";
const MIN_WIDTH = 220;
const MAX_WIDTH = 640;

/** This window's own (session storage: per window, kept through a reload). */
function recall(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function keep(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    /* storage blocked: it lasts until the window closes */
  }
}

export function mountExplorerPane(host: ExplorerPaneHost): ExplorerPane {
  let open = recall(OPEN_KEY) === "1";
  let popped = recall(POPPED_KEY) === "1";
  let filesFolded = (() => {
    try {
      return localStorage.getItem(FILES_KEY) === "1";
    } catch {
      return false;
    }
  })();
  let files: ProjectFiles | null = null;
  let width = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Number(recall(WIDTH_KEY)) || 300));

  const explorer = mountExplorer({
    ...host,
    changed: (state: ExplorerState) => {
      keep(STATE_KEY, JSON.stringify(state));
      host.changed?.(state);
    },
  });
  try {
    const kept = JSON.parse(recall(STATE_KEY) ?? "null") as ExplorerState | null;
    if (kept) explorer.setState(kept);
  } catch {
    /* nothing kept */
  }

  const addTable = button("Table", (e) => host.addTable(e.currentTarget as HTMLElement), { icon: "plus", class: "ghost wb-data-add", title: "Add a table" });
  addTable.setAttribute("aria-label", "Add a table");
  addTable.setAttribute("aria-haspopup", "menu");
  const addBlade = button("Blade", () => flyout(shown === "blades" ? null : "blades"), { icon: "plus", class: "ghost wb-data-add", title: "Blades and connections" });
  addBlade.setAttribute("aria-label", "Add a blade");
  const popOut = button("Pop out", () => host.popOut(), { icon: "popout", iconOnly: true, class: "ghost", title: "Open the Data page in a window of its own" });
  const closeButton = button("Close the Data Explorer", () => toggle(false), { icon: "close", iconOnly: true, class: "ghost", title: "Close (Ctrl+Shift+E)" });

  const filesHead = h("button", { type: "button", class: "wb-files-head", "aria-expanded": String(!filesFolded) });
  const fileList = h("ul", { class: "wb-files-list" });
  const filesSection = h("section", { class: "wb-files", "aria-label": "Project files", hidden: true }, filesHead, fileList);
  filesHead.addEventListener("click", () => {
    filesFolded = !filesFolded;
    try {
      localStorage.setItem(FILES_KEY, filesFolded ? "1" : "0");
    } catch {
      /* storage blocked */
    }
    drawFiles();
  });

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

  const grip = h("div", { class: "wb-explorer-grip", role: "separator", "aria-orientation": "vertical", "aria-label": "Resize the Data Explorer", tabindex: "0" });
  const element = h(
    "aside",
    { class: "wb-explorer wb-data", "aria-label": "Data Explorer" },
    h("div", { class: "wb-data-head" }, h("h2", {}, icon("zoom"), h("span", { class: "wb-data-title" }, "Data Explorer")), h("span", { class: "spacer" }), addTable, addBlade, popOut, closeButton),
    h("div", { class: "wb-explorer-body" }, explorer.element, filesSection),
    flyoutEl,
    grip,
  );

  // ----- resizing by the right edge (the arrows too)
  const setWidth = (w: number): void => {
    width = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(w)));
    element.style.width = `${width}px`;
    keep(WIDTH_KEY, String(width));
  };
  let startW = width;
  dragResize(grip, {
    start: () => void (startW = width),
    move: (dx) => setWidth(startW + dx),
    end: () => void window.dispatchEvent(new Event("resize")), // the editors measure again
  });
  grip.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      setWidth(width + (e.key === "ArrowRight" ? 16 : -16));
    }
  });

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
          { class: `wb-file${f.derived ? " derived" : ""}${kindOfPath(f.path) ? ` km-${kindOfPath(f.path)}` : ""}` },
          f.open
            ? h("button", { type: "button", class: "link wb-file-open", title: f.word ?? "", "data-icon": f.icon ?? "", onclick: () => f.open?.() }, f.icon ? icon(f.icon) : null, h("span", {}, f.path))
            : h("span", { class: "wb-file-name" }, f.icon ? icon(f.icon) : null, h("span", {}, f.path)),
          f.note ? h("span", { class: "wb-file-note" }, f.note) : null,
        ),
      ),
    );
  }

  function draw(): void {
    element.hidden = !open || popped;
    element.style.width = `${width}px`;
    if (element.hidden) flyout(null);
  }

  function toggle(next?: boolean): boolean {
    open = next ?? !open;
    keep(OPEN_KEY, open ? "1" : "0");
    draw();
    host.toggled(open && !popped);
    if (open && !popped) explorer.focus();
    return open && !popped;
  }

  draw();
  drawFiles();
  flyout(null);

  return {
    element,
    explorer,
    toggle,
    isOpen: () => open && !popped,
    setFiles: (list) => {
      files = list;
      drawFiles();
    },
    setPopped: (on) => {
      popped = on;
      keep(POPPED_KEY, on ? "1" : "0");
      draw();
      host.toggled(open && !popped);
    },
    popped: () => popped,
    bladesHost,
    catalogHost,
    flyout,
    flyoutShown: () => shown,
  };
}
