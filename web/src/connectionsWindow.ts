/**
 * connectionsWindow.ts: the Connections page, the rail's plug (Plans/workbench-and-connections.plan.md):
 * the user's connections, each a database, a file or a key vault, and adding one with a form per type.
 * [WIRE + EXPORT]
 *
 *   [PAGE]   a page, not a dialog (the owner, 2026-11-16: "connection rail icon should open a connections
 *            page where all the active connections are presented as cards and I can click one to see all
 *            the references in the workbench that use that connection and an overview of its
 *            configuration and how many times it has been called this session"): areaPage.ts, at the
 *            address the dialog had (open=connections), over whichever page you are on
 *   [CARDS]  a card each, grouped (databases, files, your own code, key vaults): its type's icon, its
 *            name, its type, its status (works, ready, needs a password, failing: a cheap check, never a
 *            run) and its calls this session. Add connection and Add API in the heading row
 *   [DETAIL] a card's click (at=detail&name=): where it is used (each notebook or script cell, canvas
 *            block and open grid; a click opens that cell in the Workbench, or the grid), its
 *            configuration (type, settings, sign-in, each password's source by kind and name: never a
 *            value), its calls this session by kind; Open as grid, Edit, Test, Refresh catalog, Copy for
 *            Python, Remove. A Power BI dataset has Import its relationships in the catalog
 *   [POWER BI] its form signs in three ways; the first reads the app registration's tenant id, client
 *            id and client secret from a key vault (each box starts on "A key vault")
 *   [ADD]    pick a type (Databases, Files, Vaults), then its form:
 *   [ORDER]  every database form reads the same way (the owner's decision 14; the rule is
 *            domain/connections.py form_order): where it is (server, port, catalog or database, then the
 *            rest), who signs in (Sign in, the user, then each password under its own label), how it is
 *            secured (encrypt, the certificate file and Trust server certificate together)
 *   [FILE]   a file connection is named after the file picked or typed; Test shows the file's columns
 *            and first rows
 *   [DRIVER] a driver that is not installed: the command, and Install beside it (into the app's Python)
 *   [FORM]   a name; Sign in, where the type has several ways (SQL Server, Azure SQL: Windows, user name
 *            and password, MFA), each its own code, switched keeping what was typed; the starter's
 *            settings as fields (on/off ones as checkboxes; a file or folder field has Browse…); its
 *            passwords (kept in the system keyring); Test connection (runs the form, nothing saved);
 *            Save. The Python it makes shows underneath, editable for the unusual case
 *   [PYTHON] "Python (your own code)", under Your own code: its own form (pythonConnectionForm.ts:
 *            three code boxes and the environment variables they read); its row's Test shows the first
 *            table's first rows under it
 *   [API]    Add API (addApi.ts): an OpenAPI document or a form made into API_<name>.py and a Python
 *            connection, then that connection's form (where each variable comes from)
 *   [VAULT]  a vault's form lists its secrets by name (never a value) as soon as it can be read (its
 *            address filled in, or opened to edit). Each becomes an environment variable: left empty,
 *            under the vault's own name (shown faintly); typed, under that name. Every secret (new ones
 *            too), or untick it and choose. Every Workbench kernel starts with them set
 *
 * ROUTING: [CARDS] GET /connections/usage      [DETAIL] GET /connections/{name}/usage, GET /connections
 *          Remove -> DELETE /blades/{name}; Refresh -> POST /blades/{name}/refresh
 *          [TYPES] GET /connections/types        [EDIT] GET /connections/{name}
 *          [FIELD] POST /blades/fill (the value into the code)   [CODE] POST /blades/inspect (its fields again)
 *          [TEST]  POST /connections/test        [SAVE] POST /connections, PUT /connections/{name}
 *          [VAULT] POST /connections/vaults/secrets (the names in it); GET /connections/vaults (a password's)
 *          [RELATIONSHIPS] POST /connections/{name}/relationships (a Power BI dataset's, merged)
 *          [INSTALL] POST /blades/install {packages}, then POST /blades/inspect (is it installed now?)
 */
