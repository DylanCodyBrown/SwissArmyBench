/**
 * pythonConnectionForm.ts: the Connections window's form for "Python (your own code)", a connection
 * made of the user's own Python (domain/python_connections.py). [WIRE + EXPORT]
 *
 *   [BOXES]     three code boxes, each the Workbench's Python editor (a plain box until it loads):
 *               Connect makes conn; List the tables returns its catalog; Read a table returns a
 *               table's rows. One short line on each says what it gives back
 *   [VARIABLES] every environment variable the boxes read (os.environ["X"], os.environ.get,
 *               os.getenv, secret), found by the server as the boxes change, each with what it reads on
 *               this computer (variableBox.ts previewLine: a secret masked; not set: Set it). Where its
 *               value comes from is the Variables page's (12.7), never a picker here
 *   [TEST]      Connect, then List the tables, then the first table's first rows (nothing is saved)
 *   [SAVE]      one connection: the three boxes and the mapping
 *
 * ROUTING: [VARIABLES] POST /connections/variables {code, tables, read}
 *          [LINE]      POST /variables/resolve
 *          [PACKAGES]  POST /blades/inspect (what the boxes import); POST /blades/install
 *          [TEST]      POST /connections/test      [SAVE] POST /connections, PUT /connections/{name}
 */
import { api } from "./api";
import { button, clear, h, toast } from "./dom";
import { busy, busyClick } from "./loading";
import { type Missing, promptForError, promptInstall, reminder } from "./missingPackages";
import type { CodeEditor } from "./lazy/codeEditor";
import { backButton } from "./nav";
import { effectiveTheme } from "./theme";
import { previewLine } from "./variableBox";
import { errorNote } from "./errorNote";
import { loadEditors } from "./lazyLoad";

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
  /** Where its Back goes (nav.backButton), and the trail above it past one level. */
  backTo: { label: string; url: string };
  trail: HTMLElement | null;
  /** Hands over what the form lets go of when another view replaces it (its editors). */
  leaving: (dispose: () => void) => void;
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
  const failed = (e: unknown): void => void result.replaceChildren(errorNote(e));

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
  const variablesHost = h("div", {});
  // Each variable the boxes read, and what it reads on this computer (12.7): where its value comes from (the
  // keyring, a key vault's entry, the environment, a plain value) is set once on the Variables page, for every
  // place that uses it; one not set is the one error, with Set it. A secret is masked, never shown.
  const drawVariables = (): void => {
    if (!reads.length) {
      variablesHost.replaceChildren();
      return;
    }
    const rows = reads.map((r) => {
      const { line, show } = previewLine();
      // A variable the code reads with a default of its own (os.environ.get) is not an error when not set.
      void show(r.required || r.set ? `\${${r.name}}` : "");
      return h("div", { class: "connection-password python-variable", "data-variable": r.name }, h("code", {}, r.name), line);
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
      if (!same) drawVariables();
      void readPackages(true);
    } catch {
      // the boxes are being typed: the names follow when they read again
    }
  };

  // ===== a package the boxes import that the app's Python does not have =====
  const installSlot = h("div", {});
  // The prompt comes in the user's face as the form opens (`ask`), not while a box is typed in; the small
  // Install reminder stays beside the boxes (missingPackages.ts).
  const readPackages = async (ask = false): Promise<void> => {
    let found: { missing?: Missing | null };
    try {
      found = await api("/blades/inspect", "POST", { code: [connect.value(), tables.value(), read.value()].join("\n"), template: "python", name: editing });
    } catch {
      return; // a box that is not Python yet
    }
    const missing = found.missing;
    if (!missing) {
      installSlot.replaceChildren();
      return;
    }
    const options = { then: () => readPackages() };
    if (ask) void promptInstall(missing, options);
    installSlot.replaceChildren(h("p", { class: "hint install-note" }, reminder(missing, options), h("code", {}, missing.command)));
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
      // A mapping saved before the Variables page kept every source stays as it was (nothing lost).
      variables: [...sources.values()].filter((s) => names.has(s.name)).map((s) => (s.from === "vault" ? { name: s.name, from: s.from, vault: s.vault ?? "", secret: s.secret ?? "" } : s.from === "value" ? { name: s.name, from: s.from, value: s.value ?? "" } : { name: s.name, from: s.from })),
    };
  };
  const test = async (): Promise<void> => {
    result.replaceChildren();
    try {
      await readVariables(); // the boxes as they are now
      const r = await api<PythonTested & { type?: string }>("/connections/test", "POST", { ...sent(), name: name.value.trim() || "Untitled" });
      result.replaceChildren(h("p", { class: "status-ok" }, `It works: ${pythonWorked(r) ?? `made a ${r.type}`}.`), ...(r.preview ? tablePreview(r.preview) : []));
    } catch (e) {
      failed(e);
      promptForError(e, { then: () => test() }); // stopped on a missing package: install it, then test again
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

  host.leaving(dispose);
  clear(
    body,
    host.trail,
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
    backButton(host.backTo.label, host.backTo.url),
    // The form is gated while it tests or saves (loading.ts).
    button("Test connection", busyClick("Testing…", () => busy(body, `Connecting to ${name.value.trim() || "the connection"}…`, test())), { icon: "play" }),
    button("Save", busyClick("Saving…", () => busy(body, `Saving ${name.value.trim() || "the connection"}…`, save())), { icon: "save", class: "primary" }),
  );
  drawVariables();
  void readPackages();
  name.focus();
}
