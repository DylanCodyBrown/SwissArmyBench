/**
 * workbenchCompletion.ts: what the Workbench's editors offer as you type. [FUNCTION]
 *
 *   PYTHON     the document's kernel (IPython's completer, with Jedi): your variables, their attributes,
 *              a DataFrame's columns, modules; hover shows a signature and its help. Inside
 *              sab.connection("…") or sab.blade("…"): your connection and blade names; inside
 *              sab.dax("…"): your Power BI workspaces' datasets
 *   SQL CELL   with no connection (DuckDB): after `[` the connections, after `[Finance].` its datasets or
 *              schemas and tables (connectionSql.ts); and
 *              the data explorer's catalog of the cell's connection (every catalog when it has none):
 *              schemas, tables, views and columns, `orders.` gives orders' columns; the kernel's names
 *              too once it runs (a file connection's own tables); SQL's words
 *   DAX CELL   its dataset's part of the workspace's catalog (a DAX cell names `Finance/Sales model`:
 *              the catalog Finance, the schema Sales model): tables as 'Sales', columns as
 *              'Sales'[Amount] (after 'Sales'[ that table's columns), measures as [Total Sales]; DAX's
 *              functions and keywords; never SQL's words, and nothing from the kernel
 *
 * The catalog answers are kept in the page (by what was asked), so typing on asks the server little.
 * Before the kernel starts nothing runs on the user's computer to complete: the catalog still answers.
 *
 * ROUTING: GET /catalogs, /catalogs/{name}/search, /catalogs/{name}/columns; POST /workbench/kernels/{id}/complete;
 *          POST /connections/{name}/catalog (a cell's connection with no catalog yet: it loads itself);
 *          GET /connections/{name}/datasets?live=0 (a Power BI workspace's datasets, from its catalog)
 */
import { api } from "./api";
import { connectionSuggestions } from "./connectionSql";
import type { Suggestion } from "./lazy/codeEditor";
import { sqlLine } from "./notebookCells";
import type { Kernel } from "./workbenchKernel";

interface Found {
  tables: { schema: string | null; table: string; kind: string; columns: number }[];
  columns: { schema: string | null; table: string; column: string; type: string }[];
}

const SQL_WORDS = [
  "SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "JOIN", "LEFT JOIN", "INNER JOIN", "ON", "AS",
  "DISTINCT", "COUNT", "SUM", "AVG", "MIN", "MAX", "CASE", "WHEN", "THEN", "ELSE", "END", "AND", "OR", "NOT",
  "IN", "IS NULL", "IS NOT NULL", "LIKE", "BETWEEN", "LIMIT", "TOP", "WITH", "UNION ALL", "INSERT INTO", "UPDATE",
  "DELETE", "CAST", "COALESCE", "DESC", "ASC",
];

// A DAX cell's own words, never SQL's: the keywords of a query, then the functions most used.
const DAX_KEYWORDS = ["EVALUATE", "DEFINE", "MEASURE", "COLUMN", "TABLE", "VAR", "RETURN", "ORDER BY", "START AT", "ASC", "DESC", "TRUE", "FALSE", "IN", "NOT"];
const DAX_FUNCTIONS = [
  "ADDCOLUMNS", "ALL", "ALLEXCEPT", "ALLSELECTED", "AND", "AVERAGE", "AVERAGEX", "BLANK", "CALCULATE", "CALCULATETABLE",
  "CALENDAR", "COALESCE", "CONCATENATE", "CONCATENATEX", "COUNT", "COUNTA", "COUNTROWS", "COUNTX", "CROSSJOIN", "DATATABLE",
  "DATE", "DATEADD", "DATESBETWEEN", "DATESYTD", "DISTINCT", "DISTINCTCOUNT", "DIVIDE", "EARLIER", "EXCEPT", "FILTER",
  "FIRSTDATE", "FORMAT", "GENERATE", "GROUPBY", "HASONEVALUE", "IF", "IFERROR", "INTERSECT", "ISBLANK", "ISFILTERED",
  "KEEPFILTERS", "LASTDATE", "LOOKUPVALUE", "MAX", "MAXX", "MIN", "MINX", "MONTH", "NATURALINNERJOIN", "NATURALLEFTOUTERJOIN",
  "OR", "RANKX", "RELATED", "RELATEDTABLE", "REMOVEFILTERS", "ROUND", "ROW", "SAMEPERIODLASTYEAR", "SELECTCOLUMNS",
  "SELECTEDVALUE", "SUM", "SUMMARIZE", "SUMMARIZECOLUMNS", "SUMX", "SWITCH", "TOPN", "TOTALYTD", "TREATAS", "UNION",
  "USERELATIONSHIP", "VALUES", "YEAR", "INFO.VIEW.TABLES", "INFO.VIEW.COLUMNS", "INFO.VIEW.MEASURES", "INFO.VIEW.RELATIONSHIPS",
  "COLUMNSTATISTICS",
];

