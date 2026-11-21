/**
 * connectionTree.ts: a connection's tables as a tree with a search (the owner, 2026-11-17: "the app needs
 * to make it easy for me as the user to use that connection to get those tables"), on the same contract
 * every kind of connection keeps (domain/connection_tables.py): a Power BI workspace's datasets or a
 * database's schemas, each with its tables.
 *
 *   [TABLE]  Open (a grid), Preview (its first rows, under it), Copy name (`[Finance Captive].Sales`,
 *            how DuckDB SQL names it anywhere: the "+" tab, a notebook's %%sql cell, sab.sql)
 *   [GROUP]  Open all its tables (a confirm with the count; each its own grid), Import its relationships
 *            (Power BI), Query in a notebook (a new %%sql cell on its first table)
 *   [STATE]  a catalog that is not loaded loads (catalog_loading), said while it does
 *
 * ROUTING: GET /connections/{name}/tree   POST /connections/{name}/open   POST .../preview
 *          POST /connections/{name}/open-dataset {dataset}   POST /connections/{name}/relationships
 *          POST /workbench/window {command: "cell.insertBelow"}
 */
import { bringPage, PAGE_WINDOW } from "./workbenchPages";
import { api } from "./api";
import { button, clear, h, icon, toast } from "./dom";
import { busy, busyClick, loadingBlock, room } from "./loading";
import { tablePreview } from "./pythonConnectionForm";
import { clearError, errorHere, errorNote, showError } from "./errorNote";

interface TreeTable {
  database: string;
  schema: string;
  table: string;
  sql: string;
  /** What the source says of it: a Delta table's version, size and partition columns; a sheet. */
  title?: string;
}

interface TreeGroup {
  database: string;
  schema: string;
  count: number;
  tables: TreeTable[];
}

export interface Tree {
  connection: string;
  kind: string;
  group: string;
  state: { state: string; error?: string };
  groups: TreeGroup[];
}

export const WORKBENCH_WINDOW = PAGE_WINDOW.notebooks;
const SHOWN = 400; // tables drawn at once in a group (the search finds the rest)

/** A query's text for a new %%sql cell on a table. */
export function cellQuery(sql: string): string {
  return `SELECT *\nFROM ${sql}\nLIMIT 100`;
}

/** A new %%sql cell in the Workbench (its notebook in front), else the cell's text on the clipboard. */
export async function queryInNotebook(sql: string): Promise<void> {
  const source = cellQuery(sql);
  try {
    await api("/workbench/window", "POST", { command: "cell.insertBelow", args: { kind: "sql", source }, page: "notebooks" });
    bringPage("notebooks", "/notebooks", {}, true); // a cell is a notebook's: the Notebooks page (workbenchPages.ts)
    toast("A SQL cell is in the notebook.");
  } catch {
    await navigator.clipboard.writeText(`%%sql\n${source}`).catch(() => undefined);
    toast("Copied as a %%sql cell: paste it into a notebook.");
  }
}

