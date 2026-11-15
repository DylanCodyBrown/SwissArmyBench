/**
 * pythonConnectionForm.ts: the Connections window's form for "Python (your own code)", a connection
 * made of the user's own Python (domain/python_connections.py). [WIRE + EXPORT]
 *
 *   [BOXES]     three code boxes, each the Workbench's Python editor (a plain box until it loads):
 *               Connect makes conn; List the tables returns its catalog; Read a table returns a
 *               table's rows. One short line on each says what it gives back
 *   [VARIABLES] every environment variable the boxes read (os.environ["X"], os.environ.get,
 *               os.getenv, secret), found by the server as the boxes change. Each with where it comes
 *               from: this computer's environment, saved on this computer, a key vault's entry, or a
 *               plain value. A value typed here goes to the keyring; none comes back
 *   [TEST]      Connect, then List the tables, then the first table's first rows (nothing is saved)
 *   [SAVE]      one connection: the three boxes and the mapping
 *
 * ROUTING: [VARIABLES] POST /connections/variables {code, tables, read}
 *          [VAULT]     GET /connections/vaults; POST /connections/vaults/secrets {name} (names only)
 *          [PACKAGES]  POST /blades/inspect (what the boxes import); POST /blades/install
 *          [TEST]      POST /connections/test      [SAVE] POST /connections, PUT /connections/{name}
 */
import { api, errorText } from "./api";
import { button, clear, h, toast } from "./dom";
import type { CodeEditor } from "./lazy/codeEditor";
import { effectiveTheme } from "./theme";

interface Source {
  name: string;
  from: "env" | "keyring" | "vault" | "value";
  vault?: string;
  secret?: string;
  value?: string;
}

interface Read {
  name: string;
  /** The code cannot run without it (os.environ["X"], secret("X")). */
  required: boolean;
  /** Its name reads like a password, a token or a key. */
  secret: boolean;
  /** This computer's environment has it (never its value). */
  set: boolean;
}

export interface PythonForm {
  label: string;
  code: string;
  catalog: { language: string; command: string } | null;
  read?: { command: string } | null;
  variables?: Source[];
  reads?: Read[];
  name?: string;
  description?: string;
  row_limit?: number | null;
  summary?: { secrets: Record<string, boolean> };
}

interface Vault {
  name: string;
  entries: { env: string; secret: string }[];
}

export interface TablePreview {
  table: string;
  schema: string;
  columns: string[];
  rows: unknown[][];
  total: number | null;
}

export interface PythonTested {
  tables?: number;
  columns?: number;
  preview?: TablePreview;
}

/** What a test of a Python connection found, in a few words: "2 tables, 3 columns". */
export function pythonWorked(r: PythonTested): string | null {
  if (r.tables === undefined) return null;
  const count = (n: number, word: string): string => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
  return `${count(r.tables, "table")}, ${count(r.columns ?? 0, "column")}`;
}

/** The first table's first rows, as Read a table returned them. */
export function tablePreview(preview: TablePreview): HTMLElement[] {
  const shown = (value: unknown): string => (value === null || value === undefined ? "" : String(value));
  const n = preview.rows.length;
  const of = preview.total !== null && preview.total > n ? ` of ${preview.total.toLocaleString()}` : "";
  return [
    h("p", { class: "hint" }, `${preview.schema ? `${preview.schema}.` : ""}${preview.table}: the first ${n.toLocaleString()}${of} row${n === 1 && !of ? "" : "s"}`),
    h(
      "div",
      { class: "connection-preview", tabindex: 0, role: "region", "aria-label": "The table's first rows" },
      h("table", { class: "small" }, h("thead", {}, h("tr", {}, ...preview.columns.map((c) => h("th", {}, c)))), h("tbody", {}, ...preview.rows.map((row) => h("tr", {}, ...row.map((v) => h("td", { class: typeof v === "number" ? "num" : "" }, shown(v))))))),
    ),
  ];
}

