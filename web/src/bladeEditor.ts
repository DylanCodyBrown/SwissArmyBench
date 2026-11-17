/**
 * bladeEditor.ts: the blade screen, New blade, and running a blade (Refresh, Test). [VIEW]
 *
 * A blade is saved Python that reaches outside Python to load something (plan decisions 14-16). Its code
 * is edited in its file (the library's or a blade folder's .blade.py), never in the app (the owner,
 * 2026-11-17: "blades can only be edited in the folder not from the app"): the screen shows it read-only
 * (Monaco, as tall as the code), with Show its file (a starter's: Copy as your own). What the screen
 * changes is the file's header: the name, description, tags, and a table blade's own table name ("Its
 * table is called", checked as it is typed). It shows what the code makes, the secrets it asks for
 * (typed here into the operating system's vault, never shown again), missing packages, and a
 * connection's "How its tables are listed" (read-only, folded). New blade makes a file from a template.
 */
import { api, ApiError } from "./api";
import { append, button, clear, h, openDialog, toast } from "./dom";
import type { EditorLanguage } from "./lazy/codeEditor";
import { effectiveTheme } from "./theme";
import { exportBlades } from "./bladeLibrary";
import { copyAsOwn } from "./starters";
import { installError, type Missing, promptInstall, reminder } from "./missingPackages";

// ===== shapes the server sends (server/routes_catalog.py) =====

export type BladeKind = "sql" | "other" | "vault" | "secret" | "analysis" | "snippet";

export interface BladeSummary {
  name: string;
  kind: BladeKind;
  dialect: string;
  variable: string | null;
  has_catalog: boolean;
  catalog_loaded: boolean;
  template: string | null;
  secrets: Record<string, boolean>;
  vaults: string[];
  typed: Record<string, string>;
  env_names: string[];
  /** What it is for, and words to find it by (search matches the name, the description and the tags). */
  description: string;
  tags: string[];
  /** A favourite on this computer: listed first. */
  pinned: boolean;
  /** "folder": its own .blade.py file in a blade folder (`path`); "saved": kept by the app; "pack":
   * from an installed Claude Code plugin (a marketplace), read-only; "starter": the built-in starter pack,
   * read-only (Copy as your own). */
  source: "saved" | "folder" | "pack" | "starter";
  /** Its family in the starter pack (kept on a copy); a snippet's language and the name a Streamlit
   * piece gives its cell. */
  family?: string;
  language?: string;
  cell_name?: string;
  pack?: string | null; // the pack's label (sales@team-blades 1a2b3c), for a pack blade
  path: string | null;
  /** A database or file blade is a connection, listed apart (connectionsWindow.ts). */
  connection?: "database" | "file" | "vault" | "python" | null;
  /** A connection's variable in the Workbench (Sales DB -> sales_db). */
  code_name?: string | null;
  /** A table blade (a function or code that makes a DataFrame): its table's own name ("": its code's). */
  names_table?: boolean;
  table?: string;
}

interface CatalogCommand {
  language: "sql" | "python";
  command: string;
}

interface BladeDetail extends BladeSummary {
  code: string;
  catalog: CatalogCommand | null;
  vault_mapping: { env: string; secret: string }[];
  inspect?: Inspection;
  /** A snippet's placeholders (domain/snippets.py). */
  placeholders?: { name: string; label: string; kind: string }[];
  /** The file it is kept in (edited there: Show its file). */
  file?: string;
  /** Kept by the app (the library's): Remove deletes its file. A blade folder's file is the user's. */
  removable?: boolean;
}

interface Package {
  module: string;
  pip: string;
  guessed: boolean;
  installed: boolean;
}

interface Inspection {
  variable: string | null;
  assigned: string[];
  secrets: string[];
  imports: string[];
  import_lines: string[];
  packages: Package[];
  install_here: string | null;
  install_yours: string | null;
  /** What is missing from the app's Python, in the prompt's shape (missingPackages.ts). */
  missing?: Missing | null;
  settings?: BladeSetting[];
  error?: string;
}

/** A value in a blade's code that each person fills in for themselves (blade_core/fill.py). */
export interface BladeSetting {
  id: string; // its place in this code: changes when the code does
  name: string; // server, database, user, path...
  key: string; // as the code writes it: host, Server, dbname...
  value: string | number;
  type: "text" | "number";
  line: number;
  where: string;
  placeholder: boolean; // still a stand-in such as my-server
  suggestions: { value: string; from: string }[];
}

