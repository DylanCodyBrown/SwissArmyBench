/**
 * openMenu.ts: the Tables list, behind the ≡ button beside "+" in the tab strip. [WIRE + EXPORT]
 *
 * One list of every table the app can show (the owner's decision 9), in three sections:
 *
 *   Open tables      the tables that have a tab, with their size
 *   Closed tables    tables still in memory whose tabs were closed: Open puts the original back as a
 *                    tab (the same table, not a copy)
 *   Python sessions  the tables in your running Python sessions. A session whose watcher is on
 *                    (swissarmygrid imported in a notebook, or sag.watch() in a script) tells the
 *                    server which tables it holds: names and sizes, never rows. Open asks that
 *                    session to push the table, and from then on the table follows its variable.
 *                    Reload sends it again, for changes made in place that the watcher cannot see.
 *
 * The line under the title is the data budget (the status bar's meter shows only near the limit,
 * and opens this list).
 *
 * ROUTING: [≡ BUTTON]      beside the "+" in the tab bar -> showTables()
 *          [TABLES]        -> read-only, derived from GET /datasets (redrawn when tabs or tables change)
 *          [OPEN]          a closed table -> POST /grids {dataset}: a grid on the original table
 *          [REMOVE]        -> DELETE /datasets/{name} (asks first: its tabs close, nothing is saved)
 *          [SESSION]       -> read-only, derived from GET /processes (redrawn on processes_changed)
 *          [OPEN / RELOAD] -> askToOpen(session, table)      POST /processes/{id}/open
 *          [OPEN ALL]      -> askToOpen() for each table not open yet
 *          [ERROR TOAST]   process_error notice -> the table that did not open, and why
 */
import { api, onNotice, type Budget, type Notice } from "./api";
import { button, closeDialogs, formatCount, h, openDialog, toast } from "./dom";

interface Dataset {
  name: string;
  rows: number;
  size: string;
  grids: string[];
}

interface TableEntry {
  name: string;
  kind: string;
  rows: number | null;
  columns: number | null;
  open: boolean;
}

interface Session {
  id: string;
  label: string;
  pid: number;
  tables: TableEntry[];
}

const KIND_LABELS: Record<string, string> = {
  dataframe: "DataFrame",
  polars: "Polars",
  arrow: "Arrow",
  relation: "DuckDB relation",
  table: "DuckDB table",
};

/** Redraws the open dialog; null while no dialog is open. */
let redraw: (() => void) | null = null;

/** Listen for the server's notices about sessions. Called once, by the workspace page. */
export function mountOpenMenu(): void {
  onNotice((notice: Notice) => {
    if (["processes_changed", "grid_shown", "grid_closed", "dataset_closed", "dataset_updated", "dataset_renamed"].includes(notice.type)) redraw?.();
    if (notice.type === "process_error") {
      toast(`${notice.name ?? "A table"} did not open from ${notice.label || "Python"}: ${notice.message ?? "no reason given"}`, "error");
    }
  });
}

/** The button beside the "+": opens the list. */
export function openMenuButton(): HTMLButtonElement {
  return button("Tables", () => showTables(), {
    icon: "rows",
    iconOnly: true,
    class: "ghost tab-new",
  });
}

async function askToOpen(session: Session, table: TableEntry, pressed?: HTMLButtonElement): Promise<void> {
  if (pressed) {
    pressed.disabled = true;
    // A Reload of a table that is already open changes nothing the list shows, so give the button back.
    setTimeout(() => { pressed.disabled = false; }, 2000);
  }
  try {
    await api(`/processes/${encodeURIComponent(session.id)}/open`, "POST", { name: table.name });
  } catch (e) {
    toast(`Could not ask ${session.label} for ${table.name}: ${(e as Error).message}`, "error");
    if (pressed) pressed.disabled = false;
  }
}

function sizeOf(table: TableEntry): string {
  const rows = table.rows === null ? "?" : formatCount(table.rows);
  const columns = table.columns === null ? "?" : formatCount(table.columns);
  return `${rows} × ${columns}`;
}

function tableRow(session: Session, table: TableEntry): HTMLElement {
  return h(
    "tr",
    {},
    h("td", {}, h("strong", {}, table.name)),
    h("td", {}, KIND_LABELS[table.kind] ?? table.kind),
    h("td", { class: "num", title: "rows × columns" }, sizeOf(table)),
    h("td", {}, table.open ? h("span", { class: "open-state" }, "open") : ""),
    h(
      "td",
      {},
      button(table.open ? "Reload" : "Open", (event) => void askToOpen(session, table, event.currentTarget as HTMLButtonElement), {
        class: table.open ? "ghost" : "primary",
      }),
    ),
  );
}