// The Workbench's editor (Monaco), loaded when a form first opens; its styles with it.
let editors: Promise<typeof import("./lazy/codeEditor")> | null = null;
function loadEditors(): Promise<typeof import("./lazy/codeEditor")> {
  if (!document.querySelector('link[href="/static/build/lazy/codeEditor.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/build/lazy/codeEditor.css" }));
  }
  return (editors ??= import(/* external */ "/static/build/lazy/codeEditor.js" as string) as Promise<typeof import("./lazy/codeEditor")>);
}

interface Box {
  element: HTMLElement;
  value: () => string;
  dispose: () => void;
}

/** A code box: a plain one at once, the Python editor in its place as soon as it has loaded. */
function codeBox(title: string, line: string, text: string, changed: () => void): Box {
  const plain = h("textarea", { class: "mono connection-code", rows: Math.min(14, Math.max(3, text.split("\n").length + 1)), spellcheck: false, "aria-label": title }, text) as HTMLTextAreaElement;
  plain.addEventListener("input", changed);
  const host = h("div", { class: "python-box-editor" }, plain);
  let editor: CodeEditor | null = null;
  let gone = false;
  void loadEditors().then(
    (m) => {
      if (gone || !host.isConnected) return;
      const mount = h("div", { class: "python-box-monaco", "aria-label": title });
      const current = plain.value;
      host.replaceChildren(mount);
      editor = m.createCodeEditor(mount, { language: "python", value: current, theme: effectiveTheme(), grow: true });
      editor.onChange(changed);
    },
    () => undefined, // the plain box stays
  );
  return {
    element: h("section", { class: "python-box" }, h("h4", {}, title), h("p", { class: "hint" }, line), host),
    value: () => (editor ? editor.value() : plain.value),
    dispose: () => {
      gone = true;
      editor?.dispose();
    },
  };
}

export interface PythonFormHost {
  body: HTMLElement;
  foot: HTMLElement;
  form: PythonForm;
  /** The saved connection being changed, or null for a new one. */
  editing: string | null;
  back: () => void;
  saved: (name: string) => void;
  /** Add a key vault from here: this form waits, kept as it is, and `then` runs when it is back. */
  newVault: (then: () => Promise<void>) => void;
}

export function showPythonForm(host: PythonFormHost): void {
  const { body, foot, form, editing } = host;
  const name = h("input", { type: "text", value: form.name ?? "", "aria-label": "Name", maxlength: 64 }) as HTMLInputElement;
  const description = h("input", { type: "text", value: form.description ?? "", "aria-label": "Description", placeholder: "Optional" }) as HTMLInputElement;
  const rowLimit = h("input", { type: "number", min: 1, step: 1, value: form.row_limit ? String(form.row_limit) : "", placeholder: "10000", "aria-label": "Rows to open" }) as HTMLInputElement;
  const result = h("div", { class: "connection-result", role: "status" });
  const failed = (e: unknown): void => void result.replaceChildren(h("p", { class: "status-error" }, errorText(e)));

  // ===== the three boxes =====
  let waiting = 0;
  const changed = (): void => {
    window.clearTimeout(waiting);
    waiting = window.setTimeout(() => void readVariables(), 400);
  };
  const connect = codeBox("Connect", "Makes conn", form.code, changed);
  const tables = codeBox("List the tables", "Returns a list of dicts or a DataFrame: table, column; optionally schema, type, description", form.catalog?.command ?? "", changed);
  const read = codeBox("Read a table", "Given conn, schema, table, limit (None: all). Returns the rows, or (rows, total)", form.read?.command ?? "", changed);

  // ===== the variables the boxes read, and where each comes from =====
  let reads: Read[] = form.reads ?? [];
  const sources = new Map<string, Source>((form.variables ?? []).map((s) => [s.name, { ...s }]));
  const typed = new Map<string, HTMLInputElement>(); // values to save on this computer
  const savedHere = form.summary?.secrets ?? {};
  let vaults: Vault[] = [];
  const readVaults = (): Promise<unknown> => api<{ vaults: Vault[] }>("/connections/vaults").then((r) => (vaults = r.vaults), () => undefined);
  // Each vault's secret names, read once (names only: the server never sends a value).
  const secretNames = new Map<string, Promise<string[] | null>>();
  const vaultSecrets = (vault: string): Promise<string[] | null> => {
    let reading = secretNames.get(vault);
    if (!reading) {
      reading = api<{ names: { secret: string }[] | null }>("/connections/vaults/secrets", "POST", { name: vault }).then((r) => (r.names ? r.names.map((n) => n.secret) : null));
      reading.catch(() => secretNames.delete(vault));
      secretNames.set(vault, reading);
    }
    return reading;
  };
  const variablesHost = h("div", {});
  const sourceOf = (variable: string): Source => {
    let source = sources.get(variable);
    if (!source) {
      source = { name: variable, from: "env" };
      sources.set(variable, source);
    }
    return source;
  };
  const drawVariables = (): void => {
    typed.clear();
    if (!reads.length) {
      variablesHost.replaceChildren();
      return;
    }
    const BY_NAME = "\u0000by-name";
    const rows = reads.map((r) => {
      const source = sourceOf(r.name);
      const from = h(
        "select",
        { "aria-label": `Where ${r.name} comes from` },
        h("option", { value: "env", selected: source.from === "env" }, "This computer's environment"),
        h("option", { value: "keyring", selected: source.from === "keyring" }, "Saved on this computer"),
        h("option", { value: "vault", selected: source.from === "vault" }, "A key vault"),
        h("option", { value: "value", selected: source.from === "value" }, "A plain value (not a secret)"),
      ) as HTMLSelectElement;
      const slot = h("span", { class: "field-row" });
      const draw = (): void => {
        typed.delete(r.name);
        if (source.from === "env") {
          // Only what needs doing is said: a variable the code needs that this computer does not have.
          slot.replaceChildren(r.set || !r.required ? "" : h("span", { class: "status-error" }, "Not set on this computer"));
        } else if (source.from === "keyring") {
          const input = h("input", { type: "password", autocomplete: "new-password", "aria-label": `${r.name}: its value`, placeholder: savedHere[r.name] ? "Saved" : "Value" }) as HTMLInputElement;
          typed.set(r.name, input);
          slot.replaceChildren(input);
        } else if (source.from === "value") {
          const input = h("input", { type: "text", class: "mono", "aria-label": `${r.name}: its value`, value: source.value ?? "", spellcheck: false, placeholder: "Value" }) as HTMLInputElement;
          input.addEventListener("input", () => (source.value = input.value));
          source.value ??= "";
          slot.replaceChildren(input);
        } else {
          if (!vaults.length) {
            slot.replaceChildren(button("New vault", () => host.newVault(async () => void (await readVaults(), drawVariables())), { icon: "plus" }));
            return;
          }
          if (!vaults.some((v) => v.name === source.vault)) source.vault = vaults[0]!.name;
          const vault = h("select", { "aria-label": `${r.name}: the vault` }, ...vaults.map((v) => h("option", { value: v.name, selected: v.name === source.vault }, v.name))) as HTMLSelectElement;
          const entry = h("select", { "aria-label": `${r.name}: the entry in the vault` }) as HTMLSelectElement;
          const byName = h("input", { type: "text", "aria-label": `${r.name}: the secret's name in the vault`, placeholder: "Secret name", spellcheck: false, value: source.secret ?? "", hidden: true }) as HTMLInputElement;
          byName.addEventListener("input", () => (source.secret = byName.value.trim()));
          let filling = 0;
          const fill = (): void => {
            const mine = ++filling;
            const mapped = (vaults.find((v) => v.name === vault.value)?.entries ?? []).map((e) => e.secret);
            const paint = (names: string[] | null, state: "reading" | "read" | "unlisted" | "failed"): void => {
              if (mine !== filling) return;
              const all = [...new Set([...mapped, ...(names ?? []), ...(source.secret ? [source.secret] : [])])];
              const typing = entry.value === BY_NAME || (state !== "reading" && !all.length);
              clear(
                entry,
                h("option", { value: "", disabled: true, selected: !source.secret && !typing }, state === "reading" ? "Reading the vault…" : all.length ? "Choose a secret" : "No secrets listed"),
                ...all.map((secret) => h("option", { value: secret, selected: secret === source.secret && !typing }, secret)),
                h("option", { value: BY_NAME, selected: typing }, "A secret by name…"),
              );
              entry.title = state === "unlisted" ? "This vault does not list its secrets" : state === "failed" ? "The vault could not be read" : "";
              byName.hidden = entry.value !== BY_NAME;
            };
            paint(null, "reading");
            void vaultSecrets(vault.value).then(
              (names) => paint(names, names === null ? "unlisted" : "read"),
              () => paint(null, "failed"),
            );
          };
          vault.addEventListener("change", () => {
            source.vault = vault.value;
            source.secret = undefined;
            fill();
          });
          entry.addEventListener("change", () => {
            byName.hidden = entry.value !== BY_NAME;
            if (entry.value === BY_NAME) {
              source.secret = byName.value.trim() || undefined;
              byName.focus();
            } else source.secret = entry.value;
          });
          fill();
          slot.replaceChildren(vault, entry, byName);
        }
      };
      from.addEventListener("change", () => {
        source.from = from.value as Source["from"];
        draw();
      });
      draw();
      return h("div", { class: "connection-password python-variable" }, h("label", { class: "field" }, h("code", {}, r.name), from), h("div", { class: "field password-box" }, slot));
    });
    variablesHost.replaceChildren(h("fieldset", { class: "connection-passwords" }, h("legend", {}, "Environment variables"), ...rows));
  };
  let asked = 0;
  const readVariables = async (): Promise<void> => {
    const mine = ++asked;
    try {
      const found = await api<{ variables: Read[] }>("/connections/variables", "POST", { code: connect.value(), tables: tables.value(), read: read.value() });
      if (mine !== asked) return;
      const same = found.variables.map((v) => v.name).join() === reads.map((v) => v.name).join();
      reads = found.variables;
      if (!same) drawVariables(); // the same names keep their boxes (and what is typed in them)
      void readPackages();
    } catch {
      // the boxes are being typed: the names follow when they read again
    }
  };

  // ===== a package the boxes import that the app's Python does not have =====
  const installSlot = h("div", {});
  const readPackages = async (): Promise<void> => {
    let found: { install_here: string | null; packages?: { pip: string; installed: boolean }[] };
    try {
      found = await api("/blades/inspect", "POST", { code: [connect.value(), tables.value(), read.value()].join("\n"), template: "python", name: editing });
    } catch {
      return; // a box that is not Python yet
    }
    if (!found.install_here) {
      installSlot.replaceChildren();
      return;
    }
    const missing = (found.packages ?? []).filter((p) => !p.installed).map((p) => p.pip);
    const state = h("span", { class: "hint", role: "status" });
    const go = button("Install", () => {
      go.disabled = true;
      state.textContent = "Installing…";
      void api("/blades/install", "POST", { packages: missing }).then(
        () => void readPackages(),
        (e: Error) => {
          go.disabled = false;
          state.textContent = "";
          failed(e);
        },
      );
    }, { icon: "export", title: "Into this app's own Python" });
    installSlot.replaceChildren(h("p", { class: "hint install-note" }, "Not installed: ", h("code", {}, found.install_here), go, state));
  };

  // ===== test and save =====
  const sent = (): Record<string, unknown> => {
    const names = new Set(reads.map((r) => r.name));
    const list = tables.value();
    const rows = read.value();
    return {
      name: name.value.trim(),
      description: description.value.trim(),
      kind: "other",
      template: "python",
      variable: "conn",
      code: connect.value(),
      catalog: list.trim() ? { language: "python", command: list } : null,
      read: rows.trim() ? { command: rows } : null,
      row_limit: rowLimit.value.trim() ? Number(rowLimit.value) : null,
      variables: [...sources.values()].filter((s) => names.has(s.name)).map((s) => (s.from === "vault" ? { name: s.name, from: s.from, vault: s.vault ?? "", secret: s.secret ?? "" } : s.from === "value" ? { name: s.name, from: s.from, value: s.value ?? "" } : { name: s.name, from: s.from })),
      secrets: Object.fromEntries([...typed].filter(([, input]) => input.value).map(([variable, input]) => [variable, input.value])),
    };
  };
  const test = async (): Promise<void> => {
    result.replaceChildren(h("p", { class: "hint" }, "Connecting…"));
    try {
      await readVariables(); // the boxes as they are now
      const r = await api<PythonTested & { type?: string }>("/connections/test", "POST", { ...sent(), name: name.value.trim() || "Untitled" });
      result.replaceChildren(h("p", { class: "status-ok" }, `It works: ${pythonWorked(r) ?? `made a ${r.type}`}.`), ...(r.preview ? tablePreview(r.preview) : []));
    } catch (e) {
      failed(e);
    }
  };
  const save = async (): Promise<void> => {
    try {
      await readVariables();
      const sending = sent();
      await (editing ? api(`/connections/${encodeURIComponent(editing)}`, "PUT", sending) : api("/connections", "POST", sending));
      toast(`Saved ${name.value.trim()}.`);
      dispose();
      host.saved(name.value.trim());
    } catch (e) {
      failed(e);
    }
  };
  const dispose = (): void => {
    window.clearTimeout(waiting);
    for (const box of [connect, tables, read]) box.dispose();
  };

  clear(
    body,
    h("h3", {}, editing ? `Edit ${editing}` : "New Python connection"),
    h("label", { class: "field" }, h("span", {}, "Name"), name),
    h("label", { class: "field" }, h("span", {}, "Description"), description),
    connect.element,
    variablesHost,
    tables.element,
    read.element,
    h("label", { class: "field" }, h("span", {}, "Rows to open"), rowLimit),
    installSlot,
    result,
  );
  clear(foot);
  foot.append(
    button("Back", () => {
      dispose();
      host.back();
    }, { icon: "back" }),
    button("Test connection", () => void test(), { icon: "play" }),
    button("Save", () => void save(), { icon: "save", class: "primary" }),
  );
  drawVariables();
  void readVaults().then(drawVariables);
  void readPackages();
  name.focus();
}