/** The tree's section for a connection's detail; `onOpened` when a table opened as a grid. */
export function tablesSection(name: string, onOpened: () => void = () => undefined): HTMLElement {
  const path = encodeURIComponent(name);
  const list = h("div", { class: "conn-tree", role: "tree", "aria-label": `${name}'s tables` });
  const count = h("span", { class: "count" }, "");
  const search = h("input", { type: "search", class: "conn-tree-search", placeholder: "Search tables", "aria-label": "Search tables" }) as HTMLInputElement;
  const section = h(
    "section",
    { class: "connection-section connection-tables", "aria-label": "Tables" },
    h("h2", {}, icon("rows"), "Tables", count),
    search,
    list,
  );
  let tree: Tree | null = null;

  const open = async (t: TreeTable): Promise<void> => {
    try {
      const got = await api<{ dataset?: string }>(`/connections/${path}/open`, "POST", { database: t.database, schema: t.schema, table: t.table });
      toast(`${got.dataset ?? t.table} is open as a grid.`);
      onOpened();
    } catch (e) {
      errorHere(e);
    }
  };

  const preview = async (t: TreeTable, under: HTMLElement): Promise<void> => {
    if (under.childElementCount) {
      under.replaceChildren();
      return;
    }
    under.replaceChildren(loadingBlock(`Reading ${t.table}…`, { height: "80px" }));
    try {
      const got = await api<{ columns: string[]; rows: unknown[][] }>(`/connections/${path}/preview`, "POST", { database: t.database, schema: t.schema, table: t.table });
      under.replaceChildren(...tablePreview({ table: t.table, schema: t.schema, columns: got.columns, rows: got.rows, total: null }));
    } catch (e) {
      under.replaceChildren(errorNote(e));
    }
  };

  const openAll = async (g: TreeGroup): Promise<void> => {
    if (!confirm(`Open all ${g.count} tables of ${g.schema}? Each opens as its own grid.`)) return;
    try {
      const got = await busy(section, `Opening ${g.count} tables of ${g.schema}…`, api<{ opened: unknown[]; failed: { table: string; error: string }[] }>(`/connections/${path}/open-dataset`, "POST", { dataset: g.schema }), { errorIn: false });
      const failed = got.failed.length ? ` ${got.failed.length} could not: ${got.failed.map((f) => f.table).join(", ")}.` : "";
      if (got.failed.length) {
        showError(section, { what: `${got.opened.length} tables of ${g.schema} are open.${failed}`, where: g.schema, details: got.failed.map((f) => `${f.table}: ${f.error}`).join("\n") });
      } else {
        clearError(section);
        toast(`${got.opened.length} tables of ${g.schema} are open.`);
      }
      onOpened();
    } catch (e) {
      errorHere(e);
    }
  };

  const importRelationships = async (g: TreeGroup): Promise<void> => {
    try {
      const got = await api<{ imported: unknown[] }>(`/connections/${path}/relationships`, "POST", { dataset: g.schema });
      toast(`${got.imported.length} relationships from ${g.schema} are in the model.`);
    } catch (e) {
      errorHere(e);
    }
  };

  const row = (t: TreeTable): HTMLElement => {
    const under = h("div", { class: "conn-tree-preview" });
    return h(
      "li",
      { class: "conn-tree-table", role: "treeitem", "data-table": t.table },
      h(
        "div",
        { class: "conn-tree-row" },
        h("span", { class: "conn-tree-name" }, icon("rows"), t.table, t.title ? h("span", { class: "conn-tree-title" }, t.title) : null),
        h(
          "span",
          { class: "conn-tree-actions" },
          button("Open", busyClick("Opening…", () => open(t)), { icon: "rows", class: "small" }),
          button("Preview", busyClick("Reading…", () => preview(t, under)), { icon: "eye", class: "small line" }),
          button("Copy name", () => void navigator.clipboard.writeText(t.sql).then(() => toast(`Copied ${t.sql}`)), { icon: "copy", class: "small line", title: t.sql }),
        ),
      ),
      under,
    );
  };

  const draw = (): void => {
    if (!tree) return;
    const words = search.value.trim().toLowerCase();
    const groups = tree.groups
      .map((g) => ({ g, shown: words ? g.tables.filter((t) => `${g.schema}.${t.table}`.toLowerCase().includes(words)) : g.tables }))
      .filter(({ shown }) => shown.length || !words);
    const total = tree.groups.reduce((n, g) => n + g.count, 0);
    count.textContent = String(total);
    const single = tree.groups.length === 1 && tree.kind !== "powerbi";
    clear(
      list,
      groups.length
        ? h(
            "ul",
            { class: "conn-tree-groups", role: "group" },
            ...groups.map(({ g, shown }) => {
              const title = g.schema || g.database || tree!.connection;
              const items = h("ul", { class: "conn-tree-tables", role: "group" }, ...shown.slice(0, SHOWN).map(row));
              const more = shown.length > SHOWN ? h("p", { class: "hint" }, `${(shown.length - SHOWN).toLocaleString()} more: search to find them`) : null;
              const first = g.tables[0];
              return h(
                "li",
                { class: "conn-tree-group", role: "treeitem", "data-group": g.schema },
                h(
                  "details",
                  { open: single || Boolean(words) || groups.length === 1 },
                  h(
                    "summary",
                    {},
                    h("span", { class: "conn-tree-group-name" }, icon(tree!.kind === "powerbi" ? "diagram" : "folder"), title, h("span", { class: "count" }, String(g.count))),
                    h(
                      "span",
                      { class: "conn-tree-actions" },
                      g.count > 1 ? button("Open all", busyClick("Opening…", () => openAll(g)), { icon: "grids", class: "small line" }) : null,
                      tree!.kind === "powerbi" ? button("Import its relationships", busyClick(`Reading ${g.schema}'s relationships…`, () => importRelationships(g)), { icon: "diagram", class: "small line" }) : null,
                      first ? button("Query in a notebook", () => void queryInNotebook(first.sql), { icon: "notebook", class: "small line" }) : null,
                    ),
                  ),
                  items,
                  more,
                ),
              );
            }),
          )
        : h("p", { class: "empty-note" }, words ? "No table matches" : "No tables"),
    );
  };
  search.addEventListener("input", draw);

  const load = async (): Promise<void> => {
    clear(list, room());
    try {
      tree = await busy(section, `Loading ${name}'s tables…`, api<Tree>(`/connections/${path}/tree`), { errorIn: false });
      if (tree.state.state === "failed" && !tree.groups.length) {
        clear(list, errorNote(tree.state.error ?? "The catalog did not load."));
        return;
      }
      draw();
    } catch (e) {
      clear(list, errorNote(e));
    }
  };
  void load();
  return section;
}
