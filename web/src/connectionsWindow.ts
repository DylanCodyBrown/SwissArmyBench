/**
 * connectionsWindow.ts: the Application row's Connections window (Plans/workbench-and-connections.plan.md):
 * the user's connections, each a database, a file or a key vault, and adding one with a form per type.
 * [WIRE + EXPORT]
 *
 *   [LIST]   each connection: its type, its catalog, Edit, Test, Refresh catalog, Copy for Python, Remove;
 *            a key vault shows its entries (variable <- secret in the vault) instead; a Power BI
 *            dataset has Import its relationships (into the current model: the Diagram shows them)
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
 *   [VAULT]  a vault's form lists its secrets by name (never a value) as soon as it can be read (its
 *            address filled in, or opened to edit). Each becomes an environment variable: left empty,
 *            under the vault's own name (shown faintly); typed, under that name. Every secret (new ones
 *            too), or untick it and choose. Every Workbench kernel starts with them set
 *
 * ROUTING: [LIST]  GET /connections; Remove -> DELETE /blades/{name}; Refresh -> POST /blades/{name}/refresh
 *          [TYPES] GET /connections/types        [EDIT] GET /connections/{name}
 *          [FIELD] POST /blades/fill (the value into the code)   [CODE] POST /blades/inspect (its fields again)
 *          [TEST]  POST /connections/test        [SAVE] POST /connections, PUT /connections/{name}
 *          [VAULT] POST /connections/vaults/secrets (the names in it); GET /connections/vaults (a password's)
 *          [RELATIONSHIPS] POST /connections/{name}/relationships (a Power BI dataset's, merged)
 *          [INSTALL] POST /blades/install {packages}, then POST /blades/inspect (is it installed now?)
 */
import { api, errorText, onNotice } from "./api";
import { button, clear, closeDialogs, h, openDialog, toast } from "./dom";
import { chooseFile } from "./fileChooser";
import { pickSheets } from "./openFile";
import { pythonWorked, showPythonForm, tablePreview, type PythonForm, type PythonTested } from "./pythonConnectionForm";