// Each connection's dialect by its name without regard to case (the Workbench tells it as it lists them).
const dialects = new Map<string, string>();

/** The connections' dialects, as the page last listed them. */
export function setDialects(found: { name: string; dialect?: string | null }[]): void {
  dialects.clear();
  for (const c of found) if (c.dialect) dialects.set(c.name.toLowerCase(), c.dialect);
}

/** Whether this connection is a Power BI workspace: its datasets are what DAX cells run on. */
export function isWorkspace(connection: string | null): boolean {
  return connection !== null && dialects.get(connection.toLowerCase()) === "dax";
}

/** A DAX cell's dataset as it is named: `Finance/Sales model` is the connection Finance and its
 *  dataset Sales model ("" when the name is the workspace alone). */
export function splitDataset(name: string): { connection: string; dataset: string } {
  const at = name.indexOf("/");
  return at < 0 ? { connection: name.trim(), dataset: "" } : { connection: name.slice(0, at).trim(), dataset: name.slice(at + 1).trim() };
}

// The workspaces whose catalog is not loaded: their datasets are not listed until it is.
const unlisted = new Set<string>();

/** Every Power BI workspace's datasets as a DAX cell names them (`Finance/Sales model`), from each
 *  workspace's loaded catalog: Power BI is not asked, so no sign-in window opens for a list. A
 *  workspace with no catalog yet is there by its own name (a workspace of one dataset runs so). */
export async function listDatasets(workspaces: string[]): Promise<string[]> {
  const out: string[] = [];
  unlisted.clear();
  for (const workspace of workspaces) {
    try {
      const found = await api<{ from: string; datasets: { name: string; cell: string; note?: string }[] }>(`/connections/${encodeURIComponent(workspace)}/datasets?live=0`);
      if (found.from === "none") unlisted.add(workspace);
      // One that could not be read goes last: a new cell starts on a dataset that answers.
      const read = [...found.datasets.filter((d) => !d.note), ...found.datasets.filter((d) => d.note)];
      out.push(...(read.length ? read.map((d) => d.cell) : [workspace]));
    } catch {
      out.push(workspace);
    }
  }
  return out;
}

/** A DAX cell's picker was opened: a workspace whose datasets are not listed loads its catalog now
 *  (once; the page hears catalogs_changed and lists again). */
export function datasetsWanted(): void {
  for (const workspace of unlisted) loadCatalogOnce(workspace);
}

const daxTable = (table: string): string => `'${table.replaceAll("'", "''")}'`;
const daxColumn = (column: string): string => `[${column.replaceAll("]", "]]")}]`;

let catalogList: Promise<string[]> | null = null;
let catalogsAt = 0;
const searches = new Map<string, Promise<Found>>();
const tableColumns = new Map<string, Promise<{ column: string; type: string }[]>>();

/** Forget what was kept: a catalog was refreshed or loaded. */
export function forgetCatalogs(): void {
  catalogList = null;
  searches.clear();
  tableColumns.clear();
}

function catalogs(): Promise<string[]> {
  if (!catalogList || Date.now() - catalogsAt > 30_000) {
    catalogsAt = Date.now();
    catalogList = api<{ catalogs: { name: string }[] }>("/catalogs").then((r) => r.catalogs.map((c) => c.name), () => []);
  }
  return catalogList;
}

function search(catalog: string, text: string): Promise<Found> {
  const key = `${catalog}\u0000${text.toLowerCase()}`;
  let found = searches.get(key);
  if (!found) {
    found = api<Found>(`/catalogs/${encodeURIComponent(catalog)}/search?q=${encodeURIComponent(text)}&limit=200`).catch(() => ({ tables: [], columns: [] }));
    searches.set(key, found);
    if (searches.size > 500) searches.delete(searches.keys().next().value!);
  }
  return found;
}

