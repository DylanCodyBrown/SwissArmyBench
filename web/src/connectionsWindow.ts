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
 *            run) and its calls this session. Add connection, Import… and Find connections on this computer…
 *            (findConnections.ts) in the heading row
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
import { openOnPage } from "./workbenchPages";
import { showAddApi } from "./addApi";
import { api, onNotice } from "./api";
import { slotLine, slotsSection } from "./connectionSlots";
import { type Figures, figuresTerms, figuresTitle, usualWords } from "./callFigures";
import { openAreaPage, type PageElement } from "./areaPage";
import { button, clear, h, hasIcon, icon, recall, remember, toast } from "./dom";
import { accessSection } from "./connectionAccess";
import { tablesSection } from "./connectionTree";
import { chooseFile } from "./fileChooser";
import { clearError, errorHere, errorMark, errorNote, showError, warningNote } from "./errorNote";
import { forgetVariables, namesVariable, variableBox } from "./variableBox";
import { busy, busyClick, loadingBlock } from "./loading";
import { sandboxPanel } from "./dataSandbox";
import { openImport } from "./projectImport";
import { openFindConnections } from "./findConnections";
import { pickSheets } from "./openFile";
import { type Missing, noticeMissing, promptForError, reminder } from "./missingPackages";
import { touring } from "./tourButton";
import { colourPicker } from "./connectionColours";
import { kindIcon } from "./kindColours";
import { backButton, crumbs, dismissDialog, go, homeWindow, layerOpened, registerLayer, setOverTitle, visit, watchLayerDialog, withParams } from "./nav";
import { pythonWorked, showPythonForm, tablePreview, type PythonForm, type PythonTested, type TablePreview } from "./pythonConnectionForm";
import { emptyState } from "./emptyState";

interface Field {
  id: string;
  name: string;
  key: string;
  value: string | number | boolean;
  type: "text" | "number" | "flag";
  placeholder: boolean;
  picker: "file" | "folder" | null;
  suggestions: { value: string; from: string }[];
  /** A setting that may come from an environment variable (a certificate or keystore file; every setting of
   *  the lake and SharePoint kinds): the variable it is read from (null: as typed here). */
  env?: string | null;
  /** The variable the form offers for it (SHAREPOINT_TENANT_ID), editable. */
  suggested_env?: string;
  /** Its one box's text (12.7): the value, `${NAME}` where the code reads a variable. */
  text?: string;
}

/** The lake and SharePoint kinds (domain/lakes.py): a group of their own on the page. */
const LAKE_GROUP = "Lakes and SharePoint";

/** The connection kinds this browser opened last, newest first (Add connection puts them first). */
const RECENT_KINDS = "connections.recentKinds";
function recentKinds(): string[] {
  try {
    const kept = JSON.parse(recall(RECENT_KINDS) ?? "[]") as unknown;
    return Array.isArray(kept) ? kept.filter((k): k is string => typeof k === "string").slice(0, 6) : [];
  } catch {
    return [];
  }
}
function rememberKind(id: string): void {
  remember(RECENT_KINDS, JSON.stringify([id, ...recentKinds().filter((k) => k !== id)].slice(0, 6)));
}
const LAKE_KINDS = new Set(["onelake", "datalake", "delta", "sharepoint", "sharepoint_docs"]);
/** Those whose own code reads their tables: sab.read, and Test shows a table's first rows. */
const readsByCode = (dialect: string): boolean => dialect === "dataverse" || LAKE_KINDS.has(dialect);

/** What a connection leans on that only this computer has (domain/portability.py): an amber note (the owner,
 * 2026-11-17: "any connector that does not scale to a function app needs to carry a warning that it will
 * only work on your machine"). */
interface LocalNote {
  key: string;
  reason: string;
  instead: string;
  words: string;
}

/** The notes as the form, the card's detail and the export say them: the one warning (errorNote.ts, 9.5), each
 *  in its own words ("Only works on your machine: ..."). */
function localNotes(notes: LocalNote[] | undefined, extra = ""): HTMLElement | null {
  if (!notes?.length) return null;
  return h("div", { class: `local-only ${extra}`.trim() }, ...notes.map((n) => warningNote({ what: n.words, dismiss: false, agent: false })));
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
  sign_ins?: { label: string; mark: string; code: string; local?: LocalNote[]; note?: string }[];
  /** What the kind itself leans on that only this computer has (an ODBC driver, a file on this disk). */
  local?: LocalNote[];
  /** The note a password saved on this computer (the keyring) carries. */
  keyring_note?: LocalNote;
  /** Where a new one's passwords are first offered from: "vault" (a Power BI dataset's app registration). */
  secrets_from?: string;
  /** SQL Server and Azure SQL (domain/sql_server.py): settings that may come from an environment variable,
   *  those folded under Options, and those that offer a choice. */
  env_settings?: string[];
  options?: string[];
  choices?: Record<string, string[]>;
}

/** The part of the form a setting belongs to (where, who, security, options), and its rank there. */
const fieldPart = (form: Form, f: Field): string => (form.options?.includes(f.name.toLowerCase()) ? "options" : (form.field_places?.[f.name.toLowerCase()]?.part ?? "where"));
const fieldPlace = (form: Form, f: Field): number => form.field_places?.[f.name.toLowerCase()]?.rank ?? 9;

/** One part's boxes, in the form's order (a setting the form does not rank keeps the code's order). */
function partBoxes(form: Form, fields: Field[], boxes: HTMLElement[], wanted: string): HTMLElement[] {
  return fields
    .map((f, i) => ({ f, i }))
    .filter(({ f }) => fieldPart(form, f) === wanted)
    .sort((a, b) => fieldPlace(form, a.f) - fieldPlace(form, b.f) || a.i - b.i)
    .map(({ i }) => boxes[i]!);
}