import { showAddApi } from "./addApi";
import { api, errorText, onNotice, token } from "./api";
import { openAreaPage, type PageElement } from "./areaPage";
import { button, clear, h, hasIcon, icon, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { openImport } from "./projectImport";
import { pickSheets } from "./openFile";
import { type Missing, noticeMissing, promptForError } from "./missingPackages";
import { colourPicker } from "./connectionColours";
import { kindIcon } from "./kindColours";
import { backButton, crumbs, dismissDialog, go, homeWindow, layerOpened, registerLayer, runArea, setOverTitle, visit, watchLayerDialog, withParams } from "./nav";
import { pythonWorked, showPythonForm, tablePreview, type PythonForm, type PythonTested, type TablePreview } from "./pythonConnectionForm";

interface Field {
  id: string;
  name: string;
  key: string;
  value: string | number | boolean;
  type: "text" | "number" | "flag";
  placeholder: boolean;
  picker: "file" | "folder" | null;
  suggestions: { value: string; from: string }[];
  /** A certificate or keystore file only: the environment variable it is read from (null: a plain path). */
  env?: string | null;
}

interface Form {
  id: string;
  label: string;
  group: string;
  connection: "database" | "file" | "vault" | "python";
  kind: string;
  dialect: string;
  variable: string;
  catalog: { language: string; command: string } | null;
  note: string;
  code: string;
  fields: Field[];
  secrets: string[];
  install_here: string | null;
  /** The packages the code needs, each installed in the app's Python or not. */
  packages?: { pip: string; installed: boolean }[];
  /** What is missing from the app's Python, in the one shape the prompt reads (missingPackages.ts). */
  missing?: Missing | null;
  /** The rule's place for each setting it names: its part of the form and its rank there. */
  field_places?: Record<string, { part: "where" | "who" | "security"; rank: number }>;
  name?: string;
  description?: string;
  summary?: { secrets: Record<string, boolean> };
  vault_mapping: Mapping[];
  vault_all?: boolean;
  /** A database: how many rows a table opens with as a grid (none: 10,000). */
  row_limit?: number | null;
  /** Ways to sign in, each its own code; `mark` is text only that code holds. */
  sign_ins?: { label: string; mark: string; code: string }[];
  /** Where a new one's passwords are first offered from: "vault" (a Power BI dataset's app registration). */
  secrets_from?: string;
}

interface Mapping {
  env: string;
  secret: string;
}

interface Vault {
  name: string;
  entries: Mapping[];
  /** Every secret it holds, each under its own name. */
  every: boolean;
  read_only: boolean;
}

/** After a vault saved from a password's "New vault": back to that connection's form. */
type Then = (saved: string | null) => void;

interface Connection {
  name: string;
  template?: string | null;
  connection: "database" | "file" | "vault" | "python";
  /** A key vault's: each variable it sets, from which secret; `every`: every secret it holds. */
  entries?: Mapping[];
  every?: boolean;
  type: string;
  dialect: string;
  has_catalog: boolean;
  /** Its catalog loading in the background: loading, waiting (first use), failed and why; none: loaded or not asked. */
  catalog_state: { state: "loading" | "waiting" | "failed"; error?: string } | null;
  catalog_loaded: boolean;
  description: string;
  source: string;
  pack: string | null;
  /** A project opened on another computer: a password with no source here, and its fix (Edit). */
  needs_password?: { missing: string[]; message: string } | null;
}

type Status = "works" | "ready" | "needs" | "failing";

interface Calls {
  total: number;
  by_kind: Record<string, number>;
  last_used: number | null;
  last_kind: string | null;
  last_ok: boolean | null;
}

/** A card (GET /connections/usage). */
interface Card {
  name: string;
  connection: Connection["connection"];
  type: string;
  template: string | null;
  status: Status;
  missing: string[];
  catalog_state: { state: string; error?: string } | null;
  calls: Calls;
}

/** A cell, a canvas block or an open grid that uses a connection. */
export interface Reference {
  document: string;
  title: string;
  kind: "notebook" | "script" | "app" | "grid";
  how: string;
  line: string;
  cell: number | null;
  name?: string;
  page?: string;
  block?: string;
  grid?: string;
  table_cell?: boolean;
}

interface Usage extends Card {
  references: Reference[];
  unread: string[];
  configuration: {
    kind: Connection["connection"];
    type: string;
    dialect: string;
    description: string;
    settings: { name: string; value: string | number | boolean }[];
    sign_in: string | null;
    passwords: { name: string; from: "keyring" | "vault" | "environment" | "missing"; vault?: string; secret?: string }[];
    variables: { name: string; from: string; vault?: string; secret?: string }[];
    vault_entries: { variable: string; secret: string }[];
    vault_all: boolean;
    catalog: boolean;
    row_limit: number | null;
  };
}

const STATUS_WORDS: Record<Status, string> = { works: "Works", ready: "Ready", needs: "Needs a password", failing: "Failing" };
const CALL_WORDS: Record<string, string> = { catalog: "Catalog loads", query: "Queries", read: "Table reads", test: "Tests", connect: "Connects" };

/** A card's status, in a word (the reason on hover: the missing passwords, the catalog's failure). */
function statusPill(c: Card): HTMLElement {
  const why = c.status === "needs" ? c.missing.join(", ") : c.status === "failing" ? (c.catalog_state?.error ?? "") : "";
  return h("span", { class: `connection-status st-${c.status}`, title: why || undefined }, h("span", { class: "connection-status-dot", "aria-hidden": "true" }), STATUS_WORDS[c.status]);
}

function ago(seconds: number): string {
  const s = Math.max(0, Date.now() / 1000 - seconds);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return `${Math.floor(s / 3600)} h ago`;
}

/** "12 calls · 3 min ago"; "No calls yet". */
function callsWord(calls: Calls): string {
  if (!calls.total) return "No calls yet";
  return `${calls.total.toLocaleString()} call${calls.total === 1 ? "" : "s"}${calls.last_used ? ` · ${ago(calls.last_used)}` : ""}`;
}

/** Where a reference opens: the Workbench page's own (its documents and cells), else this one. */
let cellOpener: ((path: string, cell: number | null) => Promise<void>) | null = null;

/** The Workbench: a reference opens its cell here (workbenchPage.ts goToCell). */
export function setCellOpener(open: (path: string, cell: number | null) => Promise<void>): void {
  cellOpener = open;
}

const WORKBENCH_WINDOW = "swissarmybench-workbench";

/** A reference's click: its cell in the Workbench (this window's, else the Workbench window, opened on
 *  it when there is none), or its grid on the home page. */
export async function openReference(ref: Reference): Promise<void> {
  if (ref.kind === "grid" && ref.grid) {
    const url = `/g/${encodeURIComponent(ref.grid)}`;
    if (document.querySelector(".tabs-row")) {
      visit(url);
      return;
    }
    const found = homeWindow();
    if (found) {
      found.win.location.href = url;
      found.win.focus();
    }
    return;
  }
  if (cellOpener) {
    visit(withParams({ open: null, at: null, type: null, name: null })); // the page makes way
    await cellOpener(ref.document, ref.cell);
    return;
  }
  try {
    await api("/workbench/window", "POST", { command: "file.openCell", args: { path: ref.document, ...(ref.cell ? { cell: ref.cell } : {}) } });
    window.open("", WORKBENCH_WINDOW)?.focus();
  } catch {
    // No Workbench window yet: one, opened on the file at the cell.
    const words = new URLSearchParams({ ...(token ? { token } : {}), open: ref.document, ...(ref.cell ? { cell: String(ref.cell) } : {}) });
    window.open(`/workbench#${words.toString()}`, WORKBENCH_WINDOW)?.focus();
  }
}

/** A reference as the detail lists it: the document's icon, its name and cell, how it names the
 *  connection, the line. */
function referenceItem(ref: Reference, connection: string): HTMLElement {
  const where = ref.kind === "grid" ? "an open grid" : ref.kind === "app" ? `${ref.page ?? "a page"} · ${ref.line}` : ref.cell ? `@cell${ref.cell}${ref.name ? ` ${ref.name}` : ""}` : "main code";
  return h(
    "li",
    {},
    h(
      "button",
      {
        type: "button",
        class: `connection-ref km-${ref.kind === "grid" ? "plain" : ref.kind}`,
        "data-kind": ref.kind,
        "data-connections": connection, // it wears the connection's colour
        title: ref.document || ref.title,
        onclick: () => void openReference(ref).catch((e: Error) => toast(e.message, "error")),
      },
      h("span", { class: "connection-ref-icon", "aria-hidden": "true" }, icon(ref.kind === "grid" ? "grids" : kindIcon(ref.kind, ref.document))),
      h("span", { class: "connection-ref-where" }, h("strong", {}, ref.title), h("span", { class: "connection-ref-cell" }, where), ref.table_cell ? h("span", { class: "badge" }, "Table cell") : null),
      h("code", { class: "connection-ref-how" }, ref.how),
      ref.kind === "app" ? null : h("code", { class: "connection-ref-line" }, ref.line),
    ),
  );
}

/** A term and its description, for the configuration and the calls. */
const term = (name: string, ...value: (Node | string | null)[]): HTMLElement[] => [h("dt", {}, name), h("dd", {}, ...value)];

/** The calls this session, by kind, and the last use. */
function callsList(calls: Calls): HTMLElement {
  return h(
    "dl",
    { class: "connection-calls" },
    ...Object.entries(CALL_WORDS).flatMap(([k, label]) => term(label, String(calls.by_kind[k] ?? 0))),
    ...term("Last used", calls.last_used ? `${ago(calls.last_used)}${calls.last_ok === false ? " (failed)" : ""}` : "Not yet"),
  );
}

/** How code names a connection: a Power BI workspace's DAX cells, your own Python's sab.read, a key
 *  vault's sab.blade, a database's sab.connection and SQL cell. */
function inCode(c: Connection): string {
  const cell = /\s/.test(c.name) ? `"${c.name}"` : c.name;
  if (c.dialect === "dax") return `sab.dax("${c.name}/<dataset>", …)  ·  %%dax ${c.name}/<dataset>`;
  if (c.connection === "vault") return `sab.blade("${c.name}")`;
  if (c.connection === "python" || c.dialect === "dataverse") return `sab.connection("${c.name}")  ·  sab.read("${c.name}", table)${c.dialect === "dataverse" ? `  ·  %%sql ${cell}` : ""}`;
  return `sab.connection("${c.name}")  ·  %%sql ${cell}`;
}

function passwordSource(p: Usage["configuration"]["passwords"][number]): string {
  if (p.from === "keyring") return "the system keyring";
  if (p.from === "vault") return p.secret ? `${p.vault} (${p.secret})` : `${p.vault}`;
  if (p.from === "environment") return "an environment variable";
  return "nowhere yet";
}

const FILE_KINDS: Record<string, string[]> = {
  csv: [".csv", ".tsv", ".txt"],
  excel: [".xlsx", ".xlsm", ".xls"],
  parquet: [".parquet"],
  json: [".json", ".jsonl", ".ndjson"],
  sqlite: [".db", ".sqlite", ".sqlite3"],
  duckdb: [".duckdb", ".db"],
  access: [".accdb", ".mdb"],
};

const words = (name: string): string => (name.charAt(0).toUpperCase() + name.slice(1)).replace(/_/g, " ");
/** A starter's label as a type's name: "A CSV file" -> "CSV file". */
const plain = (label: string): string => {
  const bare = label.replace(/^(an?|the) /i, "");
  return bare.charAt(0).toUpperCase() + bare.slice(1);
};
/** A path's file or folder name without its kind: C:\data\orders.csv -> orders. */
/** The variable a certificate file is offered as (domain/certificate_files.py suggested_variable):
 *  Warehouse, certificate file -> WAREHOUSE_CERTIFICATE_FILE; a keystore's is TRINO_KEYSTORE_PATH. */
const certificateVariable = (connection: string, setting: string): string => {
  if (setting === "keystore") return "TRINO_KEYSTORE_PATH";
  const name = `${connection} ${setting}`.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toUpperCase();
  return name && !/^[0-9]/.test(name) ? name : `_${name}`;
};
// What the file chooser offers for each kind of certificate file.
const CERTIFICATE_KINDS: Record<string, string[]> = {
  "certificate file": [".pem", ".crt", ".cer"],
  "client certificate file": [".pem", ".crt", ".cer"],
  "client key file": [".pem", ".key"],
  keystore: [".keystore", ".jks", ".jceks", ".p12", ".pfx"],
};
const stem = (path: string): string => (path.split(/[\\/]/).filter(Boolean).pop() ?? "").replace(/\.[^.]+$/, "");
/** A secret's variable, named as in the vault (domain/blades.py env_name_for_secret): SqlPassword stays,
 *  Sql--Password -> Sql__Password, warehouse-password -> warehouse_password. */
const envFor = (secret: string): string => {
  const w = secret.trim().replace(/^[a-z][a-z0-9+.-]*:\/\//i, "").replace(/--/g, "__").replace(/[^A-Za-z0-9_]/g, "_").replace(/^_+|_+$/g, "").slice(0, 128) || "SECRET";
  return (/^\d/.test(w) ? `_${w}` : w).slice(0, 128);
};
/** What a Test answers: a vault reads its variables; a connection makes something (a file: is there). */
// A Power BI workspace's test signs in and lists its datasets (`found` says how many); a connection saved
// for one dataset asks it one question: say that, not its class's name. Your own Python's says what each box gave.
const worked = (r: { type?: string; found?: string; variables?: string[]; tables?: number; columns?: number }): string =>
  pythonWorked(r) ?? (r.variables ? `read ${r.variables.join(", ")}` : (r.found ?? (r.type === "PowerBI" ? "signed in and reached the dataset" : `made a ${r.type}`)));

// The list, while it shows: drawn again as catalogs load in the background (the notices below).
let listShowing: (() => void) | null = null;
onNotice((notice) => {
  if (notice.type === "catalog_loading" || notice.type === "catalogs_changed") listShowing?.();
});

/** What a connection's catalog is doing, in a word or two (the reason on hover). */
function catalogWord(c: Connection): HTMLElement | null {
  const state = c.catalog_state?.state;
  if (state === "loading") return h("span", { class: "hint" }, "loading catalog…");
  if (state === "failed") return h("span", { class: "status-error", title: c.catalog_state?.error ?? "" }, "catalog not loaded");
  return null;
}

interface Preview {
  columns: string[];
  rows: unknown[][];
  sheet?: string;
}

/** A file connection's Test: what is in the file, its columns and first rows. */
function previewOf(preview: Preview): HTMLElement[] {
  const n = preview.columns.length;
  const shown = (value: unknown): string => (value === null || value === undefined ? "" : String(value));
  return [
    h("p", { class: "hint" }, `${preview.sheet ? `Sheet ${preview.sheet}: ` : ""}${n.toLocaleString()} column${n === 1 ? "" : "s"}, the first ${preview.rows.length.toLocaleString()} row${preview.rows.length === 1 ? "" : "s"}`),
    h(
      "div",
      { class: "connection-preview", tabindex: 0, role: "region", "aria-label": "The file's first rows" },
      h("table", { class: "small" }, h("thead", {}, h("tr", {}, ...preview.columns.map((c) => h("th", {}, c)))), h("tbody", {}, ...preview.rows.map((row) => h("tr", {}, ...row.map((v) => h("td", { class: typeof v === "number" ? "num" : "" }, shown(v))))))),
    ),
  ];
}

/** On the grid page the new table arrives as the tab in front, so the page makes way for the grids
 * (decision 8). In the Workbench's window the grid is in another window, and this page stays. */
function shownAsTab(): void {
  if (document.querySelector(".tabs-row")) visit(withParams({ open: null, at: null, type: null, name: null }));
}

/** A file connection's file as a grid: a workbook asks which sheets (the first ticked), a folder's
 * files open from the catalog (each its own table). */
async function openConnection(name: string): Promise<void> {
  const path = `/connections/${encodeURIComponent(name)}/open`;
  try {
    const answer = await api<{ dataset?: string; sheets?: string[] }>(path, "POST", {});
    if (answer.sheets) {
      const sheets = await pickSheets(name, answer.sheets);
      for (const sheet of sheets) await api(path, "POST", { table: sheet });
      if (sheets.length) shownAsTab();
      return;
    }
    shownAsTab();
    toast(`${answer.dataset} is open as a grid.`);
  } catch (e) {
    toast(errorText(e), "error");
  }
}

/** One Power BI dataset's own relationships (`dataset`: the one of the workspace `connection`),
 * merged into the current model (the ERD and the Key Finder's known joins then show them). It is
 * offered on a dataset in the catalog (its right-click menu and its page) and when one of its tables
 * opens as a grid. */
export async function importRelationships(connection: string, dataset = ""): Promise<void> {
  const from = dataset || connection;
  toast(`Reading ${from}'s relationships…`);
  try {
    const answer = await api<{ imported: unknown[]; changed: string[] }>(`/connections/${encodeURIComponent(connection)}/relationships`, "POST", dataset ? { dataset } : {});
    const n = answer.imported.length;
    const changed = answer.changed.length ? ` Changed: ${answer.changed.join("; ")}.` : "";
    toast(`${n.toLocaleString()} relationship${n === 1 ? "" : "s"} from ${from} ${n === 1 ? "is" : "are"} in the model.${changed}`);
  } catch (e) {
    toast(errorText(e), "error");
  }
}

/** A connection type's icon (2026-11-16): its own, by its id (dom.ts ICONS: postgres, excel,
 *  azure_key_vault, ...), else its group's. */
const GROUP_ICONS = { database: "sql", file: "folder", vault: "key", python: "code" } as const;
export function connectionIcon(type: string | null | undefined, group: keyof typeof GROUP_ICONS): string {
  return type && hasIcon(type) ? type : GROUP_ICONS[group];
}

// ===== the window's views in the address (nav.ts): open=connections, then at= types | form&type= |
// edit&name= | api. The browser's Back and Forward move between them; a reload comes back to the same one.
const KEYS = ["at", "type", "name"];
const LIST = { at: null, type: null, name: null };
const TYPES = { at: "types", type: null, name: null };
const API = { at: "api", type: null, name: null };
const urlOf = (params: Record<string, string | null>): string => withParams({ ...params, open: "connections" });
/** The open window: what shows the view an address names. */
let shownWindow: { dialog: PageElement; showAt: (url: URL) => void } | null = null;

registerLayer("connections", {
  isOpen: () => Boolean(shownWindow?.dialog.open),
  open: (url) => void drawConnections(url),
  show: (url) => shownWindow?.showAt(url),
  dismiss: () => {
    if (shownWindow) dismissDialog(shownWindow.dialog);
  },
});

/** The Connections page (and Add API: `addApi`), opened by the user: its address pushed. */
export async function openConnections(start: { addApi?: boolean; folder?: string } = {}): Promise<void> {
  if (shownWindow?.dialog.open) return;
  const params = start.addApi ? API : LIST;
  layerOpened("connections", params);
  await drawConnections(new URL(urlOf(params), location.href), start.folder);
}

async function drawConnections(at: URL, folder?: string): Promise<void> {
  const { element: dialog, body, foot, actions, setHeading } = openAreaPage("connections", "Connections");
  const start = { folder };
  // The view drawn now (its address' words), so an address that names it again draws nothing.
  let drawn = "";
  // What the view on screen lets go of when another replaces it (a Python form's editors).
  let leaving: (() => void) | null = null;
  const leave = (key: string): void => {
    drawn = key;
    leaving?.();
    leaving = null;
  };
  const keyOf = (url: URL): string => KEYS.map((k) => url.searchParams.get(k) ?? "").join("|");
  /** The user moved inside the window: the new view's address pushed, then the view drawn. */
  const move = (params: Record<string, string | null>, draw: () => void): void => {
    void go(urlOf(params), "push");
    draw();
  };
  const view = {
    dialog,
    showAt: (url: URL): void => {
      if (keyOf(url) === drawn) return;
      const at = url.searchParams.get("at");
      if (at === "types") void showTypes();
      else if (at === "detail" && url.searchParams.get("name")) void showDetail(url.searchParams.get("name")!);
      else if (at === "api") showApi();
      else if (at === "edit" && url.searchParams.get("name")) void showForm({ edit: url.searchParams.get("name")! });
      else if (at === "form" && url.searchParams.get("type")) void showFormOf(url.searchParams.get("type")!);
      else void showList();
    },
  };
  shownWindow = view;
  watchLayerDialog(dialog, "connections", KEYS, () => {
    leaving?.();
    if (shownWindow?.dialog === dialog) shownWindow = null;
  });
  let drawing = 0;
  /** The heading row's actions: Add connection, on the cards only (Add API is the APIs page's, 2026-11-17). */
  const listActions = (on: boolean): void => {
    actions.replaceChildren(
      ...(on ? [button("Add connection", () => move(TYPES, () => void showTypes()), { icon: "plus", class: "primary" }), button("Import…", () => void openImport("connections").then((done) => done && showList()), { icon: "import" })] : []), // Import: from another project or this computer's saved ones (projectImport.ts)
    );
  };
  const detailUrl = (name: string): string => urlOf({ at: "detail", type: null, name });
  const showList = async (): Promise<void> => {
    leave("||");
    setOverTitle("Connections");
    setHeading("Connections");
    listActions(true);
    listShowing = () => (body.isConnected ? void showList() : (listShowing = null));
    // Drawn again as catalogs load: only the newest draw paints (never twice, never over a view opened
    // meanwhile), and "Loading…" shows only the first time (no flicker).
    const mine = ++drawing;
    if (!body.querySelector(".connection-cards, .empty-note")) {
      clear(foot);
      clear(body, h("p", { class: "hint" }, "Loading…"));
    }
    let found: Card[];
    try {
      found = (await api<{ connections: Card[] }>("/connections/usage")).connections;
    } catch (e) {
      if (mine !== drawing) return;
      clear(foot);
      clear(body, h("p", { class: "status-error" }, (e as Error).message));
      return;
    }
    if (mine !== drawing) return;
    clear(foot);
    const card = (c: Card): HTMLElement =>
      h(
        "li",
        { class: "connection-card-item" },
        // Its colour (connectionColours.ts): the card's edge, and the swatch that chooses it.
        c.connection === "vault" ? null : colourPicker(c.name),
        h(
          "a",
          {
            class: `connection-card fam-${c.connection} st-${c.status}`,
            href: detailUrl(c.name),
            "data-connection": c.name,
            ...(c.connection === "vault" ? {} : { "data-connections": c.name }),
            onclick: (e: MouseEvent) => {
              if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return; // a new tab, as links do
              e.preventDefault();
              move({ at: "detail", type: null, name: c.name }, () => void showDetail(c.name));
            },
          },
          h("span", { class: "connection-card-icon", "aria-hidden": "true" }, icon(connectionIcon(c.template, c.connection))),
          h("span", { class: "connection-card-text" }, h("strong", { class: "connection-card-name" }, c.name), h("span", { class: "connection-card-type" }, c.type ? plain(c.type) : { database: "Database", file: "File", vault: "Key vault", python: "Python" }[c.connection])),
          statusPill(c),
          h("span", { class: "connection-card-calls" }, callsWord(c.calls)),
        ),
      );
    const groups: [string, Card["connection"]][] = [
      ["Databases", "database"],
      ["Files", "file"],
      ["Your own code", "python"],
      ["Key vaults", "vault"],
    ];
    clear(
      body,
      found.length
        ? h(
            "div",
            { class: "connection-groups" },
            ...groups.flatMap(([title, kind]) => {
              const these = found.filter((c) => c.connection === kind);
              return these.length ? [h("h2", { class: "connection-group-title" }, title), h("ul", { class: "connection-cards", "aria-label": title }, ...these.map(card))] : [];
            }),
          )
        : h("p", { class: "empty-note" }, "No connections"),
      // APIs are connections that do not get the connection treatment (the owner, 2026-11-17).
      h("p", { class: "connections-apis-link muted" }, h("button", { type: "button", class: "link", onclick: () => runArea("apis") }, "APIs are on the APIs page")),
    );
  };

  // ===== DETAIL: where it is used, its configuration, its calls =====
  const showDetail = async (name: string): Promise<void> => {
    leave(`detail||${name}`);
    listShowing = null;
    const mine = ++drawing;
    setOverTitle(`Connections › ${name}`);
    setHeading(name);
    listActions(false);
    clear(foot);
    clear(body, h("p", { class: "hint" }, "Loading…"));
    let usage: Usage;
    let listed: Connection | undefined;
    try {
      [usage, listed] = await Promise.all([
        api<Usage>(`/connections/${encodeURIComponent(name)}/usage`),
        api<{ connections: Connection[] }>("/connections").then((r) => r.connections.find((c) => c.name === name)),
      ]);
    } catch (e) {
      if (mine === drawing) failedView(e);
      return;
    }
    if (mine !== drawing) return;
    const c = listed;
    const config = usage.configuration;
    const readOnly = c?.source === "pack";
    const path = encodeURIComponent(name);
    const swatch = config.kind === "vault" ? null : colourPicker(name);
    setHeading(name, " ", statusPill(usage));
    const tested = h("div", { class: "connection-result connection-tested", role: "status" });
    const tools = h(
      "div",
      { class: "connection-detail-tools", role: "toolbar", "aria-label": "Connection" },
      swatch ? h("span", { class: "connection-colour" }, swatch, "Colour") : null,
      c && c.connection === "file" && c.template !== "folder" ? button("Open as grid", () => void openConnection(name), { icon: "rows", class: "primary" }) : null,
      readOnly ? null : button("Edit", () => move({ at: "edit", type: null, name }, () => void showForm({ edit: name })), { icon: "edit" }),
      button("Test", () => void testSaved(name, c && (c.connection === "python" || c.dialect === "dataverse") ? tested : undefined).then(refreshCalls), { icon: "play" }),
      c?.has_catalog ? button("Refresh catalog", () => void refresh(name).then(() => void showDetail(name)), { icon: "import" }) : null,
      config.kind === "vault" ? null : button("Copy for Python", () => void navigator.clipboard.writeText(`conn = sab.connection("${name}")`).then(() => toast("Copied")), { icon: "copy" }),
      readOnly
        ? null
        : button("Remove", () => {
            if (!confirm(config.kind === "vault" ? `Remove the key vault ${name}? Its variables stop being set.` : `Remove the connection ${name}? Its saved passwords go too.`)) return;
            void api(`/blades/${path}`, "DELETE").then(() => {
              void go(urlOf(LIST), "replace");
              void showList();
            }, (e: Error) => toast(e.message, "error"));
          }, { icon: "trash" }),
    );
    // Where it is used: the documents' cells, the canvases' blocks, the open grids.
    const refs = usage.references;
    const used = h(
      "section",
      { class: "connection-section connection-used", "aria-label": "Used in" },
      h("h2", {}, icon("link"), "Used in", h("span", { class: "count" }, String(refs.length))),
      refs.length ? h("ul", { class: "connection-refs" }, ...refs.map((r) => referenceItem(r, name))) : h("p", { class: "empty-note" }, "No references"),
    );
    // Its configuration: never a password's value.
    const configuration = h(
      "dl",
      { class: "connection-config" },
      ...term("Type", c?.type ? plain(c.type) : config.type || config.dialect),
      ...(config.description ? term("Description", config.description) : []),
      ...(config.sign_in ? term("Sign in", config.sign_in) : []),
      ...config.settings.flatMap((f) => term(words(f.name), typeof f.value === "boolean" ? (f.value ? "Yes" : "No") : String(f.value))),
      ...config.passwords.flatMap((p) => term(words(p.name), h("span", { class: p.from === "missing" ? "status-error" : "" }, passwordSource(p)))),
      ...config.variables.flatMap((v) => term(v.name, v.from === "vault" ? `${v.vault ?? ""} (${v.secret ?? ""})` : v.from)),
      ...(config.vault_all ? term("Secrets", "Every secret, each under its own name") : []),
      ...config.vault_entries.flatMap((e) => term(e.variable, h("code", {}, e.secret))),
      ...(config.row_limit === 0 ? term("Rows to open", "Every row") : config.row_limit ? term("Rows to open", config.row_limit.toLocaleString()) : []),
      ...(c ? term("In code", h("code", { class: "connection-in-code" }, inCode(c))) : []),
    );
    const calls = usage.calls;
    /** After a Test: the status and the calls again, the rest (a Test's rows under it) as it is. */
    const refreshCalls = async (): Promise<void> => {
      try {
        const now = await api<Usage>(`/connections/${encodeURIComponent(name)}/usage`);
        if (mine !== drawing) return;
        setHeading(name, " ", statusPill(now));
        body.querySelector(".connection-calls")?.replaceWith(callsList(now.calls));
        const count = body.querySelector(".connection-calls-count");
        if (count) count.textContent = String(now.calls.total);
      } catch {
        /* the next draw says it */
      }
    };
    const counted = callsList(calls);
    clear(
      body,
      h("div", { class: "connection-detail-top" }, backButton("Connections", urlOf(LIST)), crumbs([{ label: "Connections", url: urlOf(LIST) }, { label: name }])),
      tools,
      tested,
      h(
        "div",
        { class: "connection-detail" },
        used,
        h(
          "div",
          { class: "connection-detail-side" },
          h("section", { class: "connection-section", "aria-label": "Configuration" }, h("h2", {}, icon("cog"), "Configuration"), configuration),
          h("section", { class: "connection-section", "aria-label": "Calls this session" }, h("h2", {}, icon("clock"), "Calls this session", h("span", { class: "count connection-calls-count" }, String(calls.total))), counted),
        ),
      ),
    );
  };

  const testSaved = async (name: string, under?: HTMLElement): Promise<void> => {
    toast(`Testing ${name}…`);
    try {
      const r = await api<{ type?: string; found?: string; variables?: string[] } & PythonTested>(`/blades/${encodeURIComponent(name)}/test`, "POST");
      toast(`${name} works: ${worked(r)}.`);
      under?.replaceChildren(...(r.preview ? tablePreview(r.preview) : []));
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  const refresh = async (name: string): Promise<void> => {
    toast(`Refreshing ${name}…`);
    try {
      const r = await api<{ catalog: { tables: number; columns: number } }>(`/blades/${encodeURIComponent(name)}/refresh`, "POST");
      toast(`${name}: ${r.catalog.tables} tables, ${r.catalog.columns} columns`);
      void showList();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  // ===== ADD: the types =====
  /** A view that could not be drawn (a connection removed since, a type no longer offered): said, with
   *  the way back to the list. */
  const failedView = (e: unknown): void => {
    clear(body, h("p", { class: "status-error", role: "alert" }, errorText(e)));
    clear(foot, backButton("Connections", urlOf(LIST)));
  };
  let typesAsked: Promise<Form[]> | null = null;
  const types = (): Promise<Form[]> => (typesAsked ??= api<{ types: Form[] }>("/connections/types").then((r) => r.types, (e: unknown) => {
    typesAsked = null;
    throw e;
  }));

  const showTypes = async (then?: Then): Promise<void> => {
    listActions(false);
    setHeading("Connections");
    // A vault made from a password's form waits outside the address: Back returns to that form.
    if (!then) {
      leave("types||");
      setOverTitle("Connections › Add connection");
    }
    listShowing = null;
    drawing++; // a list draw still on its way paints nothing now
    clear(foot);
    clear(body, h("p", { class: "hint" }, "Loading…"));
    let offered: Form[];
    try {
      offered = await types();
    } catch (e) {
      failedView(e);
      return;
    }
    const open = (t: Form): void => (then ? void showForm({ type: t, then }) : move({ at: "form", type: t.id, name: null }, () => void showForm({ type: t })));
    // A picker: each type's own icon over its name, tinted by its group (connectionIcon).
    const tile = (t: Form): HTMLElement => {
      const made = button(plain(t.label), () => open(t), { class: `connection-type fam-${t.connection}`, icon: connectionIcon(t.id, t.connection) });
      made.dataset.type = t.id;
      return made;
    };
    const group = (title: string, kind: Form["connection"]): HTMLElement[] => [h("h3", {}, title), h("div", { class: "connection-types" }, ...offered.filter((t) => t.connection === kind).map(tile))];
    // From a password's New vault: only vaults, and Back returns to that connection.
    clear(body, ...(then ? [] : [...group("Databases", "database"), ...group("Files", "file"), ...group("Your own code", "python")]), ...group("Key vaults", "vault"));
    foot.append(then ? button("Back", () => void then(null), { icon: "back" }) : backButton("Connections", urlOf(LIST)));
  };

  /** A new connection's form by its type's id (an address: a reload, Forward, a breadcrumb). */
  const showFormOf = async (id: string): Promise<void> => {
    leave(`form|${id}|`);
    clear(foot);
    clear(body, h("p", { class: "hint" }, "Loading…"));
    try {
      const type = (await types()).find((t) => t.id === id);
      if (!type) throw new Error(`There is no connection type called ${id}.`);
      await showForm({ type });
    } catch (e) {
      failedView(e);
    }
  };

  // ===== FORM =====
  const showForm = async (what: { type?: Form; edit?: string; then?: Then }): Promise<void> => {
    listShowing = null;
    drawing++;
    listActions(false);
    setHeading("Connections");
    if (!what.then) leave(what.edit ? `edit||${what.edit}` : `form|${what.type!.id}|`);
    clear(foot);
    let form: Form;
    if (what.edit) {
      try {
        form = await api<Form>(`/connections/${encodeURIComponent(what.edit)}`);
      } catch (e) {
        failedView(e);
        return;
      }
    } else form = structuredClone(what.type!);
    const editing = what.edit ?? null;
    // Where its Back goes, its trail and the window's title (a vault from a password's form has none).
    const backTo = editing ? { label: editing, url: detailUrl(editing) } : { label: "Add connection", url: urlOf(TYPES) };
    const trail = what.then || editing ? null : crumbs([{ label: "Connections", url: urlOf(LIST) }, { label: "Add connection", url: urlOf(TYPES) }, { label: plain(form.label) }]);
    if (!what.then) setOverTitle(editing ? `Connections › Edit ${editing}` : `Connections › Add connection › ${plain(form.label)}`);
    /** Saved: its detail (a new one's, or the one edited, renamed or not), in this entry's place (Back
     *  then goes to where the form was opened from). */
    const savedNow = (saved?: string): void => {
      const now = saved || editing;
      if (!now) {
        void go(urlOf(LIST), "replace");
        void showList();
        return;
      }
      void go(detailUrl(now), "replace");
      void showDetail(now);
    };
    if (form.connection === "python") {
      // Your own Python: three code boxes and the variables they read (pythonConnectionForm.ts).
      showPythonForm({
        body,
        foot,
        form: form as unknown as PythonForm,
        editing,
        backTo,
        trail,
        leaving: (dispose) => (leaving = dispose),
        saved: (saved) => savedNow(saved),
        newVault: (then) => {
          // A vault made from here: this form waits (kept as it is) and comes back to it.
          const kept = [...body.childNodes];
          const keptFoot = [...foot.childNodes];
          void showTypes(async () => {
            body.replaceChildren(...kept);
            foot.replaceChildren(...keptFoot);
            await then();
          });
        },
      });
      return;
    }
    const isVault = form.connection === "vault";
    let code = form.code;
    let fields = form.fields;
    // A database is named after its type until renamed; a file connection after the file chosen.
    const name = h("input", { type: "text", value: form.name ?? (form.connection === "file" ? "" : plain(form.label)), "aria-label": "Name", maxlength: 64 });
    let named = Boolean(form.name);
    name.addEventListener("input", () => (named = name.value.trim() !== "")); // emptied: not named again
    const description = h("input", { type: "text", value: form.description ?? "", "aria-label": "Description", placeholder: "Optional" });
    const fieldsHost = h("div", { class: "connection-fields" });
    const whoHost = h("div", { class: "connection-fields connection-who" });
    const securityHost = h("div", { class: "connection-fields connection-security" });
    const passwords = new Map<string, HTMLInputElement>();
    const codeBox = h("textarea", { class: "mono connection-code", rows: 8, spellcheck: false, "aria-label": "The Python this connection runs" }, code) as HTMLTextAreaElement;
    const result = h("div", { class: "connection-result", role: "status" });

    /** A changed field's value, written into the code by the server; the fields keep their boxes. */
    const fill = async (field: Field, value: string, env?: string | null): Promise<void> => {
      // A certificate file sends its source too: its variable, or null for a plain path.
      const sent = field.env !== undefined ? { value, env: env === undefined ? field.env : env } : field.type === "number" ? Number(value) : value;
      try {
        const answer = await api<{ code: string; settings: Field[] }>("/blades/fill", "POST", { code, values: { [field.id]: sent }, template: form.id || null, name: editing });
        code = answer.code;
        codeBox.value = code;
        // The ids follow the new code; the same settings in the same order keep their boxes.
        if (answer.settings.length === fields.length) fields = fields.map((f, i) => ({ ...f, ...answer.settings[i]!, picker: f.picker }));
        else drawFields(answer.settings.map((s) => ({ ...s, picker: fields.find((f) => f.name === s.name)?.picker ?? (CERTIFICATE_KINDS[s.name] ? "file" : null) })));
        readWhenReady();
      } catch (e) {
        result.replaceChildren(h("p", { class: "status-error" }, (e as Error).message));
      }
    };

    const fileSource = (field: Field, i: number, input: HTMLInputElement): HTMLElement => {
      const label = words(field.name);
      const from = h("select", { "aria-label": `${label} from` }, h("option", { value: "path", selected: !field.env }, "Path"), h("option", { value: "env", selected: Boolean(field.env) }, "From an environment variable")) as HTMLSelectElement;
      const variable = h("input", { type: "text", value: field.env ?? "", placeholder: certificateVariable(name.value.trim() || form.id, field.name), "aria-label": `${label} variable`, spellcheck: false, hidden: !field.env, class: "mono" }) as HTMLInputElement;
      const path = (): string => input.value.trim() || String(fields[i]!.value);
      from.addEventListener("change", () => {
        const mapped = from.value === "env";
        if (mapped && !variable.value.trim()) variable.value = variable.placeholder;
        variable.hidden = !mapped;
        void fill(fields[i]!, path(), mapped ? variable.value.trim() : null);
      });
      variable.addEventListener("change", () => {
        if (variable.value.trim()) void fill(fields[i]!, path(), variable.value.trim());
      });
      return h("span", { class: "field-row field-source" }, from, variable);
    };

    const drawFields = (next: Field[]): void => {
      fields = next;
      const boxes = fields.map((field, i) => {
        if (field.type === "flag") {
          // On or off: True/False in the code, yes/no in a connection string.
          const tick = h("input", { type: "checkbox", checked: ["true", "yes", "1", "on"].includes(String(field.value).toLowerCase()), "aria-label": words(field.name) }) as HTMLInputElement;
          tick.addEventListener("change", () => void fill(fields[i]!, tick.checked ? "yes" : "no"));
          return h("label", { class: "field field-flag" }, tick, h("span", {}, words(field.name)));
        }
        const input = h("input", { type: field.type === "number" ? "number" : "text", value: field.placeholder ? "" : String(field.value), placeholder: String(field.value), "aria-label": words(field.name), spellcheck: false });
        input.addEventListener("change", () => {
          // A file connection is named after its file, picked or typed, until the user names it.
          if (field.picker && !named && input.value.trim()) name.value = stem(input.value.trim());
          void fill(fields[i]!, input.value);
        });
        const browse = field.picker
          ? button("Browse…", () => {
              const suffixes = CERTIFICATE_KINDS[field.name] ?? FILE_KINDS[form.id];
              void chooseFile({ title: field.picker === "folder" ? "Choose folder" : "Choose file", mode: field.picker!, suffixes, start: field.placeholder ? undefined : String(field.value) }).then((path) => {
                if (!path) return;
                input.value = path;
                if (!named) name.value = stem(path);
                void fill(fields[i]!, path);
              });
            }, { icon: "folder" })
          : null;
        const list = field.suggestions.length ? h("datalist", { id: `conn-suggest-${i}` }, ...field.suggestions.map((s) => h("option", { value: s.value }, s.from))) : null;
        if (list) input.setAttribute("list", `conn-suggest-${i}`);
        // A certificate or keystore file: its path as it is, or from an environment variable whose
        // default is the path on this computer (a function app sets the variable to the file there).
        const source = field.env !== undefined ? fileSource(field, i, input) : null;
        return h("label", { class: `field${field.picker ? " wide" : ""}` }, h("span", {}, words(field.name), field.key.toLowerCase() !== field.name.toLowerCase() ? h("span", { class: "hint" }, ` (${field.key})`) : null), h("span", { class: "field-row" }, input, browse), source, list);
      });
      // The same order on every form: where, who, security (a setting the rule does not name stays
      // with "where", after the ones it does, in the code's order).
      const part = (f: Field): string => form.field_places?.[f.name.toLowerCase()]?.part ?? "where";
      const place = (f: Field): number => form.field_places?.[f.name.toLowerCase()]?.rank ?? 9;
      const of = (wanted: string): HTMLElement[] =>
        fields
          .map((f, i) => ({ f, i }))
          .filter(({ f }) => part(f) === wanted)
          .sort((a, b) => place(a.f) - place(b.f) || a.i - b.i)
          .map(({ i }) => boxes[i]!);
      clear(fieldsHost, ...of("where"));
      clear(whoHost, ...of("who"));
      clear(securityHost, ...of("security"));
    };
    drawFields(fields);

    // Each password's source: saved on this computer (the keyring), an environment variable, or a key
    // vault (a vault blade's entry, or a new one added to it). Variables and vault entries are named in
    // the code: secret("WAREHOUSE_PASSWORD"), read from the environment the vault sets.
    let vaults: Vault[] = [];
    // Each vault's secret names, read once in the background (names only: the server never sends a
    // value); null: a vault that does not list them.
    const secretNames = new Map<string, Promise<string[] | null>>();
    const vaultSecrets = (vault: string): Promise<string[] | null> => {
      let reading = secretNames.get(vault);
      if (!reading) {
        reading = api<{ names: Mapping[] | null }>("/connections/vaults/secrets", "POST", { name: vault }).then((r) => (r.names ? r.names.map((n) => n.secret) : null));
        reading.catch(() => secretNames.delete(vault)); // a failed read is tried again next time
        secretNames.set(vault, reading);
      }
      return reading;
    };
    const readVaults = (): Promise<unknown> => api<{ vaults: Vault[] }>("/connections/vaults").then((r) => (vaults = r.vaults), () => undefined);
    const vaultsRead = readVaults();
    // Each password's source as the user chose it (kept when the passwords are drawn again).
    const chosen = new Map<string, string>();
    // A password pointed at a vault: which vault, and the secret's name there (shown when drawn again).
    const pointedAt = new Map<string, string>();
    const secretOf = new Map<string, string>();
    const looksLikeVariable = (s: string): boolean => /^[A-Z][A-Z0-9_]*$/.test(s) && s.includes("_");
    // Each password keeps the word the starter gave it ("Password") while its source renames it in the code.
    const labels = new Map<string, string>(form.secrets.map((s) => [s, s]));
    const label = (s: string): string => words(labels.get(s) ?? s);
    const pointAt = async (secret: string, body: Record<string, unknown>): Promise<void> => {
      try {
        const answer = await api<{ code: string; secret: string }>("/connections/source", "POST", { code, secret, label: labels.get(secret) ?? secret, connection: name.value.trim(), ...body });
        code = answer.code;
        codeBox.value = code;
        form.secrets = form.secrets.map((s) => (s === secret ? answer.secret : s));
        labels.set(answer.secret, labels.get(secret) ?? secret);
        if (body.from === "vault") vaults = (await api<{ vaults: Vault[] }>("/connections/vaults")).vaults;
        chosen.delete(secret);
        chosen.set(answer.secret, String(body.from)); // drawn again as the source just chosen
        if (body.vault) pointedAt.set(answer.secret, String(body.vault));
        if (typeof body.vault_secret === "string") secretOf.set(answer.secret, body.vault_secret);
        passwordsSlot.replaceChildren(drawPasswords() ?? "");
        result.replaceChildren(h("p", { class: "hint" }, `${label(answer.secret)}: ${answer.secret}${body.vault ? ` in ${String(body.vault)}` : ""}`));
      } catch (e) {
        result.replaceChildren(h("p", { class: "status-error" }, (e as Error).message));
      }
    };
    const drawPasswords = (): HTMLElement | null => {
      passwords.clear();
      if (!form.secrets.length) return null;
      const saved = form.summary?.secrets ?? {};
      // Which vault each password was pointed at (an every-secret vault has no entry to show it by).
      return h(
        "fieldset",
        { class: "connection-passwords" },
        // A Power BI workspace's are an app registration's values (two ids and a secret), not passwords alone.
        h("legend", {}, form.dialect === "dax" || form.dialect === "dataverse" ? "App registration" : "Passwords"),
        ...form.secrets.map((s) => {
          const inVault = vaults.find((v) => v.entries.some((e) => e.env === s)) ?? vaults.find((v) => v.name === pointedAt.get(s));
          // A starter may say its passwords come from a key vault first (a Power BI dataset's app registration).
          const vaultOnly = form.secrets_from === "vault only"; // never typed into the app
          const first = (form.secrets_from === "vault" && !editing && labels.get(s) === s) || vaultOnly ? "vault" : "keyring";
          const guess = chosen.get(s) ?? (inVault ? "vault" : looksLikeVariable(s) && !saved[s] ? "env" : first);
          const origin = vaultOnly && guess === "keyring" ? "vault" : guess;
          const from = h("select", { "aria-label": `Where ${label(s)} comes from` }, vaultOnly ? null : h("option", { value: "keyring", selected: origin === "keyring" }, "Saved on this computer"), h("option", { value: "env", selected: origin === "env" }, "An environment variable"), h("option", { value: "vault", selected: origin === "vault" }, "A key vault"));
          const slot = h("span", { class: "field-row" });
          // The box's own label, above it: what to type or pick there.
          const boxLabel = h("span", {});
          const draw = (): void => {
            if (from.value === "keyring") {
              boxLabel.textContent = label(s);
              const input = h("input", { type: "password", autocomplete: "new-password", "aria-label": label(s), placeholder: saved[s] ? "Saved" : "" });
              passwords.set(s, input);
              slot.replaceChildren(input);
            } else if (from.value === "env") {
              boxLabel.textContent = "Variable's name";
              passwords.delete(s);
              const variable = h("input", { type: "text", class: "mono", "aria-label": `${label(s)}: the variable's name`, value: looksLikeVariable(s) ? s : "", placeholder: "WAREHOUSE_PASSWORD", spellcheck: false });
              slot.replaceChildren(variable, button("Use it", () => void pointAt(s, { from: "env", env: variable.value.trim() }), { icon: "check" }));
            } else {
              boxLabel.textContent = "Vault and its entry";
              passwords.delete(s);
              if (!vaults.length) {
                slot.replaceChildren(button("New vault", () => newVault(s), { icon: "plus" }));
                return;
              }
              const vault = h("select", { "aria-label": "Vault" }, ...vaults.map((v) => h("option", { value: v.name, selected: v === inVault }, v.name)));
              const entry = h("select", { "aria-label": "Entry in the vault" });
              const newName = h("input", { type: "text", "aria-label": "The secret's name in the vault", placeholder: "Secret name", spellcheck: false, value: pointedAt.get(s) ? (secretOf.get(s) ?? "") : "" });
              const useTyped = button("Use it", () => void pointAt(s, { from: "vault", vault: vault.value, vault_secret: newName.value.trim() }), { icon: "check" });
              const BY_NAME = "\u0000by-name";
              // The vault's secrets by name (never a value), read in the background: its entries show
              // at once, the rest as they arrive. Picking one applies it; there is nothing else to press.
              let filling = 0;
              const fillEntries = (): void => {
                const mine = ++filling;
                const chosen = vaults.find((v) => v.name === vault.value);
                const mapped = chosen?.entries ?? [];
                const current = mapped.find((e) => e.env === s)?.secret ?? (pointedAt.get(s) === vault.value ? secretOf.get(s) : undefined);
                const paint = (names: string[] | null, state: "reading" | "read" | "unlisted" | "failed"): void => {
                  if (mine !== filling) return;
                  const all = [...new Set([...mapped.map((e) => e.secret), ...(names ?? []), ...(current ? [current] : [])])];
                  const typing = entry.value === BY_NAME || (state !== "reading" && !all.length);
                  clear(
                    entry,
                    h("option", { value: "", disabled: true, selected: !current && !typing }, state === "reading" ? "Reading the vault…" : all.length ? "Choose a secret" : "No secrets listed"),
                    ...all.map((secret) => {
                      const as = mapped.find((e) => e.secret === secret)?.env;
                      return h("option", { value: secret, selected: secret === current && !typing }, as && as !== envFor(secret) ? `${secret} (as ${as})` : secret);
                    }),
                    chosen?.read_only && !chosen.every ? null : h("option", { value: BY_NAME, selected: typing }, "A secret by name…"),
                  );
                  entry.title = state === "unlisted" ? "This vault does not list its secrets" : state === "failed" ? "The vault could not be read" : "";
                  newName.hidden = useTyped.hidden = entry.value !== BY_NAME;
                };
                paint(null, "reading");
                void vaultSecrets(vault.value).then(
                  (names) => paint(names, names === null ? "unlisted" : "read"),
                  () => paint(null, "failed"),
                );
              };
              vault.addEventListener("change", fillEntries);
              entry.addEventListener("change", () => {
                newName.hidden = useTyped.hidden = entry.value !== BY_NAME;
                if (entry.value === BY_NAME) {
                  newName.focus();
                  return;
                }
                const picked = vaults.find((v) => v.name === vault.value)?.entries.find((e) => e.secret === entry.value);
                void pointAt(s, picked ? { from: "vault", vault: vault.value, env: picked.env } : { from: "vault", vault: vault.value, vault_secret: entry.value });
              });
              fillEntries();
              slot.replaceChildren(vault, entry, newName, useTyped);
            }
          };
          from.addEventListener("change", () => {
            chosen.set(s, from.value);
            draw();
          });
          draw();
          return h(
            "div",
            { class: "connection-password" },
            h("label", { class: "field" }, h("span", {}, `${label(s)} comes from`), from),
            h("div", { class: "field password-box" }, boxLabel, slot),
          );
        }),
      );
    };
    void vaultsRead.then(() => passwordsSlot.replaceChildren(drawPasswords() ?? ""));

    /** A vault made from here: this form waits (kept as it is) and comes back with the new vault in its list. */
    const newVault = (secret: string): void => {
      const kept = [...body.childNodes];
      const keptFoot = [...foot.childNodes];
      chosen.set(secret, "vault");
      void showTypes(async () => {
        body.replaceChildren(...kept);
        foot.replaceChildren(...keptFoot);
        await readVaults();
        passwordsSlot.replaceChildren(drawPasswords() ?? "");
      });
    };

    // ===== a vault's secrets: each ticked one becomes an environment variable =====
    // Every secret (a new vault's default): each one under its own name, new ones too; a box renames one.
    const every = h("input", { type: "checkbox", checked: editing ? Boolean(form.vault_all) : true, "aria-label": "Every secret in the vault" }) as HTMLInputElement;
    const mapRows: { secret: string; env: HTMLInputElement; use: HTMLInputElement; row: HTMLElement }[] = [];
    const mapBody = h("tbody", {});
    const mapFilter = h("input", { type: "search", placeholder: "Filter", "aria-label": "Filter the secrets", hidden: true }) as HTMLInputElement;
    /** A secret's row. `mapped`: the variable it was given; none, and it takes the vault's own name. */
    const addMapping = (secret: string, mapped: string | null, use: boolean): void => {
      if (mapRows.some((r) => r.secret === secret)) return;
      const tick = h("input", { type: "checkbox", checked: use, "aria-label": `Use ${secret}` }) as HTMLInputElement;
      const own = envFor(secret);
      const variable = h("input", { type: "text", class: "mono", value: mapped && mapped !== own ? mapped : "", placeholder: own, spellcheck: false, "aria-label": `${secret}: the variable's name` }) as HTMLInputElement;
      variable.addEventListener("input", () => (tick.checked = true));
      const row = h("tr", {}, h("td", {}, tick), h("td", {}, h("code", {}, secret)), h("td", {}, variable));
      mapRows.push({ secret, env: variable, use: tick, row });
      mapBody.insertBefore(row, newRow);
      mapFilter.hidden = mapRows.length <= 10;
    };
    const newSecret = h("input", { type: "text", placeholder: "Secret name", spellcheck: false, "aria-label": "A secret's name in the vault" }) as HTMLInputElement;
    const addTyped = (): void => {
      const secret = newSecret.value.trim();
      if (!secret) return;
      addMapping(secret, null, true);
      newSecret.value = "";
      newSecret.focus();
    };
    newSecret.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        addTyped();
      }
    });
    const newRow = h("tr", { class: "vault-new" }, h("td", {}), h("td", {}, newSecret), h("td", {}, button("Add", addTyped, { icon: "plus" })));
    mapBody.append(newRow);
    mapFilter.addEventListener("input", () => {
      const words = mapFilter.value.toLowerCase();
      for (const r of mapRows) r.row.hidden = Boolean(words) && !`${r.secret} ${r.env.value} ${r.env.placeholder}`.toLowerCase().includes(words);
    });
    for (const m of form.vault_mapping ?? []) if (editing) addMapping(m.secret, m.env, true);
    const mapTable = h("table", { class: "vault-map" }, h("thead", {}, h("tr", {}, h("th", {}, ""), h("th", {}, "In the vault"), h("th", {}, "Environment variable"))), mapBody);
    const showEvery = (): void => void mapTable.classList.toggle("every", every.checked);
    every.addEventListener("change", showEvery);
    showEvery();
    let reading = 0;
    const readVault = async (): Promise<void> => {
      const mine = ++reading;
      result.replaceChildren(h("p", { class: "hint" }, "Reading the vault…"));
      try {
        const r = await api<{ names: Mapping[] | null }>("/connections/vaults/secrets", "POST", { ...sent(), secrets: typed() });
        if (mine !== reading) return; // a newer read (the address changed again) answers instead
        if (r.names === null) {
          result.replaceChildren(h("p", { class: "hint" }, "This vault does not list its secrets: add them by name."));
          newSecret.focus();
          return;
        }
        for (const m of r.names) addMapping(m.secret, null, false);
        result.replaceChildren(h("p", { class: "status-ok" }, `${r.names.length} secret${r.names.length === 1 ? "" : "s"}`));
      } catch (e) {
        if (mine === reading) failed(e, () => void readVault());
      }
    };
    /** Read the vault on its own once it can be: every setting filled in (not a starter's placeholder). */
    const readWhenReady = (): void => {
      if (isVault && fields.every((f) => !f.placeholder)) void readVault();
    };
    const secretsBox = isVault
      ? h(
          "fieldset",
          { class: "connection-passwords vault-secrets" },
          h("legend", {}, "Secrets"),
          h("label", { class: "vault-every" }, every, h("span", {}, "Every secret in the vault")),
          h("div", { class: "field-row" }, button("Read the vault", () => void readVault(), { icon: "import" }), mapFilter),
          mapTable,
        )
      : null;

    // The code edited by hand: read its fields and passwords again.
    codeBox.addEventListener("change", () => {
      code = codeBox.value;
      void api<{ settings: Field[]; secrets: string[]; install_here: string | null; packages?: Form["packages"]; missing?: Missing | null }>("/blades/inspect", "POST", { code, template: form.id || null, name: editing }).then(
        (found) => {
          // The packages the code needs now (a stale "Not installed" once stayed after the code changed).
          form.install_here = found.install_here;
          form.packages = found.packages;
          form.missing = found.missing ?? null;
          drawInstall();
          drawFields(found.settings.map((s) => ({ ...s, picker: fields.find((f) => f.name === s.name)?.picker ?? (CERTIFICATE_KINDS[s.name] ? "file" : null) })));
          if (found.secrets.join() !== form.secrets.join()) {
            form.secrets = found.secrets;
            passwordsSlot.replaceChildren(drawPasswords() ?? "");
          }
          result.replaceChildren();
          readWhenReady();
        },
        (e: Error) => result.replaceChildren(h("p", { class: "status-error" }, e.message)),
      );
    });

    const typed = (): Record<string, string> => Object.fromEntries([...passwords].filter(([, input]) => input.value).map(([s, input]) => [s, input.value]));
    const sent = (): Record<string, unknown> => ({
      name: name.value.trim(),
      description: description.value.trim(),
      kind: form.kind,
      template: form.id || null,
      dialect: form.dialect,
      variable: form.variable,
      code,
      catalog: form.catalog,
      // Every secret: only the renamed ones are kept (the rest take their own names each time).
      ...(form.connection === "database" ? { row_limit: allRows.checked ? 0 : rowLimit.value.trim() ? Number(rowLimit.value) : null } : {}),
      ...(isVault
        ? {
            vault_all: every.checked,
            // A box left empty: the vault's own name. Every secret keeps only the ones given another.
            vault_mapping: mapRows
              .filter((r) => (every.checked ? r.env.value.trim() !== "" && r.env.value.trim() !== envFor(r.secret) : r.use.checked))
              .map((r) => ({ env: r.env.value.trim() || envFor(r.secret), secret: r.secret })),
          }
        : {}),
    });
    const failed = (e: unknown, again?: () => void): void => {
      result.replaceChildren(h("p", { class: "status-error" }, errorText(e)));
      // A run that stopped on a missing package: the prompt, then the run again once it is in.
      promptForError(e, { then: again });
    };
    const test = async (): Promise<void> => {
      result.replaceChildren(h("p", { class: "hint" }, isVault ? "Reading…" : "Connecting…"));
      try {
        const r = await api<{ type?: string; found?: string; variables?: string[]; name?: string; preview?: Preview; preview_error?: string }>("/connections/test", "POST", { ...sent(), secrets: typed() });
        // Tested before it was named: the file's own name, as the server used it.
        if (r.name && !name.value.trim()) name.value = r.name;
        result.replaceChildren(
          h("p", { class: "status-ok" }, `It works: ${worked(r)}.`),
          // A table's first rows (a Dataverse environment's), or a file's.
          ...(r.preview ? ("table" in r.preview ? tablePreview(r.preview as unknown as TablePreview) : previewOf(r.preview)) : []),
          r.preview_error ? h("p", { class: "status-error" }, `Its rows could not be read: ${r.preview_error}`) : "",
        );
      } catch (e) {
        failed(e, () => void test());
      }
    };
    const save = async (): Promise<void> => {
      try {
        const body = { ...sent(), secrets: typed() };
        await (editing ? api(`/connections/${encodeURIComponent(editing)}`, "PUT", body) : api("/connections", "POST", body));
        toast(`Saved ${name.value.trim()}.`);
        if (what.then) what.then(name.value.trim());
        else savedNow(name.value.trim());
      } catch (e) {
        failed(e);
      }
    };

    // Sign in (SQL Server, Azure SQL): each way is its own code; switching keeps the values typed so far.
    const ways = form.sign_ins ?? [];
    const current = Math.max(0, ways.findIndex((w) => code.toLowerCase().includes(w.mark.toLowerCase())));
    const signInSelect = h("select", { "aria-label": "Sign in" }, ...ways.map((w, i) => h("option", { value: String(i), selected: i === current }, w.label))) as HTMLSelectElement;
    signInSelect.addEventListener("change", () => void switchSignIn(ways[Number(signInSelect.value)]!));
    const signIn = ways.length > 1 ? h("label", { class: "field" }, h("span", {}, "Sign in"), signInSelect) : null;
    const switchSignIn = async (way: { code: string }): Promise<void> => {
      const typedSoFar = new Map(fields.filter((f) => !f.placeholder).map((f) => [f.name, f.value]));
      try {
        const next = await api<{ settings: Field[]; secrets: string[]; install_here: string | null; packages?: Form["packages"]; missing?: Missing | null }>("/blades/inspect", "POST", { code: way.code, template: form.id || null, name: editing });
        const keep = Object.fromEntries(next.settings.filter((s) => typedSoFar.has(s.name) && s.name !== "driver").map((s) => [s.id, typedSoFar.get(s.name)]));
        const answer = Object.keys(keep).length
          ? await api<{ code: string; settings: Field[] }>("/blades/fill", "POST", { code: way.code, values: keep, template: form.id || null, name: editing })
          : { code: way.code, settings: next.settings };
        code = answer.code;
        codeBox.value = code;
        drawFields(answer.settings.map((s) => ({ ...s, picker: fields.find((f) => f.name === s.name)?.picker ?? (CERTIFICATE_KINDS[s.name] ? "file" : null) })));
        form.secrets = next.secrets;
        labels.clear();
        for (const secret of next.secrets) labels.set(secret, secret);
        passwordsSlot.replaceChildren(drawPasswords() ?? "");
        // The packages are this way's own (Dataverse's As you needs azure-identity; its others do not).
        form.install_here = next.install_here;
        form.packages = next.packages;
        form.missing = next.missing ?? null;
        drawInstall();
        result.replaceChildren();
      } catch (e) {
        failed(e);
      }
    };
    // A database: how many rows a table opens with as a grid (the grid says when the source has more).
    const rowLimit = h("input", { type: "number", min: 1, step: 1, value: form.row_limit ? String(form.row_limit) : "", placeholder: "10000", "aria-label": "Rows to open" }) as HTMLInputElement;
    // Load all rows (the owner, 2026-11-16: "a box on the connection to load all rows"): every table opens whole
    // (row_limit 0); the number box rests.
    const allRows = h("input", { type: "checkbox", checked: form.row_limit === 0, "aria-label": "Load all rows" }) as HTMLInputElement;
    const restLimit = (): void => {
      rowLimit.disabled = allRows.checked;
    };
    allRows.addEventListener("change", restLimit);
    restLimit();
    const rowLimitField =
      form.connection === "database"
        ? h("div", { class: "field row-limit-field" }, h("label", { class: "field" }, h("span", {}, "Rows to open"), rowLimit), h("label", { class: "check" }, allRows, "Load all rows"))
        : null;
    const passwordsSlot = h("div", {}, drawPasswords() ?? "");
    const installSlot = h("div", {});
    // A driver that is not installed: the prompt in the user's face (missingPackages.ts); after Not now a
    // small Install reminder stays, with the command in view for the user's own Python too. Installed,
    // the code is read again and the note goes.
    const drawInstall = (): void => {
      const missing = form.missing;
      if (!missing) {
        installSlot.replaceChildren();
        return;
      }
      const again = async (): Promise<void> => {
        const found = await api<{ install_here: string | null; packages?: Form["packages"]; missing?: Missing | null }>("/blades/inspect", "POST", { code, template: form.id || null, name: editing });
        form.install_here = found.install_here;
        form.packages = found.packages;
        form.missing = found.missing ?? null;
        drawInstall();
      };
      installSlot.replaceChildren(h("p", { class: "hint install-note" }, noticeMissing(missing, { then: again }), h("code", {}, missing.command)));
    };
    drawInstall();
    clear(
      body,
      trail,
      h("h3", {}, editing ? `Edit ${editing}` : isVault ? `New ${plain(form.label)}` : `New ${plain(form.label)} connection`),
      form.note ? h("p", { class: "hint" }, form.note) : null,
      h("label", { class: "field" }, h("span", {}, "Name"), name),
      h("label", { class: "field" }, h("span", {}, "Description"), description),
      fieldsHost,
      signIn,
      whoHost,
      passwordsSlot,
      securityHost,
      rowLimitField,
      secretsBox,
      installSlot,
      result,
      h("details", { class: "connection-code-box" }, h("summary", {}, "Python code"), codeBox),
    );
    foot.append(
      what.then ? button("Back", () => void showTypes(what.then), { icon: "back" }) : backButton(backTo.label, backTo.url),
      button(isVault ? "Test" : "Test connection", () => void test(), { icon: "play" }),
      button("Save", () => void save(), { icon: "save", class: "primary" }),
    );
    name.focus();
    name.select();
    readWhenReady(); // a vault opened to edit is read at once; a new one when its address is filled in
  };

  // ===== Add API (addApi.ts): an OpenAPI document or a form; then the connection's own form =====
  const showApi = (): void => {
    listActions(false);
    setHeading("Connections");
    leave("api||");
    setOverTitle("Connections › Add API");
    listShowing = null;
    drawing++;
    showAddApi({
      body,
      foot,
      folder: start.folder,
      backTo: { label: "Connections", url: urlOf(LIST) },
      // The connection it made: its own form, in Add API's place (Back goes to where Add API was opened from).
      added: (name) => {
        void go(urlOf({ at: "edit", type: null, name }), "replace");
        void showForm({ edit: name });
      },
    });
  };

  view.showAt(at);
}