/** One field for a setting: its value, a "needs your value" mark on a placeholder, and the suggested
 * values as buttons (from the user's other blades, or a standard environment variable). `onValue` gets
 * every change; `commit` (optional) a finished one: Enter, leaving the field, or a suggestion. */
export function settingField(setting: BladeSetting, onValue: (value: string) => void, commit?: () => void): HTMLElement {
  const input = h("input", {
    type: setting.type === "number" ? "number" : "text",
    value: String(setting.value),
    spellcheck: "false",
    "aria-label": `${setting.key} (${setting.name})`,
    class: setting.placeholder ? "needs-value" : undefined,
  });
  input.addEventListener("input", () => onValue(input.value));
  if (commit) input.addEventListener("change", commit);
  const chips = setting.suggestions.slice(0, 4).map((s) =>
    button(s.value, () => {
      input.value = s.value;
      onValue(s.value);
      commit?.();
    }, { class: "chip suggestion", title: s.from }),
  );
  return h(
    "div",
    { class: "setting-row" },
    h(
      "label",
      {},
      h("span", { class: "setting-key" }, setting.key),
      h("span", { class: "hint" }, setting.name !== setting.key.toLowerCase() ? ` ${setting.name}, line ${setting.line}` : ` line ${setting.line}`),
      setting.placeholder ? h("span", { class: "needs-value-badge" }, "needs your value") : null,
    ),
    input,
    chips.length ? h("div", { class: "chips suggestions" }, h("span", { class: "hint" }, "Suggested:"), ...chips) : null,
  );
}

export interface Template {
  id: string;
  label: string;
  group: string;
  kind: BladeKind;
  dialect: string;
  code: string;
  variable: string;
  catalog: CatalogCommand | null;
  vault_mapping: { env: string; secret: string }[];
  note: string;
}

const KIND_LABELS: Record<BladeKind, string> = {
  sql: "SQL connection",
  other: "Other",
  vault: "Vault",
  secret: "Secret",
  analysis: "Analysis",
  snippet: "Snippet",
};

/** "a, b,c" -> ["a", "b", "c"]: tags as typed, commas between. */
export function splitTags(text: string): string[] {
  return text.split(",").map((t) => t.trim()).filter(Boolean);
}

export function kindLabel(kind: BladeKind): string {
  return KIND_LABELS[kind];
}

const path = (name: string): string => `/blades/${encodeURIComponent(name)}`;

let templatesCache: Promise<Template[]> | null = null;
export function templates(): Promise<Template[]> {
  templatesCache ??= api<{ templates: Template[] }>("/blades/templates").then((r) => r.templates);
  return templatesCache;
}

/** The line a blade drops into a script: `conn = sab.blade("Warehouse")`. */
export function bladeLine(blade: { name: string; kind: BladeKind; variable: string | null; connection?: string | null }): string {
  const call = `sab.${blade.connection ? "connection" : "blade"}(${JSON.stringify(blade.name)})`;
  return blade.kind === "vault" || blade.kind === "secret" || !blade.variable ? call : `${blade.variable} = ${call}`;
}

// ===== running a blade =====

/** Ask for the values a secret blade holds, for this one run (never kept). */
function askTyped(needs: Record<string, string>, action: string): Promise<Record<string, string> | null> {
  return new Promise((resolve) => {
    const { body, foot, close, dialog } = openDialog(`Values for this ${action}`);
    const inputs = new Map<string, HTMLInputElement>();
    for (const [env, source] of Object.entries(needs)) {
      const input = h("input", { type: "password", autocomplete: "off", "aria-label": env });
      inputs.set(env, input);
      body.append(h("label", { class: "field" }, h("span", {}, `${env} `, h("span", { class: "hint" }, `(${source})`)), input));
    }
    let answered = false;
    const finish = (values: Record<string, string> | null): void => {
      answered = true;
      close();
      resolve(values);
    };
    dialog.addEventListener("close", () => {
      if (!answered) resolve(null);
    });
    foot.append(
      button("Cancel", () => finish(null), { class: "ghost" }),
      button("Run", () => {
        const values: Record<string, string> = {};
        for (const [env, input] of inputs) {
          if (!input.value) {
            input.focus();
            toast(`Type ${env}.`, "error");
            return;
          }
          values[env] = input.value;
        }
        finish(values);
      }, { class: "primary" }),
    );
    inputs.values().next().value?.focus();
  });
}