interface Mapping {
  env: string;
  secret: string;
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
  /** How it lists and reads its tables (domain/connection_tables.py); none: a key vault. */
  tables_kind?: string | null;
}

type Status = "works" | "ready" | "needs" | "failing" | "resuming";

interface Calls {
  total: number;
  by_kind: Record<string, number>;
  last_used: number | null;
  last_kind: string | null;
  last_ok: boolean | null;
  /** The open project's running figures for it (services/call_stats.py), null while it has none. */
  figures?: Figures | null;
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
  /** The last run's error in plain words (SQL Server's say the fix). */
  error?: string;
  /** What the server said it is (SQL Server's Test): driver and sign-in, version, a case-sensitive collation. */
  about?: string[];
  /** What it writes (domain/write_capability.py): its Write starters, or why it is read-only. */
  writes?: Writes | null;
  /** How it lists and reads its tables; "api": an API's (the APIs page has those, not this page). */
  tables_kind?: string | null;
  /** What it leans on that only this computer has: the card's "Only works on your machine". */
  local?: LocalNote[];
  /** Its code is the app's earlier SQL Server code on pyodbc: Update to the new driver. */
  update_driver?: boolean;
}

interface Writes {
  writable: boolean;
  operations: string[];
  starters: string[];
  how: string;
  note: string;
  reason: string;
  words: string;
}

/** A connection's writes in its detail: its operations and its Write starter (its name: the Blades page has
 *  it), or why not. */
function writesTerm(w: Writes | null | undefined): HTMLElement[] {
  if (!w) return [];
  if (!w.writable) return term("Read-only", w.reason);
  const said = w.starters.length ? `${w.operations.join(", ")} (${w.starters.join(", ")})` : w.how;
  return term("Writes", h("span", { class: "connection-writes-list" }, said, w.note ? h("span", { class: "hint" }, ` (${w.note})`) : ""));
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

const STATUS_WORDS: Record<Status, string> = { works: "Works", ready: "Ready", needs: "Needs a password", failing: "Failing", resuming: "Resuming" };
const CALL_WORDS: Record<string, string> = { catalog: "Catalog loads", query: "Queries", read: "Table reads", test: "Tests", connect: "Connects" };

/** A card's status, in a word (the reason on hover: the missing passwords, the catalog's failure). */
function statusPill(c: Card): HTMLElement {
  const why = c.status === "needs" ? c.missing.join(", ") : c.status === "failing" || c.status === "resuming" ? c.error || (c.catalog_state?.error ?? "") : "";
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
  const usual = usualWords(calls.figures);
  return `${calls.total.toLocaleString()} call${calls.total === 1 ? "" : "s"}${calls.last_used ? ` · ${ago(calls.last_used)}` : ""}${usual ? ` · ${usual}` : ""}`;
}

/** Where a reference opens: the Workbench page's own (its documents and cells), else this one. */
let cellOpener: ((path: string, cell: number | null) => Promise<void>) | null = null;

/** The Workbench: a reference opens its cell here (workbenchPage.ts goToCell). */
export function setCellOpener(open: (path: string, cell: number | null) => Promise<void>): void {
  cellOpener = open;
}


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
  // On its page: a notebook's cell on the Notebooks page, a script on the Scripts page (workbenchPages.ts).
  await openOnPage(ref.document, { cell: ref.cell ?? null });
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
        onclick: () => void openReference(ref).catch((e: Error) => errorHere(e)),
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
    ...figuresTerms(calls.figures),
  );
}

/** How code names a connection: a Power BI workspace's DAX cells, your own Python's sab.read, a key
 *  vault's sab.blade, a database's sab.connection and SQL cell. */
function inCode(c: Connection): string {
  const cell = /\s/.test(c.name) ? `"${c.name}"` : c.name;
  if (c.dialect === "dax") return `sab.dax("${c.name}/<dataset>", …)  ·  %%dax ${c.name}/<dataset>`;
  if (c.connection === "vault") return `sab.blade("${c.name}")`;
  if (c.connection === "python" || readsByCode(c.dialect)) return `sab.connection("${c.name}")  ·  sab.read("${c.name}", table)${c.dialect !== "sharepoint" && c.dialect !== "sharepoint_docs" && c.connection !== "python" ? `  ·  %%sql ${cell}` : ""}`;
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
    errorHere(e);
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
    errorHere(e);
  }
}

/** The Connections page shows no APIs (the owner, 2026-11-17: "APIs are connections but they dont get
 *  the connection treatment here"): the APIs page has them. */
function withoutApis<T extends { tables_kind?: string | null }>(found: T[]): T[] {
  return found.filter((c) => c.tables_kind !== "api");
}

/** A connection's detail: its tables (connectionTree.ts) above where it is used; a key vault has none. */
function withTables(name: string, c: Connection | undefined, used: HTMLElement): HTMLElement {
  if (!c?.tables_kind || c.tables_kind === "api") return used;
  return h("div", { class: "connection-detail-main" }, tablesSection(name, shownAsTab), used);
}