function sessionBlock(session: Session): HTMLElement {
  const closed = session.tables.filter((t) => !t.open);
  return h(
    "section",
    { class: "open-session" },
    h(
      "header",
      {},
      h("strong", {}, session.label),
      h("span", { class: "hint" }, `process ${session.pid}`),
      closed.length > 1
        ? button("Open all", () => closed.forEach((t) => void askToOpen(session, t)), { class: "ghost" })
        : null,
    ),
    session.tables.length
      ? h("table", { class: "kf-table small" }, h("tbody", {}, ...session.tables.map((t) => tableRow(session, t))))
      : h("p", { class: "hint" }, "No tables"),
  );
}

/** A table in memory: its name, rows and size, then its actions. */
function datasetRow(d: Dataset): HTMLElement {
  const closed = d.grids.length === 0;
  const open = closed
    ? button("Open", (event) => {
        (event.currentTarget as HTMLButtonElement).disabled = true;
        // A grid on the table itself: the original comes back as a tab, in front, and this list closes.
        void api("/grids", "POST", { dataset: d.name }).then(closeDialogs, (e: Error) => toast(e.message, "error"));
      }, { class: "primary" })
    : null;
  const remove = button(`Remove ${d.name}`, () => {
    if (!confirm(`Remove ${d.name} from memory? ${closed ? "Nothing" : "Its tabs close too; nothing"} is saved.`)) return;
    void api(`/datasets/${encodeURIComponent(d.name)}`, "DELETE").catch((e: Error) => toast(e.message, "error"));
  }, { icon: "trash", iconOnly: true, class: "ghost" });
  return h(
    "tr",
    {},
    h("td", {}, h("strong", {}, d.name)),
    h("td", { class: "num", title: "rows" }, `${formatCount(d.rows)} row${d.rows === 1 ? "" : "s"}`),
    h("td", { class: "num" }, d.size),
    h("td", {}, open),
    h("td", {}, remove),
  );
}

function datasetBlock(title: string, id: string, datasets: Dataset[]): HTMLElement | null {
  if (!datasets.length) return null;
  return h(
    "section",
    { class: "open-session", id },
    h("header", {}, h("strong", {}, title)),
    h("table", { class: "kf-table small" }, h("tbody", {}, ...datasets.map(datasetRow))),
  );
}

/** The Tables list. Also what the status bar's memory meter opens. */
export function showTables(): void {
  const { dialog, body } = openDialog("Tables", true);
  body.classList.add("open-dialog");
  const budget = h("p", { class: "hint", id: "tables-budget", role: "status" }, "Loading…");
  const tables = h("div", { class: "open-tables" });
  const status = h("p", { class: "hint", role: "status" });
  const list = h("div", { class: "open-sessions" });
  body.append(budget, tables, h("section", { class: "open-session", id: "python-sessions" }, h("header", {}, h("strong", {}, "Python sessions")), status, list));

  const load = async (): Promise<void> => {
    try {
      const listing = await api<{ datasets: Dataset[]; budget: Budget }>("/datasets");
      const b = listing.budget;
      budget.textContent = `${b.used} of ${b.total} in use · ${b.datasets} of ${b.max_datasets} tables · ${b.grids} of ${b.max_grids} tabs`;
      tables.replaceChildren(
        ...[
          datasetBlock("Open tables", "open-tables", listing.datasets.filter((d) => d.grids.length)),
          datasetBlock("Closed tables", "closed-tables", listing.datasets.filter((d) => !d.grids.length)),
        ].filter((block): block is HTMLElement => block !== null),
      );
    } catch (e) {
      budget.textContent = `Could not read the tables: ${(e as Error).message}`;
    }
    try {
      const sessions = (await api<{ processes: Session[] }>("/processes")).processes;
      status.textContent = sessions.length ? "" : "No Python sessions";
      status.hidden = sessions.length > 0;
      list.replaceChildren(...sessions.map(sessionBlock));
    } catch (e) {
      status.hidden = false;
      status.textContent = `Could not read the Python sessions: ${(e as Error).message}`;
    }
  };

  redraw = () => void load();
  dialog.addEventListener("close", () => { redraw = null; });
  void load();
}