interface RunFailure {
  error?: string;
  missing?: Missing;
  install_here?: string;
  needs?: Record<string, string>;
}

function failureOf(error: unknown): RunFailure | null {
  if (!(error instanceof ApiError) || (error.status !== 409 && error.status !== 422)) return null;
  try {
    return JSON.parse(error.message) as RunFailure;
  } catch {
    return null;
  }
}

/** Run a blade on the server (Refresh: its catalog; Test: does it work). Asks for secret-blade
 * values when needed, and offers to install a missing driver. Returns the answer, or null. */
export async function runBlade<T>(name: string, action: "refresh" | "test"): Promise<T | null> {
  let env: Record<string, string> = {};
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      return await api<T>(`${path(name)}/${action}`, "POST", { env });
    } catch (error) {
      const failure = failureOf(error);
      if (failure?.needs) {
        const typed = await askTyped(failure.needs, action === "refresh" ? "refresh" : "test");
        if (!typed) return null;
        env = { ...env, ...typed };
        continue;
      }
      if (failure?.missing) {
        // Stopped on a missing package: the prompt in the user's face; installed, the run goes again.
        const installed = await promptInstall(failure.missing);
        if (installed) continue;
        showRunError(name, failure);
        return null;
      }
      if (failure?.error) {
        showRunError(name, failure);
        return null;
      }
      toast((error as Error).message, "error");
      return null;
    }
  }
  return null;
}

function showRunError(name: string, failure: RunFailure): void {
  const { body, foot, close } = openDialog(`${name} did not run`, true);
  body.append(h("pre", { class: "code-box" }, failure.error ?? ""));
  if (failure.missing) body.append(h("p", { class: "install-note" }, reminder(failure.missing, { then: () => close() })));
  foot.append(button("Close", close, { class: "ghost" }));
}

/** Install packages into Swiss Army Bench's own Python, on the user's click. */
export async function install(packages: string[]): Promise<boolean> {
  toast(`Installing ${packages.join(", ")}...`);
  try {
    const result = await api<{ ok: boolean; output: string }>("/blades/install", "POST", { packages });
    toast(`Installed ${packages.join(", ")}.`);
    return result.ok;
  } catch (error) {
    const { body, foot, close } = openDialog("Install failed", true);
    body.append(h("pre", { class: "code-box" }, installError(error)));
    foot.append(button("Close", close));
    return false;
  }
}


// ===== New blade: a file from a template, then edited in the user's own editor =====

interface NewChoice {
  id: string;
  label: string;
  group: string;
  kind: BladeKind;
}

/** Show a blade's file in the system's file manager (the user's click; the agent is refused). */
export async function showFile(name: string): Promise<void> {
  try {
    await api(`${path(name)}/show`, "POST");
  } catch (error) {
    toast((error as Error).message, "error");
  }
}

/** "New blade": the templates by group. A pick makes a new .blade.py in the library's blades/ folder and
 *  shows it in its folder; `onMade` gets its name (the page opens its screen). */
export async function showTemplatePicker(host: HTMLElement, onMade: (name: string) => void): Promise<void> {
  clear(host, h("h2", {}, "New blade"), h("p", { class: "hint" }, "Loading..."));
  let all: NewChoice[];
  try {
    all = (await api<{ choices: NewChoice[] }>("/blades/new")).choices;
  } catch (error) {
    toast((error as Error).message, "error");
    return;
  }
  const groups = new Map<string, NewChoice[]>();
  for (const choice of all) groups.set(choice.group, [...(groups.get(choice.group) ?? []), choice]);
  const make = async (choice: NewChoice): Promise<void> => {
    try {
      const made = await api<BladeSummary>("/blades/new", "POST", { template: choice.id });
      onMade(made.name);
      void showFile(made.name);
    } catch (error) {
      toast((error as Error).message, "error");
    }
  };
  clear(
    host,
    h("h2", {}, "New blade"),
    h(
      "div",
      { class: "template-groups" },
      ...[...groups.entries()].map(([group, list]) =>
        h("section", {}, h("h3", {}, group), h("ul", {}, ...list.map((choice) => h("li", {}, button(choice.label, () => void make(choice)))))),
      ),
    ),
  );
}