/** A Dataverse connection saved for its Web API: one click moves it to its SQL endpoint. */
function dataverseSwitch(c: Connection | undefined, after: () => void): HTMLElement | null {
  if (c?.tables_kind !== "dataverse_web") return null;
  return button("Web API (switch to the SQL endpoint)", () => {
    void api(`/connections/${encodeURIComponent(c.name)}/sql-endpoint`, "POST").then(after, (e: Error) => errorHere(e));
  }, { icon: "sql" });
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
export async function openConnections(start: { addApi?: boolean; folder?: string; types?: boolean; detail?: string } = {}): Promise<void> {
  if (shownWindow?.dialog.open) return;
  const params = start.detail ? { at: "detail", type: null, name: start.detail } : start.addApi ? API : start.types ? TYPES : LIST;
  layerOpened("connections", params);
  await drawConnections(new URL(urlOf(params), location.href), start.folder);
}

/** Add connection's types, straight away (the "+" tab's Query from: Add a connection…). */
export function openConnectionTypes(): Promise<void> {
  return openConnections({ types: true });
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
      else if (at === "sandbox") showSandbox();
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
      ...(on ? [button("Add connection", () => move(TYPES, () => void showTypes()), { icon: "plus", class: "primary" }), button("Import…", () => void openImport("connections").then((done) => done && showList()), { icon: "import" }), button("Find connections on this computer…", () => void openFindConnections().then((made) => void (made.length && showList())), { icon: "desktop" })] : []), // Import: from another project or this computer's saved ones (projectImport.ts); Find: the tools this computer has (findConnections.ts)
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
    // meanwhile), and the placeholder shows only the first time (no flicker).
    const mine = ++drawing;
    if (!body.querySelector(".connection-cards, .empty-note")) {
      clear(foot);
      clear(body, loadingBlock("Loading the connections…"));
    }
    let found: Card[];
    try {
      // Key vaults are the Variables page's (a thing with no tables is not a connection: the owner, 2026-11-17).
      found = withoutApis((await api<{ connections: Card[] }>("/connections/usage")).connections).filter((c) => c.connection !== "vault");
    } catch (e) {
      if (mine !== drawing) return;
      clear(foot);
      clear(body, errorNote(e));
      return;
    }
    if (mine !== drawing) return;
    clear(foot);
    const card = (c: Card): HTMLElement =>
      h(
        "li",
        { class: "connection-card-item" },
        // Its colour (connectionColours.ts) is the card's own highlight: its border and a tint of its box (the
        // owner, 2026-11-21: "the highlighting for the box of the connection itself"); chosen on its detail.
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
          h("span", { class: "connection-card-marks" }, statusPill(c)),
          h("span", { class: "connection-card-calls", title: c.calls.figures?.count ? figuresTitle(c.calls.figures) : undefined }, callsWord(c.calls)),
          c.about?.length ? h("span", { class: "connection-card-about" }, c.about[0]) : null,
          c.local?.length ? h("span", { class: "connection-card-local" }, errorMark(c.local[0]!.words, { level: "warning", title: c.local.map((n) => n.words).join("\n") })) : null,
          // "Running 3 of 8 · 1 waiting", live, while anything runs or waits (connectionSlots.ts).
          c.connection === "vault" ? null : slotLine(c.name),
        ),
      );
    // The project's Sandbox (2026-11-21): a real connection kind, local test data, never live: its own card.
    const sandboxCard = (c: Card & { words?: string; tables?: number; log_words?: string }): HTMLElement =>
      h("li", { class: "connection-card-item" },
        h("a", {
          class: "connection-card fam-sandbox st-works",
          href: urlOf({ at: "sandbox", type: null, name: null }),
          "data-connection": c.name,
          "data-connections": c.name,
          onclick: (e: MouseEvent) => {
            if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
            e.preventDefault();
            move({ at: "sandbox", type: null, name: null }, () => showSandbox());
          },
        },
          h("span", { class: "connection-card-icon", "aria-hidden": "true" }, icon("sandbox")),
          h("span", { class: "connection-card-text" }, h("strong", { class: "connection-card-name" }, c.name), h("span", { class: "connection-card-type" }, `Sandbox · ${c.tables ?? 0} tables`)),
          h("span", { class: "connection-card-calls" }, c.log_words ?? ""),
          h("span", { class: "connection-card-about sandbox-never-live" }, c.words ?? ""),
        ));
    const groups: [string, (c: Card) => boolean][] = [
      ["Databases", (c) => c.connection === "database" && !LAKE_KINDS.has(c.tables_kind ?? "")],
      [LAKE_GROUP, (c) => LAKE_KINDS.has(c.tables_kind ?? "")],
      ["Files", (c) => c.connection === "file"],
      ["Your own code", (c) => c.connection === "python"],
    ];
    clear(
      body,
      found.length
        ? h(
            "div",
            { class: "connection-groups" },
            ...groups.flatMap(([title, belongs]) => {
              const these = found.filter(belongs);
              return these.length ? [h("h2", { class: "connection-group-title" }, title), h("ul", { class: "connection-cards", "aria-label": title }, ...these.map(card))] : [];
            }),
            ...(found.some((c) => (c.connection as string) === "sandbox") ? [h("h2", { class: "connection-group-title" }, "Sandbox"), h("ul", { class: "connection-cards", "aria-label": "Sandbox" }, ...found.filter((c) => (c.connection as string) === "sandbox").map(sandboxCard))] : []),
          )
        : emptyState({ icon: "plug", line: "A connection lists a database's or a folder's tables, so DuckDB SQL can read them by name.", action: { label: "Add connection", icon: "plus", run: () => move(TYPES, () => void showTypes()) } }),
      // APIs are not here (the owner, 2026-11-17); the line pointing to their page went: the rail has them
      // beside Connections ("its not needed", 2026-11-18).
    );
  };

  // ===== the Sandbox's own page: its tables, the change log, Reset (dataSandbox.ts's panel) =====
  const showSandbox = (): void => {
    leave("sandbox||");
    listShowing = null;
    ++drawing;
    setOverTitle("Connections › Sandbox");
    setHeading("Sandbox");
    listActions(false);
    clear(foot);
    clear(body, h("p", { class: "sandbox-never-live" }, icon("sandbox"), " Local test data, never live: the project's own copy in .sab/sandbox/, written only by the sandbox. Never exported as a connection."), sandboxPanel());
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
    clear(body, loadingBlock(`Loading ${name}…`));
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
    const readOnly = c?.source === "starter";
    const path = encodeURIComponent(name);
    const swatch = config.kind === "vault" ? null : colourPicker(name);
    setHeading(name, " ", statusPill(usage));
    const tested = h("div", { class: "connection-result connection-tested", role: "status" });
    const tools = h(
      "div",
      { class: "connection-detail-tools", role: "toolbar", "aria-label": "Connection" },
      swatch ? h("span", { class: "connection-colour" }, swatch, "Colour") : null,
      c && c.connection === "file" && c.template !== "folder" ? button("Open as grid", busyClick("Opening…", () => openConnection(name)), { icon: "rows", class: "primary" }) : null,
      readOnly ? null : button("Edit", () => move({ at: "edit", type: null, name }, () => void showForm({ edit: name })), { icon: "edit" }),
      button("Test", busyClick("Testing…", () => testSaved(name, tested, Boolean(c && (c.connection === "python" || readsByCode(c.dialect)))).then(() => (c?.dialect === "sqlserver" ? showDetail(name) : refreshCalls()))), { icon: "play" }),
      // SQL Server's foreign keys into the ERD, as a Power BI dataset's relationships.
      c?.dialect === "sqlserver" && c.connection === "database" ? button("Import relationships", busyClick("Reading…", () => importRelationships(name)), { icon: "diagram" }) : null,
      dataverseSwitch(c, () => void showDetail(name)),
      // The app's earlier SQL Server code (pyodbc and an ODBC driver): made again on mssql-python, its settings kept.
      usage.update_driver && !readOnly
        ? button("Update to the new driver", busyClick("Updating…", () => api(`/connections/${path}/update-driver`, "POST").then(() => {
            toast(`${name} now uses mssql-python: no ODBC driver.`);
            void showDetail(name);
          }, (e: Error) => tested.replaceChildren(errorNote(e)))), { icon: "import", class: "primary" })
        : null,
      c?.has_catalog ? button("Refresh catalog", busyClick("Refreshing…", () => refresh(name, tested).then(() => void showDetail(name))), { icon: "import" }) : null,
      config.kind === "vault" ? null : button("Copy for Python", () => void navigator.clipboard.writeText(`conn = sab.connection("${name}")`).then(() => toast("Copied")), { icon: "copy" }),
      readOnly
        ? null
        : button("Remove", () => {
            if (!confirm(config.kind === "vault" ? `Remove the key vault ${name}? Its variables stop being set.` : `Remove the connection ${name}? Its saved passwords go too.`)) return;
            void api<{ relationships_removed?: number }>(`/blades/${path}`, "DELETE").then((gone) => {
              // The relationships its tables held went with it (the ERD redraws on the server's notice).
              const n = gone.relationships_removed ?? 0;
              if (n) toast(`Removed ${n} relationship${n === 1 ? "" : "s"} that came from ${name}.`);
              void go(urlOf(LIST), "replace");
              void showList();
            }, (e: Error) => errorHere(e));
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
      ...(usage.about?.length ? term("Server", h("span", { class: "connection-about" }, ...usage.about.map((line) => h("span", {}, line)))) : []),
      ...config.settings.flatMap((f) => term(words(f.name), typeof f.value === "boolean" ? (f.value ? "Yes" : "No") : String(f.value))),
      ...config.passwords.flatMap((p) => term(words(p.name), p.from === "missing" ? errorMark(passwordSource(p)) : h("span", {}, passwordSource(p)))),
      ...config.variables.flatMap((v) => term(v.name, v.from === "vault" ? `${v.vault ?? ""} (${v.secret ?? ""})` : v.from)),
      ...(config.vault_all ? term("Secrets", "Every secret, each under its own name") : []),
      ...config.vault_entries.flatMap((e) => term(e.variable, h("code", {}, e.secret))),
      ...(config.row_limit === 0 ? term("Rows to open", "Every row") : config.row_limit ? term("Rows to open", config.row_limit.toLocaleString()) : []),
      ...(c ? term("In code", h("code", { class: "connection-in-code" }, inCode(c))) : []),
      ...writesTerm(usage.writes),
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
      localNotes(usage.local, "connection-local"),
      tested,
      usage.error && (usage.status === "failing" || usage.status === "resuming") ? errorNote(usage.error, { where: name, dismiss: false }) : null,
      h(
        "div",
        { class: "connection-detail" },
        withTables(name, c, used),
        h(
          "div",
          { class: "connection-detail-side" },
          h("section", { class: "connection-section", "aria-label": "Configuration" }, h("h2", {}, icon("cog"), "Configuration"), configuration),
          config.kind === "vault" ? null : accessSection(name),
          config.kind === "vault" ? null : slotsSection(name),
          h("section", { class: "connection-section", "aria-label": "Calls this session" }, h("h2", {}, icon("clock"), "Calls this session", h("span", { class: "count connection-calls-count" }, String(calls.total))), counted),
        ),
      ),
    );
  };

  /** A saved connection's Test: its rows under the tools when it reads them by code (`rows`); a failure there. */
  const testSaved = async (name: string, under: HTMLElement, rows: boolean): Promise<void> => {
    under.replaceChildren();
    try {
      const r = await api<{ type?: string; found?: string; variables?: string[] } & PythonTested>(`/blades/${encodeURIComponent(name)}/test`, "POST");
      toast(`${name} works: ${worked(r)}.`);
      if (rows) under.replaceChildren(...(r.preview ? tablePreview(r.preview) : []));
    } catch (e) {
      under.replaceChildren(errorNote(e));
    }
  };

  const refresh = async (name: string, said: HTMLElement): Promise<void> => {
    said.replaceChildren();
    try {
      const r = await api<{ catalog: { tables: number; columns: number } }>(`/blades/${encodeURIComponent(name)}/refresh`, "POST");
      toast(`${name}: ${r.catalog.tables} tables, ${r.catalog.columns} columns`);
      void showList();
    } catch (e) {
      said.replaceChildren(errorNote(e));
    }
  };

  // ===== ADD: the types =====
  /** A view that could not be drawn (a connection removed since, a type no longer offered): said, with
   *  the way back to the list. */
  const failedView = (e: unknown): void => {
    clear(body, errorNote(e));
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
    clear(body, loadingBlock("Loading the connection types…"));
    let offered: Form[];
    try {
      offered = await types();
    } catch (e) {
      failedView(e);
      return;
    }
    // The kinds used last come first in their group (this browser's memory: a convenience, nothing kept).
    const recent = recentKinds();
    const rank = (t: Form): number => {
      const at = recent.indexOf(t.id);
      return at < 0 ? recent.length : at;
    };
    const open = (t: Form): void => {
      rememberKind(t.id);
      if (then) void showForm({ type: t, then });
      else move({ at: "form", type: t.id, name: null }, () => void showForm({ type: t }));
    };
    // A picker: each type's own icon over its name, tinted by its group (connectionIcon).
    const tile = (t: Form): HTMLElement => {
      const made = button(plain(t.label), () => open(t), { class: `connection-type fam-${t.connection}`, icon: connectionIcon(t.id, t.connection) });
      made.dataset.type = t.id;
      made.dataset.words = `${plain(t.label)} ${t.id} ${t.group ?? ""}`.toLowerCase();
      if (recent.includes(t.id)) made.classList.add("recent");
      return made;
    };
    const group = (title: string, belongs: (t: Form) => boolean): HTMLElement[] => [
      h("h3", {}, title),
      h("div", { class: "connection-types" }, ...offered.filter(belongs).sort((a, b) => rank(a) - rank(b)).map(tile)),
    ];
    const of = (kind: Form["connection"]) => (t: Form): boolean => t.connection === kind && t.group !== LAKE_GROUP;
    // Type to filter (the owner, 2026-11-19: more than 30 tiles); Enter opens the first one left.
    const none = h("p", { class: "empty-note", hidden: true }, "No connection type matches.");
    const search = h("input", {
      type: "search",
      class: "connection-type-search",
      placeholder: "Search the types",
      "aria-label": "Search the connection types",
      oninput: () => {
        const words = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
        let left = 0;
        for (const types of body.querySelectorAll<HTMLElement>(".connection-types")) {
          let shown = 0;
          for (const t of types.querySelectorAll<HTMLElement>(".connection-type")) {
            t.hidden = !words.every((w) => (t.dataset.words ?? "").includes(w));
            if (!t.hidden) shown++;
          }
          types.hidden = !shown;
          const title = types.previousElementSibling as HTMLElement | null;
          if (title?.tagName === "H3") title.hidden = !shown;
          left += shown;
        }
        none.hidden = left > 0;
      },
      onkeydown: (e: KeyboardEvent) => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        body.querySelector<HTMLElement>(".connection-type:not([hidden])")?.click();
      },
    }) as HTMLInputElement;
    // The crumb at the top (8.11): where this is, and the way back.
    const trail = then ? null : h("div", { class: "connection-detail-top" }, backButton("Connections", urlOf(LIST)), crumbs([{ label: "Connections", url: urlOf(LIST) }, { label: "Add connection" }]));
    // From a password's New vault: only vaults, and Back returns to that connection. Otherwise no vaults:
    // they are added on the Variables page.
    clear(
      body,
      trail,
      h("div", { class: "connection-type-find" }, search),
      none,
      ...(then ? group("Key vaults", of("vault")) : [...group("Databases", of("database")), ...group(LAKE_GROUP, (t) => t.group === LAKE_GROUP), ...group("Files", of("file")), ...group("Your own code", of("python"))]),
    );
    if (then) foot.append(button("Back", () => void then(null), { icon: "back" }));
    search.focus();
  };

  /** A new connection's form by its type's id (an address: a reload, Forward, a breadcrumb). */
  const showFormOf = async (id: string): Promise<void> => {
    leave(`form|${id}|`);
    clear(foot);
    clear(body, loadingBlock("Loading the form…"));
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
    const optionsHost = h("div", { class: "connection-fields connection-options-fields" });
    const optionsBox = h("details", { class: "connection-options", hidden: true }, h("summary", {}, "Options"), optionsHost);
    const passwords = new Map<string, HTMLInputElement>();
    const codeBox = h("textarea", { class: "mono connection-code", rows: 8, spellcheck: false, "aria-label": "The Python this connection runs" }, code) as HTMLTextAreaElement;
    const result = h("div", { class: "connection-result", role: "status" });

    // Changes to the code one at a time (a box left for another box sends two): each starts from the code the
    // last one made. The settings' ids are places in the code, read again when a password's rename moved them.
    let changing: Promise<unknown> = Promise.resolve();
    const inTurn = <T>(work: () => Promise<T>): Promise<T> => {
      const next = changing.then(work, work);
      changing = next.catch(() => undefined);
      return next;
    };
    let fieldsCode = code;
    const freshIds = async (): Promise<void> => {
      if (code === fieldsCode) return;
      const read = await api<{ settings: Field[] }>("/blades/inspect", "POST", { code, template: form.id || null, name: editing });
      if (read.settings.length === fields.length) fields = fields.map((f, i) => ({ ...f, ...read.settings[i]!, picker: f.picker }));
      fieldsCode = code;
    };

    /** A changed field's value, written into the code by the server; the fields keep their boxes. */
    const fill = (field: Field, value: string, boxed = true): Promise<void> => {
      const at = fields.indexOf(field);
      return inTurn(() => fillNow(at, field, value, boxed));
    };
    const fillNow = async (at: number, was: Field, value: string, boxed: boolean): Promise<void> => {
      // A box's whole text (12.7): a value, or ${NAME} the code then reads where it runs. A choice: its value.
      const sent = boxed && was.type !== "flag" ? { text: value } : value;
      try {
        await freshIds();
        const field = at >= 0 && fields[at]?.name === was.name ? fields[at]! : was;
        const answer = await api<{ code: string; settings: Field[] }>("/blades/fill", "POST", { code, values: { [field.id]: sent }, template: form.id || null, name: editing });
        code = answer.code;
        fieldsCode = code;
        codeBox.value = code;
        // The ids follow the new code; the same settings in the same order keep their boxes.
        if (answer.settings.length === fields.length) fields = fields.map((f, i) => ({ ...f, ...answer.settings[i]!, picker: f.picker }));
        else drawFields(answer.settings.map((s) => ({ ...s, picker: fields.find((f) => f.name === s.name)?.picker ?? (CERTIFICATE_KINDS[s.name] ? "file" : null) })));
        readWhenReady();
      } catch (e) {
        showError(result, e);
      }
    };

    const drawFields = (next: Field[]): void => {
      fields = next;
      fieldsCode = code;
      const boxes = fields.map((field, i) => {
        if (field.type === "flag") {
          // On or off: True/False in the code, yes/no in a connection string.
          const tick = h("input", { type: "checkbox", checked: ["true", "yes", "1", "on"].includes(String(field.value).toLowerCase()), "aria-label": words(field.name) }) as HTMLInputElement;
          tick.addEventListener("change", () => void fill(fields[i]!, tick.checked ? "yes" : "no", false));
          return h("label", { class: "field field-flag" }, tick, h("span", {}, words(field.name)));
        }
        const offered = form.choices?.[field.name];
        if (offered?.length) {
          // A choice (SQL Server's Encrypt, its driver): the code's own value first when it is another.
          const now = String(field.value);
          const pick = h("select", { "aria-label": words(field.name) }, ...[...(offered.includes(now) ? [] : [now]), ...offered].map((o) => h("option", { value: o, selected: o === now }, o))) as HTMLSelectElement;
          pick.addEventListener("change", () => void fill(fields[i]!, pick.value, false));
          return h("label", { class: "field" }, h("span", {}, words(field.name)), pick);
        }
        // One box (12.7): its text, ${NAME} where it reads a variable (a number's box takes one too).
        const boxText = field.text ?? String(field.value);
        const input = h("input", { type: "text", inputmode: field.type === "number" && !boxText.includes("${") ? "numeric" : "text", value: field.placeholder ? "" : boxText, placeholder: boxText, "aria-label": words(field.name), spellcheck: false });
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
        // A certificate file on a Function App: ${WAREHOUSE_CERTIFICATE_FILE:-C:\certs\ca.pem} (its path here the default).
        return h("label", { class: `field${field.picker ? " wide" : ""}`, "data-setting": field.name }, h("span", {}, words(field.name), field.key.toLowerCase() !== field.name.toLowerCase() ? h("span", { class: "hint" }, ` (${field.key})`) : null), h("span", { class: "field-row" }, variableBox(input, { label: words(field.name) }), browse), list);
      });
      // The same order on every form: where, who, security (a setting the rule does not name stays
      // with "where", after the ones it does, in the code's order).
      // SQL Server's options (encryption, the driver, timeouts...) fold under Options.
      clear(fieldsHost, ...partBoxes(form, fields, boxes, "where"));
      clear(whoHost, ...partBoxes(form, fields, boxes, "who"));
      clear(securityHost, ...partBoxes(form, fields, boxes, "security"));
      const folded = partBoxes(form, fields, boxes, "options");
      clear(optionsHost, ...folded);
      optionsBox.hidden = folded.length === 0;
    };
    drawFields(fields);

    // Each password is one box (design principle 12.7): `${NAME}`, a variable whose source the Variables page
    // keeps (the keyring, a vault's entry, the environment), named in the code as secret("NAME"); or a value
    // typed here, kept on Save as a keyring variable of the connection's name (SALES_DB_PASSWORD).
    const looksLikeVariable = (s: string): boolean => /^[A-Z_][A-Z0-9_]*$/.test(s) && /[A-Z]/.test(s);
    // Each password keeps the word the starter gave it ("Password") while its variable renames it in the code.
    const labels = new Map<string, string>(form.secrets.map((s) => [s, s]));
    const label = (s: string): string => words(labels.get(s) ?? s);
    // The variable a typed password is kept as (domain/connections.py env_name_for).
    const variableFor = (s: string): string => {
      const made = `${name.value.trim() || form.label}_${labels.get(s) ?? s}`.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toUpperCase();
      return /^[0-9]/.test(made) ? `_${made}` : made || "PASSWORD";
    };
    const pointAt = (secret: string, variable: string): Promise<void> => inTurn(() => pointAtNow(secret, variable));
    const pointAtNow = async (secret: string, variable: string): Promise<void> => {
      const answer = await api<{ code: string; secret: string }>("/connections/source", "POST", { code, secret, from: "env", env: variable });
      code = answer.code;
      codeBox.value = code;
      form.secrets = form.secrets.map((s) => (s === secret ? answer.secret : s));
      labels.set(answer.secret, labels.get(secret) ?? secret);
    };
    // A typed password as it is kept: `$${NAME}` is the text `${NAME}` (12.7); a `$` elsewhere stays as typed.
    const typedValue = (text: string): string => text.replace(/\$(\$\{[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?\})/g, "$1");
    const referenceOnly = (text: string): string | null => /^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$/.exec(text.trim())?.[1] ?? null;
    const drawPasswords = (): HTMLElement | null => {
      passwords.clear();
      if (!form.secrets.length) return null;
      const saved = form.summary?.secrets ?? {};
      const vaultOnly = form.secrets_from === "vault only"; // never typed into the app: a vault's variable
      return h(
        "fieldset",
        { class: "connection-passwords" },
        // A Power BI workspace's are an app registration's values (two ids and a secret), not passwords alone.
        h("legend", {}, form.dialect === "dax" || form.dialect === "dataverse" ? "App registration" : "Passwords"),
        ...form.secrets.map((s) => {
          const named = looksLikeVariable(s) ? `\${${s}}` : "";
          const input = h("input", { type: named ? "text" : "password", class: "mono", autocomplete: "new-password", "aria-label": label(s), spellcheck: false, value: named, placeholder: saved[s] ? "Saved" : vaultOnly ? "${VARIABLE}" : "" }) as HTMLInputElement;
          // A reference reads as text; a typed password stays hidden.
          // A typed one is kept in this computer's keyring: said, amber, while it is typed (the portability rule).
          const note = h("div", { class: "password-note" });
          const typedHere = (): void => {
            input.type = input.value.includes("${") ? "text" : "password";
            const local = input.value !== "" && !namesVariable(input.value) && form.keyring_note;
            note.replaceChildren(local ? (localNotes([form.keyring_note!], "password-local") ?? "") : "");
          };
          input.addEventListener("input", typedHere);
          // The secret's name the code asks for now (renamed when a variable is put in), and the text last
          // settled: a box whose type changed while typed may not say "change", so leaving it settles it too.
          let current = s;
          let settled = input.value;
          const settle = (): void => {
            if (input.value === settled) return;
            settled = input.value;
            const variable = referenceOnly(input.value);
            if (!variable && namesVariable(input.value)) {
              // A password is a variable on its own, or a value: never part of one (its value is never shown).
              showError(result, { what: `${label(current)} takes one variable on its own, such as \${${variableFor(current)}}, or a typed password.`, where: label(current) });
              return;
            }
            if (variable && variable !== current) {
              passwords.delete(current);
              const was = current;
              current = variable;
              void pointAt(was, variable).then(
                () => clearError(result),
                (e: unknown) => {
                  current = was;
                  showError(result, e);
                },
              );
            } else if (!variable) passwords.set(current, input);
          };
          input.addEventListener("change", settle);
          input.addEventListener("blur", settle);
          if (!named) passwords.set(s, input);
          return h("div", { class: "connection-password" }, h("label", { class: "field password-box" }, h("span", {}, label(s)), h("span", { class: "field-row" }, variableBox(input, { label: label(s) })), note));
        }),
      );
    };
    /** Before Save: each typed password kept as a keyring variable, the code then asking for that variable. */
    const typedToVariables = async (): Promise<void> => {
      if (form.secrets_from === "vault only") return; // refused by the server, said there
      for (const [s, input] of [...passwords]) {
        if (!input.value || namesVariable(input.value)) continue;
        const variable = variableFor(s);
        await api("/variables", "PUT", { name: variable, value: typedValue(input.value), from: "keyring" });
        await pointAt(s, variable);
        passwords.delete(s);
        input.value = `\${${variable}}`;
        input.type = "text";
      }
    };

    // ===== a vault's secrets: each ticked one becomes an environment variable =====
    // Every secret (a new vault's default): each one under its own name, new ones too; a box renames one.
    const every = h("input", { type: "checkbox", checked: editing ? Boolean(form.vault_all) : true, "aria-label": "Every secret in the vault" }) as HTMLInputElement;
    const mapRows: { secret: string; env: HTMLInputElement; use: HTMLInputElement; row: HTMLElement }[] = [];
    // The names other sources give (your variables, other vaults), for the rows' inline check.
    let takenNames: Map<string, string> | null = null;
    let takenAsked: Promise<void> | null = null;
    const loadTaken = (): Promise<void> =>
      (takenAsked ??= api<{ variables: { name: string; from: string; vault?: string; kept?: string }[] }>("/variables").then(
        (r) => {
          takenNames = new Map(
            r.variables
              .filter((v) => (v.from === "vault" ? v.vault !== editing : Boolean(v.kept)))
              .map((v) => [v.name, v.from === "vault" ? (v.vault ?? "a key vault") : "your variables"]),
          );
        },
        () => undefined,
      ));
    // The names the form's read listed: kept with the save, so the vault's variables are there at once.
    let readNames: string[] | null = null;
    const mapBody = h("tbody", {});
    const mapFilter = h("input", { type: "search", placeholder: "Filter", "aria-label": "Filter the secrets", hidden: true }) as HTMLInputElement;
    /** A secret's row. `mapped`: the variable it was given; none, and it takes the vault's own name. */
    const addMapping = (secret: string, mapped: string | null, use: boolean): void => {
      if (mapRows.some((r) => r.secret === secret)) return;
      const tick = h("input", { type: "checkbox", checked: use, "aria-label": `Use ${secret}` }) as HTMLInputElement;
      const own = envFor(secret);
      const variable = h("input", { type: "text", class: "mono", value: mapped && mapped !== own ? mapped : "", placeholder: own, spellcheck: false, "aria-label": `${secret}: the variable's name` }) as HTMLInputElement;
      const cell = h("td", {}, variable);
      // One name, one variable: a name typed here that another source gives is said before saving.
      const check = (): void => {
        cell.querySelector(".error-mark")?.remove();
        const typedName = variable.value.trim();
        const by = typedName ? takenNames?.get(typedName) : undefined;
        if (by) cell.append(errorMark(`${typedName} is already a variable (from ${by}). Pick another name.`));
      };
      variable.addEventListener("input", () => {
        tick.checked = true;
        check();
      });
      void loadTaken().then(check);
      const row = h("tr", {}, h("td", {}, tick), h("td", {}, h("code", {}, secret)), cell);
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
        readNames = r.names.map((m) => m.secret);
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
        (e: Error) => result.replaceChildren(errorNote(e)),
      );
    });

    const typed = (): Record<string, string> => Object.fromEntries([...passwords].filter(([, input]) => input.value).map(([s, input]) => [s, typedValue(input.value)]));
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
      showError(result, e, again ? { fixes: [{ label: "Try again", run: again }] } : {});
      // A run that stopped on a missing package: the prompt, then the run again once it is in.
      promptForError(e, { then: again });
    };
    const test = async (): Promise<void> => {
      result.replaceChildren();
      try {
        const r = await api<{ type?: string; found?: string; variables?: string[]; name?: string; preview?: Preview; preview_error?: string }>("/connections/test", "POST", { ...sent(), secrets: typed() });
        // Tested before it was named: the file's own name, as the server used it.
        if (r.name && !name.value.trim()) name.value = r.name;
        result.replaceChildren(
          h("p", { class: "status-ok" }, `It works: ${worked(r)}.`),
          // A table's first rows (a Dataverse environment's), or a file's.
          ...(r.preview ? ("table" in r.preview ? tablePreview(r.preview as unknown as TablePreview) : previewOf(r.preview)) : []),
          r.preview_error ? errorNote(`Its rows could not be read: ${r.preview_error}`) : "",
        );
      } catch (e) {
        failed(e, () => void test());
      }
    };
    const save = async (): Promise<void> => {
      try {
        await typedToVariables();
        const body = { ...sent(), secrets: typed(), ...(isVault && readNames ? { vault_names: readNames } : {}) };
        await (editing ? api(`/connections/${encodeURIComponent(editing)}`, "PUT", body) : api("/connections", "POST", body));
        toast(`Saved ${name.value.trim()}.`);
        if (isVault) forgetVariables(); // the ${ list read again: the vault's variables are in it now
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
    // What the chosen way leans on that only this computer has: said beside it, amber.
    const signInNote = h("div", { class: "sign-in-local" });
    const noteSignIn = (): void => {
      const way = ways[Number(signInSelect.value)];
      // A username and password: that it cannot do multi-factor sign-in, and which way can (one line).
      const line = way?.note ? h("p", { class: "sign-in-note" }, way.note) : null;
      signInNote.replaceChildren(...[localNotes(way?.local), line].filter((x): x is HTMLElement => x !== null));
    };
    noteSignIn();
    signInSelect.addEventListener("change", noteSignIn);
    const signIn = ways.length > 1 ? h("div", {}, h("label", { class: "field" }, h("span", {}, "Sign in"), signInSelect), signInNote) : null;
    const switchSignIn = async (way: { code: string }): Promise<void> => {
      // A value typed so far, with its variable when it comes from one (SQL Server's server, a certificate).
      const typedSoFar = new Map<string, unknown>(fields.filter((f) => !f.placeholder || namesVariable(f.text ?? "")).map((f) => [f.name, f.type === "flag" || form.choices?.[f.name] ? f.value : { text: f.text ?? String(f.value) }]));
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
      // The tour's made-up form (a PostgreSQL one, on a computer without its driver) never asks: the prompt took
      // the tour's focus. The small Install reminder is there all the same.
      const note = touring() ? reminder(missing, { then: again }) : noticeMissing(missing, { then: again });
      installSlot.replaceChildren(h("p", { class: "hint install-note" }, note, h("code", {}, missing.command)));
    };
    drawInstall();
    clear(
      body,
      trail,
      h("h3", {}, editing ? `Edit ${editing}` : isVault ? `New ${plain(form.label)}` : `New ${plain(form.label)} connection`),
      form.note ? h("p", { class: "hint" }, form.note) : null,
      localNotes(form.local, "form-local"),
      h("label", { class: "field" }, h("span", {}, "Name"), name),
      h("label", { class: "field" }, h("span", {}, "Description"), description),
      fieldsHost,
      signIn,
      whoHost,
      passwordsSlot,
      securityHost,
      optionsBox,
      rowLimitField,
      secretsBox,
      installSlot,
      result,
      h("details", { class: "connection-code-box" }, h("summary", {}, "Python code"), codeBox),
    );
    foot.append(
      what.then ? button("Back", () => void showTypes(what.then), { icon: "back" }) : backButton(backTo.label, backTo.url),
      // The form is gated while it tests or saves (loading.ts): nothing typed meanwhile is lost to a redraw.
      button(isVault ? "Test" : "Test connection", busyClick("Testing…", () => busy(body, isVault ? `Reading ${name.value.trim() || plain(form.label)}…` : `Connecting to ${name.value.trim() || plain(form.label)}…`, test())), { icon: "play" }),
      button("Save", busyClick("Saving…", () => busy(body, `Saving ${name.value.trim() || plain(form.label)}…`, save())), { icon: "save", class: "primary" }),
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