interface Field {
  id: string;
  name: string;
  key: string;
  value: string | number | boolean;
  type: "text" | "number" | "flag";
  placeholder: boolean;
  picker: "file" | "folder" | null;
  suggestions: { value: string; from: string }[];
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

/** On the grid page the new table arrives as the tab in front, so this window closes to show it
 * (decision 8). In the Workbench's window the grid is in another window, and this one stays. */
function shownAsTab(): void {
  if (document.querySelector(".tabs-row")) closeDialogs();
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
 * merged into the current model (the Diagram and the Key Finder's known joins then show them). It is
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

/** The Application row's button. */
export function connectionsButton(): HTMLButtonElement {
  return button("Connections", () => void openConnections(), { icon: "link", class: "ribbon-btn" });
}

export async function openConnections(): Promise<void> {
  const { body, foot, close } = openDialog("Connections", true);
  let drawing = 0;
  const showList = async (): Promise<void> => {
    listShowing = () => (body.isConnected ? void showList() : (listShowing = null));
    // Drawn again as catalogs load: only the newest draw paints (never twice, never over a form opened
    // meanwhile), and "Loading…" shows only the first time (no flicker).
    const mine = ++drawing;
    if (!body.querySelector(".connection-list, .empty-note")) {
      clear(foot);
      clear(body, h("p", { class: "hint" }, "Loading…"));
    }
    let found: Connection[];
    try {
      found = (await api<{ connections: Connection[] }>("/connections")).connections;
    } catch (e) {
      if (mine !== drawing) return;
      clear(foot);
      clear(body, h("p", { class: "status-error" }, (e as Error).message));
      foot.append(button("Close", close));
      return;
    }
    if (mine !== drawing) return;
    clear(foot);
    const row = (c: Connection): HTMLElement => {
      const path = encodeURIComponent(c.name);
      const readOnly = c.source === "pack";
      // A Python connection's Test: the first table's first rows, under its row.
      const tested = h("div", { class: "connection-result connection-tested", role: "status" });
      return h(
        "li",
        { class: "connection-row" },
        h(
          "div",
          { class: "connection-text" },
          h("div", { class: "pack-title" }, h("strong", {}, c.name), h("span", { class: "badge" }, c.type ? plain(c.type) : { database: "Database", file: "File", vault: "Key vault", python: "Python" }[c.connection]), catalogWord(c)),
          c.description ? h("div", { class: "hint" }, c.description) : null,
          c.entries
            ? h("div", { class: "vault-entries" }, c.every ? h("span", { class: "badge" }, "Every secret") : null, ...c.entries.map((e) => h("code", { class: "hint", title: `${e.secret} in the vault` }, `${e.env} ← ${e.secret}`)))
            : // A Power BI workspace's cells are DAX cells, each on one of its datasets; your own Python's reads with sag.read.
              h("code", { class: "hint" }, c.dialect === "dax" ? `sag.dax("${c.name}/<dataset>", …)  ·  %%dax ${c.name}/<dataset>` : c.connection === "python" ? `sag.connection("${c.name}")  ·  sag.read("${c.name}", table)` : `sag.connection("${c.name}")  ·  %%sql ${/\s/.test(c.name) ? `"${c.name}"` : c.name}`),
        ),
        h(
          "span",
          { class: "connection-actions" },
          c.connection === "file" && c.template !== "folder" ? button("Open as grid", () => void openConnection(c.name), { icon: "rows", class: "primary" }) : null,
          readOnly ? null : button("Edit", () => void showForm({ edit: c.name }), { icon: "edit" }),
          button("Test", () => void testSaved(c.name, c.connection === "python" ? tested : undefined), { icon: "play" }),
          c.has_catalog ? button("Refresh catalog", () => void refresh(c.name), { icon: "import" }) : null,
          c.entries ? null : button("Copy for Python", () => void navigator.clipboard.writeText(`conn = sag.connection("${c.name}")`).then(() => toast("Copied")), { icon: "copy", iconOnly: true }),
          readOnly
            ? null
            : button("Remove", () => {
                if (!confirm(c.entries ? `Remove the key vault ${c.name}? Its variables stop being set.` : `Remove the connection ${c.name}? Its saved passwords go too.`)) return;
                void api(`/blades/${path}`, "DELETE").then(() => showList(), (e: Error) => toast(e.message, "error"));
              }, { icon: "trash", iconOnly: true }),
        ),
        c.connection === "python" ? tested : null,
      );
    };
    const databases = found.filter((c) => c.connection === "database");
    const files = found.filter((c) => c.connection === "file");
    const own = found.filter((c) => c.connection === "python");
    const vaultList = found.filter((c) => c.connection === "vault");
    clear(
      body,
      found.length
        ? h(
            "div",
            {},
            databases.length ? h("h3", {}, "Databases") : null,
            databases.length ? h("ul", { class: "connection-list" }, ...databases.map(row)) : null,
            files.length ? h("h3", {}, "Files") : null,
            files.length ? h("ul", { class: "connection-list" }, ...files.map(row)) : null,
            own.length ? h("h3", {}, "Your own code") : null,
            own.length ? h("ul", { class: "connection-list" }, ...own.map(row)) : null,
            vaultList.length ? h("h3", {}, "Key vaults") : null,
            vaultList.length ? h("ul", { class: "connection-list" }, ...vaultList.map(row)) : null,
          )
        : h("p", { class: "empty-note" }, "No connections"),
    );
    foot.append(button("Add connection", () => void showTypes(), { icon: "plus", class: "primary" }), button("Close", close));
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
  const showTypes = async (then?: Then): Promise<void> => {
    listShowing = null;
    drawing++; // a list draw still on its way paints nothing now
    clear(foot);
    clear(body, h("p", { class: "hint" }, "Loading…"));
    let types: Form[];
    try {
      types = (await api<{ types: Form[] }>("/connections/types")).types;
    } catch (e) {
      clear(body, h("p", { class: "status-error" }, (e as Error).message));
      return;
    }
    const icons = { database: "sql", file: "folder", vault: "key", python: "code" } as const;
    const tile = (t: Form): HTMLElement => button(plain(t.label), () => void showForm({ type: t, then }), { class: "connection-type", icon: icons[t.connection] });
    const group = (title: string, kind: Form["connection"]): HTMLElement[] => [h("h3", {}, title), h("div", { class: "connection-types" }, ...types.filter((t) => t.connection === kind).map(tile))];
    // From a password's New vault: only vaults, and Back returns to that connection.
    clear(body, ...(then ? [] : [...group("Databases", "database"), ...group("Files", "file"), ...group("Your own code", "python")]), ...group("Key vaults", "vault"));
    foot.append(button("Back", () => void (then ? then(null) : showList()), { icon: "back" }), button("Close", close));
  };

  // ===== FORM =====
  const showForm = async (what: { type?: Form; edit?: string; then?: Then }): Promise<void> => {
    listShowing = null;
    drawing++;
    clear(foot);
    let form: Form;
    if (what.edit) {
      try {
        form = await api<Form>(`/connections/${encodeURIComponent(what.edit)}`);
      } catch (e) {
        toast((e as Error).message, "error");
        return;
      }
    } else form = structuredClone(what.type!);
    const editing = what.edit ?? null;
    if (form.connection === "python") {
      // Your own Python: three code boxes and the variables they read (pythonConnectionForm.ts).
      showPythonForm({
        body,
        foot,
        form: form as unknown as PythonForm,
        editing,
        back: () => void (editing ? showList() : showTypes(what.then)),
        saved: () => void showList(),
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
    const fill = async (field: Field, value: string): Promise<void> => {
      try {
        const answer = await api<{ code: string; settings: Field[] }>("/blades/fill", "POST", { code, values: { [field.id]: field.type === "number" ? Number(value) : value }, template: form.id || null, name: editing });
        code = answer.code;
        codeBox.value = code;
        // The ids follow the new code; the same settings in the same order keep their boxes.
        if (answer.settings.length === fields.length) fields = fields.map((f, i) => ({ ...f, ...answer.settings[i]!, picker: f.picker }));
        else drawFields(answer.settings.map((s) => ({ ...s, picker: fields.find((f) => f.name === s.name)?.picker ?? null })));
        readWhenReady();
      } catch (e) {
        result.replaceChildren(h("p", { class: "status-error" }, (e as Error).message));
      }
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
              const suffixes = field.name === "certificate file" ? [".pem", ".crt", ".cer"] : FILE_KINDS[form.id];
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
        return h("label", { class: `field${field.picker ? " wide" : ""}` }, h("span", {}, words(field.name), field.key.toLowerCase() !== field.name.toLowerCase() ? h("span", { class: "hint" }, ` (${field.key})`) : null), h("span", { class: "field-row" }, input, browse), list);
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
        h("legend", {}, form.dialect === "dax" ? "App registration" : "Passwords"),
        ...form.secrets.map((s) => {
          const inVault = vaults.find((v) => v.entries.some((e) => e.env === s)) ?? vaults.find((v) => v.name === pointedAt.get(s));
          // A starter may say its passwords come from a key vault first (a Power BI dataset's app registration).
          const first = form.secrets_from === "vault" && !editing && labels.get(s) === s ? "vault" : "keyring";
          const origin = chosen.get(s) ?? (inVault ? "vault" : looksLikeVariable(s) && !saved[s] ? "env" : first);
          const from = h("select", { "aria-label": `Where ${label(s)} comes from` }, h("option", { value: "keyring", selected: origin === "keyring" }, "Saved on this computer"), h("option", { value: "env", selected: origin === "env" }, "An environment variable"), h("option", { value: "vault", selected: origin === "vault" }, "A key vault"));
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
        if (mine === reading) failed(e);
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
      void api<{ settings: Field[]; secrets: string[]; install_here: string | null; packages?: Form["packages"] }>("/blades/inspect", "POST", { code, template: form.id || null, name: editing }).then(
        (found) => {
          // The packages the code needs now (a stale "Not installed" once stayed after the code changed).
          form.install_here = found.install_here;
          form.packages = found.packages;
          drawInstall();
          drawFields(found.settings.map((s) => ({ ...s, picker: fields.find((f) => f.name === s.name)?.picker ?? null })));
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
      ...(form.connection === "database" ? { row_limit: rowLimit.value.trim() ? Number(rowLimit.value) : null } : {}),
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
    const failed = (e: unknown): void => {
      result.replaceChildren(h("p", { class: "status-error" }, errorText(e)));
    };
    const test = async (): Promise<void> => {
      result.replaceChildren(h("p", { class: "hint" }, isVault ? "Reading…" : "Connecting…"));
      try {
        const r = await api<{ type?: string; found?: string; variables?: string[]; name?: string; preview?: Preview; preview_error?: string }>("/connections/test", "POST", { ...sent(), secrets: typed() });
        // Tested before it was named: the file's own name, as the server used it.
        if (r.name && !name.value.trim()) name.value = r.name;
        result.replaceChildren(
          h("p", { class: "status-ok" }, `It works: ${worked(r)}.`),
          ...(r.preview ? previewOf(r.preview) : []),
          r.preview_error ? h("p", { class: "status-error" }, `Its rows could not be read: ${r.preview_error}`) : "",
        );
      } catch (e) {
        failed(e);
      }
    };
    const save = async (): Promise<void> => {
      try {
        const body = { ...sent(), secrets: typed() };
        await (editing ? api(`/connections/${encodeURIComponent(editing)}`, "PUT", body) : api("/connections", "POST", body));
        toast(`Saved ${name.value.trim()}.`);
        if (what.then) what.then(name.value.trim());
        else void showList();
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
        const next = await api<{ settings: Field[]; secrets: string[] }>("/blades/inspect", "POST", { code: way.code, template: form.id || null, name: editing });
        const keep = Object.fromEntries(next.settings.filter((s) => typedSoFar.has(s.name) && s.name !== "driver").map((s) => [s.id, typedSoFar.get(s.name)]));
        const answer = Object.keys(keep).length
          ? await api<{ code: string; settings: Field[] }>("/blades/fill", "POST", { code: way.code, values: keep, template: form.id || null, name: editing })
          : { code: way.code, settings: next.settings };
        code = answer.code;
        codeBox.value = code;
        drawFields(answer.settings.map((s) => ({ ...s, picker: fields.find((f) => f.name === s.name)?.picker ?? null })));
        form.secrets = next.secrets;
        labels.clear();
        for (const secret of next.secrets) labels.set(secret, secret);
        passwordsSlot.replaceChildren(drawPasswords() ?? "");
        result.replaceChildren();
      } catch (e) {
        failed(e);
      }
    };
    // A database: how many rows a table opens with as a grid (the grid says when the source has more).
    const rowLimit = h("input", { type: "number", min: 1, step: 1, value: form.row_limit ? String(form.row_limit) : "", placeholder: "10000", "aria-label": "Rows to open" }) as HTMLInputElement;
    const rowLimitField = form.connection === "database" ? h("label", { class: "field" }, h("span", {}, "Rows to open"), rowLimit) : null;
    const passwordsSlot = h("div", {}, drawPasswords() ?? "");
    const installSlot = h("div", {});
    // A driver that is not installed: the command stays in view (for the user's own Python too) with
    // Install beside it, which puts it into the app's Python; the note goes once it is there.
    const drawInstall = (): void => {
      if (!form.install_here) {
        installSlot.replaceChildren();
        return;
      }
      const missing = (form.packages ?? []).filter((p) => !p.installed).map((p) => p.pip);
      const state = h("span", { class: "hint", role: "status" });
      const failedBox = h("pre", { class: "code-box", hidden: true });
      const go = button("Install", () => {
        go.disabled = true;
        state.textContent = "Installing…";
        failedBox.hidden = true;
        void api<{ ok: boolean }>("/blades/install", "POST", { packages: missing })
          .then(() => api<{ install_here: string | null; packages?: Form["packages"] }>("/blades/inspect", "POST", { code, template: form.id || null, name: editing }))
          .then(
            (found) => {
              form.install_here = found.install_here;
              form.packages = found.packages;
              drawInstall();
            },
            (e: Error) => {
              go.disabled = false;
              state.textContent = "";
              let message = e.message;
              try {
                message = (JSON.parse(message) as { output?: string }).output || message;
              } catch {
                // plain words already
              }
              failedBox.textContent = message;
              failedBox.hidden = false;
            },
          );
      }, { icon: "export", title: "Into this app's own Python" });
      go.disabled = !missing.length;
      installSlot.replaceChildren(h("p", { class: "hint install-note" }, isVault ? "Not installed: " : "Driver not installed: ", h("code", {}, form.install_here), go, state), failedBox);
    };
    drawInstall();
    clear(
      body,
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
      button("Back", () => void (editing ? showList() : showTypes(what.then)), { icon: "back" }),
      button(isVault ? "Test" : "Test connection", () => void test(), { icon: "play" }),
      button("Save", () => void save(), { icon: "save", class: "primary" }),
    );
    name.focus();
    name.select();
    readWhenReady(); // a vault opened to edit is read at once; a new one when its address is filled in
  };

  await showList();
}