// ===== the blade screen: its code read-only (edited in its file), its name, words and table name =====

/** Monaco, loaded when a blade screen first opens; its styles with it. */
let editors: Promise<typeof import("./lazy/codeEditor")> | null = null;
function loadEditors(): Promise<typeof import("./lazy/codeEditor")> {
  if (!document.querySelector('link[href="/static/build/lazy/codeEditor.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/build/lazy/codeEditor.css" }));
  }
  return (editors ??= import(/* external */ "/static/build/lazy/codeEditor.js" as string) as Promise<typeof import("./lazy/codeEditor")>);
}

const LANGUAGES: Record<string, EditorLanguage> = { dax: "dax", html: "html", markdown: "markdown", python: "python", streamlit: "python", sql: "sql", typescript: "typescript", tsx: "tsx" };

/** Code shown read-only: its language's colours, line numbers, as tall as the code (a few lines at least,
 *  about 70% of the window at most, then it scrolls; wide lines scroll sideways). A plain box until Monaco
 *  has loaded. */
export function codeViewer(code: string, language: string, label: string): HTMLElement {
  const host = h("div", { class: "blade-code", "aria-label": label, "data-lines": String(code.split("\n").length) }, h("pre", { class: "code-box blade-code-plain" }, code));
  void loadEditors().then(
    (m) => {
      // Drawn once it is on the page (the screen appends it after this returns).
      const whenShown = (left: number): void => {
        if (host.isConnected) mount(m);
        else if (left > 0) requestAnimationFrame(() => whenShown(left - 1));
      };
      whenShown(120);
    },
    () => undefined, // the plain box stays
  );
  let mounted = false;
  function mount(m: typeof import("./lazy/codeEditor")): void {
    if (mounted || !host.isConnected) return;
    mounted = true;
    const box = h("div", { class: "blade-code-monaco" });
    host.replaceChildren(box);
    m.createCodeEditor(box, {
      language: LANGUAGES[language] ?? "python",
      value: code,
      theme: effectiveTheme(),
      readOnly: true,
      readOnlyMessage: "A blade's code is edited in its file.",
      fit: { min: 4, maxShare: 0.7 },
    });
  }
  return host;
}

/** Open the screen of a blade (`name`). `onSaved` gets the name it was saved under; `onClosed` runs when
 *  the user leaves. The arguments after `name` are the old editor's and ignored. */
export async function editBlade(
  host: HTMLElement,
  name: string | null,
  _template: Template | null,
  _kind: BladeKind,
  onSaved: (name: string) => void,
  onClosed: () => void,
): Promise<void> {
  if (name === null) {
    await showTemplatePicker(host, (made) => {
      onSaved(made);
      void editBlade(host, made, null, "other", onSaved, onClosed);
    });
    return;
  }
  let detail: BladeDetail;
  try {
    detail = await api<BladeDetail>(path(name));
  } catch (error) {
    toast((error as Error).message, "error");
    return;
  }
  const starter = detail.source === "starter";
  const pack = Boolean(detail.pack) && !starter;
  const readOnly = starter || pack;
  let savedName = detail.name;
  const typedSecrets = new Map<string, string>();
  const status = h("div", { class: "status-line", role: "status", "aria-live": "polite" });
  const say = (text: string, kindOf: "" | "error" | "ok" = ""): void => {
    status.textContent = text;
    status.className = `status-line ${kindOf}`;
  };

  // ----- what the app changes: its file's header (name, description, tags, table name) -----
  const nameInput = h("input", { type: "text", value: detail.name, maxlength: "64", "aria-label": "Blade name", spellcheck: "false", readonly: readOnly });
  const descriptionInput = h("textarea", { rows: "2", maxlength: "2000", "aria-label": "Description", readonly: readOnly }) as HTMLTextAreaElement;
  descriptionInput.value = detail.description ?? "";
  const tagsInput = h("input", { type: "text", value: (detail.tags ?? []).join(", "), "aria-label": "Tags", spellcheck: "false", readonly: readOnly });

  // Its table's own name, checked as it is typed (debounced): "available", or why not.
  const tableInput = h("input", { type: "text", value: detail.table ?? "", maxlength: "64", "aria-label": "Its table is called", spellcheck: "false", placeholder: detail.variable ?? "", readonly: readOnly });
  const tableSaid = h("div", { class: "table-name-check", role: "status", "aria-live": "polite" });
  let tableOk = true;
  let checkTimer = 0;
  let asked = 0;
  async function checkTable(): Promise<void> {
    const wanted = tableInput.value.trim();
    const mine = ++asked;
    if (!wanted || wanted === (detail.table ?? "")) {
      tableOk = true;
      tableSaid.textContent = "";
      tableSaid.className = "table-name-check";
      return;
    }
    try {
      const answer = await api<{ available: boolean; said: string }>(`/blades/table-name?name=${encodeURIComponent(wanted)}&blade=${encodeURIComponent(savedName)}`);
      if (mine !== asked) return; // a newer check is on its way
      tableOk = answer.available;
      tableSaid.textContent = answer.said;
      tableSaid.className = `table-name-check ${answer.available ? "ok" : "error"}`;
    } catch (error) {
      if (mine === asked) tableSaid.textContent = (error as Error).message;
    }
  }
  tableInput.addEventListener("input", () => {
    window.clearTimeout(checkTimer);
    checkTimer = window.setTimeout(() => void checkTable(), 250);
  });

  // ----- the code: read-only, edited in its file -----
  const language = detail.kind === "snippet" ? detail.language || "python" : "python";
  const code = codeViewer(detail.kind === "secret" ? detail.env_names.join("\n") : detail.code, detail.kind === "secret" ? "plaintext" : language, "Blade code");
  const fileLine = detail.file ? h("p", { class: "hint blade-file-path" }, h("code", {}, detail.file)) : null;
  const codeActions = h(
    "div",
    { class: "row-actions" },
    readOnly
      ? button("Copy as your own", () => void copyStarter(detail.name), { class: "primary", icon: "copy" })
      : button("Show its file", () => void showFile(savedName), { icon: "folder" }),
  );
  async function copyStarter(of: string): Promise<void> {
    const made = await copyAsOwn(of);
    if (!made) return;
    onSaved(made);
    await editBlade(host, made, null, "other", onSaved, onClosed);
  }

  // What the code makes, its secrets (kept in the operating system's vault) and missing packages.
  const inspection = detail.inspect ?? null;
  const madeLine = detail.kind === "snippet" || detail.kind === "secret" || !detail.variable ? null : h("p", { class: "hint" }, `${detail.kind === "vault" ? "The function that reads a secret" : "It makes"} `, h("code", {}, detail.variable));
  const secretsHost = h("div", {});
  for (const secret of inspection?.secrets ?? []) {
    const saved = detail.secrets[secret] === true;
    const input = h("input", { type: "password", autocomplete: "new-password", placeholder: saved ? "Saved" : "Not saved", "aria-label": `secret ${secret}` });
    input.addEventListener("input", () => typedSecrets.set(secret, input.value));
    const forget = saved
      ? button("Forget", () => {
          void api(`${path(savedName)}/secrets`, "PUT", { [secret]: null }).then(() => {
            detail.secrets[secret] = false;
            input.placeholder = "Not saved";
            forget?.remove();
            say(`Forgot ${secret}.`, "ok");
          }, (error: Error) => say(error.message, "error"));
        }, { class: "ghost" })
      : null;
    secretsHost.append(h("label", {}, h("span", {}, `secret("${secret}")`), h("div", { class: "row-actions" }, input, forget)));
  }
  const missing = (inspection?.packages ?? []).filter((p) => !p.installed);
  const packagesHost = missing.length
    ? h(
        "div",
        { class: "row-actions" },
        h("div", { class: "chips" }, ...missing.map((p) => h("span", { class: "chip missing", title: p.guessed ? "Guessed name" : p.module }, `${p.pip} missing`))),
        inspection?.missing ? reminder(inspection.missing, { then: () => void editBlade(host, savedName, null, "other", onSaved, onClosed) }) : null,
      )
    : null;
  const vaultRows = detail.kind === "vault" && detail.vault_mapping.length
    ? h("table", { class: "columns-table" }, h("tbody", {}, ...detail.vault_mapping.map((m) => h("tr", {}, h("td", {}, h("code", {}, m.env)), h("td", { class: "hint" }, "←"), h("td", {}, m.secret)))))
    : null;

  // A connection's tables are always listed; the query that lists them is its file's, shown read-only.
  const listing = detail.connection && detail.connection !== "vault" && detail.catalog
    ? h(
        "details",
        { class: "blade-listing" },
        h("summary", {}, "How its tables are listed"),
        codeViewer(detail.catalog.command, detail.catalog.language, "How its tables are listed"),
      )
    : null;
  // Opened: the viewer measures itself again (it was folded away when drawn).
  listing?.addEventListener("toggle", () => window.dispatchEvent(new Event("resize")));

  function body(): Record<string, unknown> {
    const out: Record<string, unknown> = { name: nameInput.value.trim(), description: descriptionInput.value.trim(), tags: splitTags(tagsInput.value) };
    if (detail.names_table) out.table = tableInput.value.trim();
    const secrets = Object.fromEntries([...typedSecrets].filter(([, value]) => value));
    if (Object.keys(secrets).length) out.secrets = secrets;
    return out;
  }

  async function save(): Promise<void> {
    if (detail.names_table) await checkTable();
    if (!tableOk) {
      say(tableSaid.textContent ?? "", "error");
      tableInput.focus();
      return;
    }
    say("Saving...");
    try {
      const saved = await api<BladeSummary>(path(savedName), "PUT", body());
      savedName = saved.name;
      detail.table = saved.table ?? "";
      typedSecrets.clear();
      say(`Saved ${saved.name}.`, "ok");
      onSaved(saved.name);
    } catch (error) {
      say((error as Error).message, "error");
    }
  }

  async function remove(): Promise<void> {
    const target = savedName;
    const { body: dialogBody, foot, close } = openDialog(`Remove ${target}?`);
    dialogBody.append(h("p", {}, "Its file and its saved secrets go."));
    foot.append(
      button("Cancel", close, { class: "ghost" }),
      button("Remove", () => {
        close();
        void api(path(target), "DELETE").then(onClosed, (error: Error) => toast(error.message, "error"));
      }, { class: "danger" }),
    );
  }

  const runnable = detail.kind !== "snippet" && detail.kind !== "secret";
  clear(host, h("h2", {}, `Blade: ${detail.name}`));
  append(
    host,
    h(
      "div",
      { class: "editor blade-screen" },
      h("div", { class: "blade-kind-line" }, h("span", { class: `blade-kind ${detail.kind}` }, kindLabel(detail.kind)), starter ? h("span", { class: "warning-text" }, `${detail.family ?? ""} starter: read-only`.trim()) : pack ? h("span", { class: "warning-text" }, `From the pack ${detail.pack}: read-only`) : null),
      h("label", {}, h("span", {}, "Name"), nameInput),
      h("label", {}, h("span", {}, "Description"), descriptionInput),
      h("label", {}, h("span", {}, "Tags"), tagsInput),
      detail.names_table ? h("div", { class: "table-name-field" }, h("label", {}, h("span", {}, "Its table is called"), tableInput), tableSaid) : null,
      h("fieldset", { class: "blade-code-field" }, h("legend", {}, "Code"), code, fileLine, codeActions, madeLine, secretsHost, packagesHost, vaultRows),
      listing,
      h(
        "div",
        { class: "row-actions" },
        readOnly ? null : button("Save", () => void save(), { class: "primary", icon: "save" }),
        runnable ? button("Test", () => void runBlade<{ type?: string; variables?: string[] }>(savedName, "test").then((a) => a && say(a.variables ? `It works: it sets ${a.variables.join(", ")}.` : a.type ? `It works: it makes a ${a.type}.` : "It works.", "ok")), { icon: "check" }) : null,
        button("Cancel", onClosed, { class: "ghost" }),
        button("Export", () => void exportBlades(savedName), { icon: "export", class: "ghost", title: "Download as .blade.py" }),
        detail.removable ? button("Remove", () => void remove(), { class: "danger", icon: "trash" }) : null,
      ),
      status,
    ),
  );
  nameInput.focus();
  // Opened with packages missing: the prompt in the user's face.
  if (inspection?.missing) void promptInstall(inspection.missing, { then: () => void editBlade(host, savedName, null, "other", onSaved, onClosed) });
}
