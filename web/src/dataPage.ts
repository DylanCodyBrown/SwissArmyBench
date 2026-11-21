/**
 * dataPage.ts: the Data page, on the rail after Variables (the owner, 2026-11-17: "yea I said a long time
 * ago we needed a standalone DATA rail icon and page" / "we dont even need catalog if its just tables"): the
 * one place to browse and find tables. [SHARED]
 *
 *   [PAGE]    a page of the rail's over any page (areaPage.ts), in the address as open=data; a search
 *             can ride along (q, kinds, connection, column: the Workbench pane's Pop out, Ctrl+K's Open
 *             the Data page)
 *   [WHAT]    the Data Explorer (dataExplorer.ts) on its fourth host, full page: the search and its chips
 *             at the top; with nothing typed, the tree of every connection and its tables, the open
 *             tables, Structures, the APIs' tables and the blades whose result is a table; typed, the tree
 *             narrowed; a table's detail beside it (dataBrowse.ts)
 *   [INSERT]  into the Workbench window's focused cell, shown only while one has a document in front (its
 *             workbench_window command explorer.target); a drag into a cell there works from here too
 *   [GRIDS]   Open as grid: the home page shows it (here, or the home window)
 *
 * ROUTING: GET /explorer/browse, /explorer/search, /explorer/table
 *          POST /workbench/window {command: "explorer.insert" | "explorer.target"}
 */
import { api } from "./api";
import { openAreaPage, type PageElement } from "./areaPage";
import { EMPTY_STATE, type Explorer, type ExplorerState, mountExplorer } from "./dataExplorer";
import { dismissDialog, HOME_WINDOW, layerOpened, registerLayer, setOverTitle, watchLayerDialog } from "./nav";
import { openVariables } from "./variablesPage";
import { errorHere } from "./errorNote";

/** The page's name, in one place: the rail, the title. */
// Catalog (the owner, 2026-11-21: "rename Data Catalog to just catalog"); its address stays open=data.
export const DATA = "Catalog";
/** The address's words a search rides in on. */
const KEYS = ["q", "kinds", "connection", "column"];

let shownPage: PageElement | null = null;
let shown: Explorer | null = null;
/** The home page shows a grid itself (main.ts); elsewhere the home window does. */
let gridShower: ((grid: string) => void) | null = null;

registerLayer("data", {
  isOpen: () => Boolean(shownPage?.open),
  open: (url) => drawPage(stateOf(url)),
  show: () => undefined,
  dismiss: () => {
    if (shownPage) dismissDialog(shownPage);
  },
});

/** The home page's way to show a grid (its tabs): Open as grid lands there. */
export function setGridShower(show: (grid: string) => void): void {
  gridShower = show;
}

function stateOf(url: URL): ExplorerState {
  const p = url.searchParams;
  const kinds = (p.get("kinds") ?? "").split(",").filter(Boolean);
  return { ...EMPTY_STATE, text: p.get("q") ?? "", kinds, connection: p.get("connection") ?? "", column: p.get("column") ?? "" };
}

/** The Data page, opened by the user (the rail's icon, Ctrl+K's Open the Data page) with a search or none. */
export function openData(state: ExplorerState = EMPTY_STATE): void {
  if (shownPage?.open && shown) {
    shown.setState(state);
    return;
  }
  const params: Record<string, string | null> = { q: state.text || null, kinds: state.kinds.join(",") || null, connection: state.connection || null, column: state.column || null };
  layerOpened("data", params);
  drawPage(state);
}

function drawPage(state: ExplorerState): void {
  const { element, body } = openAreaPage("data", DATA);
  shownPage = element;
  body.classList.add("data-page");
  setOverTitle(DATA);
  let target: { document: string | null; cell: number | null } = { document: null, cell: null };
  const explorer = mountExplorer({
    browse: true,
    insert: async (r) => {
      const got = await api<{ result: { document: string; cell: number | null } }>("/workbench/window", "POST", { command: "explorer.insert", args: { insert: r.insert, name: r.name } });
      return got.result.cell ? `cell ${got.result.cell} of ${got.result.document}` : got.result.document;
    },
    canInsert: () => Boolean(target.document),
    target: () => (target.document ? (target.cell ? `cell ${target.cell} of ${target.document}` : target.document) : "the Workbench"),
    showGrid: (grid) => {
      if (gridShower) {
        element.close();
        gridShower(grid);
        return;
      }
      if (!window.open(`/g/${encodeURIComponent(grid)}`, HOME_WINDOW)) errorHere("The browser blocked the grid's window. Allow pop-ups for this address.");
    },
    openVariable: () => openVariables(),
  });
  shown = explorer;
  body.append(explorer.element);
  if (state.text || state.kinds.length || state.connection || state.column) explorer.setState(state);

  /** The Workbench window's front document (Insert shows only while there is one). */
  const readTarget = async (): Promise<void> => {
    const before = target.document;
    try {
      const got = await api<{ result: { document: string | null; cell: number | null } }>("/workbench/window", "POST", { command: "explorer.target", args: {} });
      target = got.result ?? { document: null, cell: null };
    } catch {
      target = { document: null, cell: null };
    }
    if (target.document !== before) explorer.refresh();
  };
  const onFocus = (): void => void readTarget();
  window.addEventListener("focus", onFocus);
  void readTarget();
  watchLayerDialog(element, "data", KEYS, () => {
    window.removeEventListener("focus", onFocus);
    if (shownPage === element) {
      shownPage = null;
      shown = null;
    }
  });
  explorer.focus();
}
