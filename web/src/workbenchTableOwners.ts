/**
 * workbenchTableOwners.ts: each open table's read-only cell lives in one document (docs/ideas.md, 2026-11-14).
 * Moved out of workbenchPage.ts along its own heading (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [OWNER]  the document whose code made the table, else the one whose kernel sent it, else one that already
 *            holds its cell, else (a project) data.ipynb, else the document in front. Once given, it stays
 *   [TOOL]   the group row's word on the focused document's tables: Run tables, when one is not up to date
 *
 * ROUTING: GET /tables/cells (workbenchTables.ts fetchTables)
 */
import { button, clear, h } from "./dom";
import { errorHere } from "./errorNote";
import type { NotebookView } from "./workbenchNotebook";
import type { Doc } from "./workbenchPage";
import type { ScriptView } from "./workbenchScript";
import { fetchTables, type TableInfo } from "./workbenchTables";

/** What the tables' owners ask of the page: its documents and the one in front, and which document is the
 *  project's API.py (never given a table's cell) or its data.ipynb (given the tables no document made). */
export interface TableOwnersHost {
  docs: Doc[];
  readonly current: Doc | null;
  isApiFile: (doc: Doc | null) => boolean;
  isData: (doc: Doc) => boolean;
}

export function tableOwners(host: TableOwnersHost) {
  const { docs, isApiFile, isData } = host;
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
    // Never API.py: it is the project's local sandbox API (its header is the file's first lines, and its process
    // reaches only the sandbox), so no table's cell is written into it.
    const code = docs.filter((d) => (d.notebook || d.script) && !isApiFile(d));
    for (const [name, doc] of [...tableOwner]) if (!docs.includes(doc) || !tables.some((t) => t.name === name)) tableOwner.delete(name);
    for (const table of tables) {
      if (tableOwner.has(table.name)) continue;
      const noPython = table.origin !== "python" && table.origin !== "unknown";
      // In a project a table's read-only cell lives in data.ipynb (its export data.py is what the
      // other notebooks and the pages import): a table no document made goes there.
      const data = code.find(isData);
      // The document whose code made it (the server says: a project's documents share one kernel), else the
      // document of the kernel that sent it.
      const made = table.document ? code.find((d) => d.path === table.document) : undefined;
      const found = made ?? (table.kernel ? code.find((d) => d.kernel?.id === table.kernel && (!d.kernel.shared || !table.document)) : undefined) ?? code.find((d) => viewOf(d)!.holdsTable(table.name)) ?? data ?? (noPython && host.current && code.includes(host.current) ? host.current : undefined);
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
    const view = host.current ? viewOf(host.current) : undefined;
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

  return {
    tableOwner, tablesSent, tablesHost, viewOf, assignTables, assignSoon, refreshTablesSoon, giveTable, drawTablesTool,
    /** The open tables as last read. */
    get tables(): TableInfo[] {
      return tables;
    },
    /** Read them now (the page shows a table's transformations before the first notice). */
    read: async (): Promise<TableInfo[]> => (tables = await fetchTables()),
  };
}