function columnsOf(catalog: string, schema: string | null, table: string): Promise<{ column: string; type: string }[]> {
  const key = `${catalog}\u0000${schema ?? ""}\u0000${table}`;
  let found = tableColumns.get(key);
  if (!found) {
    const query = new URLSearchParams({ table, ...(schema ? { schema } : {}) });
    found = api<{ columns: { column: string; type: string }[] }>(`/catalogs/${encodeURIComponent(catalog)}/columns?${query}`).then((r) => r.columns, () => []);
    tableColumns.set(key, found);
  }
  return found;
}

/** Connections whose catalog this page asked to load (first use), so it asks once. */
const askedToLoad = new Set<string>();

function loadCatalogOnce(connection: string): void {
  if (askedToLoad.has(connection.toLowerCase())) return;
  askedToLoad.add(connection.toLowerCase());
  void api(`/connections/${encodeURIComponent(connection)}/catalog`, "POST").catch(() => undefined);
}

/** The SQL names at the cursor from the connection's catalog (all catalogs when it has none). */
async function catalogSuggestions(token: string, connection: string | null): Promise<Suggestion[]> {
  const names = await catalogs();
  const own = names.filter((c) => connection && c.toLowerCase() === connection.toLowerCase());
  // First use: the cell's connection has no catalog yet; it loads in the background and arrives
  // (catalogs_changed) for the next keystroke. Meanwhile the other catalogs answer.
  if (connection && !own.length) loadCatalogOnce(connection);
  const asked = own.length ? own : names.slice(0, 4);
  const out: Suggestion[] = [];
  const dot = token.lastIndexOf(".");
  for (const catalog of asked) {
    if (dot >= 0) {
      // orders.cu: the columns of orders; sales.or: the tables of the schema sales
      const owner = token.slice(0, dot).split(".").pop()!.replace(/"/g, "");
      const start = token.slice(dot + 1).replace(/"/g, "").toLowerCase();
      const found = await search(catalog, owner);
      for (const t of found.tables.filter((t) => t.table.toLowerCase() === owner.toLowerCase())) {
        for (const c of await columnsOf(catalog, t.schema, t.table)) {
          if (c.column.toLowerCase().startsWith(start)) out.push({ label: c.column, kind: "column", detail: `${t.table} · ${c.type}` });
        }
      }
      for (const t of found.tables.filter((t) => (t.schema ?? "").toLowerCase() === owner.toLowerCase() && t.table.toLowerCase().startsWith(start))) {
        out.push({ label: t.table, kind: t.kind === "view" ? "view" : "table", detail: `${t.schema} · ${t.columns} columns` });
      }
      continue;
    }
    if (!token) continue;
    const found = await search(catalog, token);
    const lower = token.toLowerCase();
    for (const t of found.tables) if (t.table.toLowerCase().startsWith(lower)) out.push({ label: t.table, kind: t.kind === "view" ? "view" : "table", detail: `${t.schema ? `${t.schema} · ` : ""}${t.columns} columns · ${catalog}` });
    for (const t of found.tables) if (t.schema && t.schema.toLowerCase().startsWith(lower)) out.push({ label: t.schema, kind: "schema", detail: catalog });
    for (const c of found.columns) if (c.column.toLowerCase().startsWith(lower)) out.push({ label: c.column, kind: "column", detail: `${c.table} · ${c.type}` });
  }
  const seen = new Set<string>();
  return out.filter((s) => (seen.has(`${s.kind}:${s.label}`) ? false : (seen.add(`${s.kind}:${s.label}`), true)));
}

async function kernelSuggestions(kernel: Kernel, code: string, offset: number, shift = 0): Promise<Suggestion[]> {
  const found = await kernel.complete(code, offset);
  if (!found) return [];
  return found.matches.map((m) => {
    const kind = found.types[m];
    return { label: m.split(".").pop() || m, insert: m, kind: kind && kind !== "<unknown>" ? kind : "statement", detail: kind && kind !== "<unknown>" ? kind : "", start: found.start - shift, end: found.end - shift };
  });
}

/** Python: the kernel's completions, every connection by its name (there before it is first used, so
 *  the kernel does not know it yet), and names inside sab.connection("…"). */
export function pythonCompleter(kernel: Kernel, names: () => { connections: string[]; blades: string[]; codeNames?: { name: string; connection: string; kind: string }[]; datasets?: string[] }) {
  return async (text: string, offset: number): Promise<Suggestion[]> => {
    const before = text.slice(Math.max(0, offset - 200), offset);
    const quoted = /sab\.(connection|blade|sql|dax)\(\s*["']([^"']*)$/.exec(before);
    if (quoted) {
      // sab.dax("…"): a Power BI workspace's datasets, as Finance/Sales model.
      const wanted = quoted[1] === "blade" ? names().blades : quoted[1] === "dax" ? (names().datasets ?? []) : names().connections;
      const typed = quoted[2]!.toLowerCase();
      const what = quoted[1] === "blade" ? "blade" : quoted[1] === "dax" ? "dataset" : "connection";
      return wanted.filter((n) => n.toLowerCase().startsWith(typed)).map((n) => ({ label: n, kind: "connection", detail: what, start: offset - quoted[2]!.length, end: offset }));
    }
    // A quote just typed opens a string: nothing to offer yet (IPython would list its 142 magics, and
    // Enter would put `%%!` in the code). Inside a string, its file paths come once a letter follows.
    if (/(^|[^\w])["']$/.test(before)) return [];
    // The cursor's line first: the kernel then completes against the live objects (a DataFrame's columns).
    // Sent the whole cell, Jedi reads `rainfall = pd.DataFrame(...)` above it as code and misses them.
    const word = /(^|[^\w.])([A-Za-z_]\w*)$/.exec(before)?.[2] ?? "";
    const connected = word
      ? (names().codeNames ?? []).filter((c) => c.name.startsWith(word.toLowerCase())).map((c) => ({
        label: c.name,
        kind: "connection",
        detail: `${c.connection} (${c.kind === "file" ? "a file" : c.kind === "python" ? "your own Python" : "a database"} connection)`,
        start: offset - word.length,
        end: offset
      }))
      : [];
    const lineStart = text.lastIndexOf("\n", offset - 1) + 1;
    const lineEnd = text.indexOf("\n", offset);
    const line = text.slice(lineStart, lineEnd < 0 ? undefined : lineEnd);
    const live = await kernelSuggestions(kernel, line, offset - lineStart, -lineStart);
    const fromKernel = live.length || lineStart === 0 ? live : await kernelSuggestions(kernel, text, offset);
    // Magics (%timeit, %%sql) only once a % is typed.
    const magic = /%\w*$/.test(before);
    const offered = fromKernel.filter((s) => magic || !(s.insert ?? s.label).startsWith("%"));
    return [...connected, ...offered.filter((s) => !connected.some((c) => c.label === s.label))];
  };
}

/** A DAX cell: its dataset's tables, columns and measures (the workspace's catalog, that dataset's
 *  schema), and DAX's functions and keywords. No SQL words, and nothing from the kernel (it would
 *  complete the text as Python or SQL). `named`: the cell's dataset, as `Finance/Sales model`. */
export function daxCompleter(named: () => string | null) {
  return async (text: string, offset: number): Promise<Suggestion[]> => {
    const { connection, dataset } = splitDataset(named() ?? "");
    const word = /[\w.]*$/.exec(text.slice(0, offset))![0];
    const from = offset - word.length;
    const opener = text[from - 1] ?? "";
    const lower = word.toLowerCase();
    const dotted = word.includes("."); // INFO.VIEW.TABLES: a function's name, never a catalog's
    const catalog = dotted ? undefined : connection ? (await catalogs()).find((c) => c.toLowerCase() === connection.toLowerCase()) : undefined;
    if (connection && !catalog) loadCatalogOnce(connection); // first use: it arrives for a later keystroke
    // The dataset's part of the catalog alone (a workspace of one dataset names none).
    const mine = (schema: string | null): boolean => !dataset || (schema ?? "").toLowerCase() === dataset.toLowerCase();
    const out: Suggestion[] = [];
    if (opener === "[") {
      // Inside brackets: after 'Sales'[ (or Sales[) that table's columns; alone, the measures.
      const closes = text[offset] === "]" ? offset + 1 : offset; // the editor closed the bracket already
      const owner = /(?:'((?:[^']|'')*)'|\b([A-Za-z_]\w*))$/.exec(text.slice(0, from - 1));
      const table = owner ? (owner[1]?.replaceAll("''", "'") ?? owner[2]!) : null;
      if (!catalog) return [];
      if (table) {
        const found = (await search(catalog, table)).tables.filter((t) => mine(t.schema) && t.table.toLowerCase() === table.toLowerCase());
        for (const t of found) {
          for (const c of await columnsOf(catalog, t.schema, t.table)) {
            if (c.column.toLowerCase().startsWith(lower) && !c.type.startsWith("measure")) out.push({ label: c.column, insert: daxColumn(c.column), filter: daxColumn(c.column), kind: "column", detail: `${t.table} · ${c.type}`, start: from - 1, end: closes });
          }
        }
        return out;
      }
      if (!word) return [];
      for (const c of (await search(catalog, word)).columns) {
        if (mine(c.schema) && c.type.startsWith("measure") && c.column.toLowerCase().startsWith(lower)) out.push({ label: c.column, insert: daxColumn(c.column), filter: daxColumn(c.column), kind: "function", detail: `${c.table} · ${c.type}`, start: from - 1, end: closes });
      }
      return out;
    }
    if (!word) return [];
    const quoted = opener === "'";
    const start = quoted ? from - 1 : from;
    const end = quoted && text[offset] === "'" ? offset + 1 : offset;
    if (catalog) {
      const found = await search(catalog, word);
      for (const t of found.tables) {
        if (mine(t.schema) && t.table.toLowerCase().startsWith(lower)) out.push({ label: t.table, insert: daxTable(t.table), kind: "table", detail: `${t.columns} columns and measures · ${t.schema || catalog}`, start, end });
      }
      if (!quoted) {
        for (const c of found.columns) {
          if (!mine(c.schema) || !c.column.toLowerCase().startsWith(lower)) continue;
          const measure = c.type.startsWith("measure");
          out.push({ label: c.column, insert: measure ? daxColumn(c.column) : daxTable(c.table) + daxColumn(c.column), kind: measure ? "function" : "column", detail: `${c.table} · ${c.type}`, start, end });
        }
      }
    }
    const seen = new Set<string>();
    const names = out.filter((s) => (seen.has(`${s.kind}:${s.insert}`) ? false : (seen.add(`${s.kind}:${s.insert}`), true)));
    // Inside a quote the typed text starts with it: matched against 'Customer', not Customer.
    if (quoted) return names.map((s) => ({ ...s, filter: s.insert }));
    const words = [...DAX_KEYWORDS.map((w) => ({ label: w, kind: "keyword" })), ...DAX_FUNCTIONS.map((w) => ({ label: w, kind: "function", detail: "DAX" }))];
    return [...names, ...words.filter((w) => w.label.toLowerCase().startsWith(lower)).map((w) => ({ ...w, start, end }))];
  };
}

/** A SQL cell: its connection's catalog, the kernel's names (as the %%sql cell it runs as), SQL's words. */
export function sqlCompleter(kernel: Kernel, connection: () => string | null, names: () => string[] = () => []) {
  return async (text: string, offset: number): Promise<Suggestion[]> => {
    // No connection: DuckDB, where a connection's tables are named by the connection ([Finance].Sales).
    if (!connection()) {
      const named = await connectionSuggestions(text, offset, names());
      if (named.length) return named;
    }
    const token = /[\w."]*$/.exec(text.slice(0, offset))![0];
    const header = `${sqlLine(connection())}\n`;
    const [fromCatalog, fromKernel] = await Promise.all([
      catalogSuggestions(token, connection()),
      kernelSuggestions(kernel, header + text, offset + header.length, header.length).catch(() => []),
    ]);
    const words = token.includes(".") ? [] : SQL_WORDS.filter((w) => w.toLowerCase().startsWith(token.toLowerCase()) && token).map((w) => ({ label: w, kind: "keyword" }));
    const seen = new Set(fromCatalog.map((s) => s.label.toLowerCase()));
    return [...fromCatalog, ...fromKernel.filter((s) => !seen.has(s.label.toLowerCase())), ...words];
  };
}
