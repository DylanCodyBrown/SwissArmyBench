/**
 * bladeEditor.ts: the blade screen, New blade, and running a blade (Refresh, Test). [VIEW]
 *
 * A blade is saved Python that reaches outside Python to load something (plan decisions 14-16). Its screen
 * is an IDE (the owner, 2026-11-21: "This is an IDE not a save form"; codeIde.ts): the code editable with the
 * Workbench's intelligence, ▶ Run with its output, result and problems below, Properties at the right (the
 * file's header: name, description, tags, a table blade's table name checked as it is typed; the secrets it
 * asks for, typed into the system's vault; missing packages; a connection's listing query). Save writes the
 * file (only when its bytes change); an edit made outside is noticed (Reload / Keep mine). A starter's Save
 * is refused: Copy as your own. New blade makes a file from a template.
 *
 * The pieces a page's tab mounts on its own (the Scripts page's blade tab): bladeProperties, runBladeCode
 * (into codeIde.ts's runPanel), watchOutsideEdits, bladeEditorIntel, bladeLanguage, saveBladeAs; editBlade
 * composes them into the standalone screen.
 */
import { api, ApiError, headers } from "./api";
import { button, clear, formatCount, h, icon, openDialog, toast } from "./dom";
import type { CodeEditor, CodeEditorOptions, EditorLanguage, Problem } from "./lazy/codeEditor";
import { busyClick, loadingBlock } from "./loading";
import { effectiveTheme } from "./theme";
import { exportBlades } from "./bladeLibrary";
import { copyAsOwn } from "./starters";
import { installError, type Missing, promptInstall, reminder } from "./missingPackages";
import { variableBox } from "./variableBox";
import { errorHere, errorNote } from "./errorNote";
import { type CodeIde, codeIde, type IdeOutput, loadEditors } from "./codeIde";
import { inlineSource } from "./inlineCompletion";
import { whenMode } from "./modes";
import { sendToAgent } from "./workbenchAgent";
import { type ErrorDetail, errorPanel, type Frame, problemsFor, yourFrame } from "./workbenchErrors";
import { pythonIntel, showProblems } from "./workbenchIntel";

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

export interface BladeDetail extends BladeSummary {
  /** The file's stamp: a Save is refused (409) when the file changed on disk since (domain/blade_tables.py). */
  stamp?: string;
  /** A starter's or a pack's: Save is refused (Copy as your own). */
  read_only?: boolean;
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
  /** Every header field its kind has (domain/blade_header.py): the Properties pane draws them. */
  header?: HeaderField[];
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
  /** Its box's text (12.7): the value, or a dollar-brace reference where the code reads a variable. */
  text?: string;
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
  // One box (12.7): a value, or a variable with a dollar-brace that the code reads where it runs.
  const input = h("input", {
    type: "text",
    inputmode: setting.type === "number" ? "numeric" : "text",
    value: setting.text ?? String(setting.value),
    spellcheck: "false",
    "aria-label": `${setting.key} (${setting.name})`,
    class: setting.placeholder ? "needs-value" : undefined,
  }) as HTMLInputElement;
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
    variableBox(input, { label: setting.key }),
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
            errorHere(`Type ${env}.`);
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
  return error.said as RunFailure | null;
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
      errorHere(error);
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


// ===== New blade: a file from a template, then opened in the IDE =====

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
    errorHere(error);
  }
}

/** New blade's kinds (domain/blade_header.py SCAFFOLD_KINDS) in its words. */
export const NEW_KINDS: { id: string; label: string; hint: string }[] = [
  { id: "table", label: "Table", hint: "a function that returns a DataFrame" },
  { id: "code", label: "Code", hint: "any Python; what it makes last is handed back" },
  { id: "analysis", label: "Analysis", hint: "a function of a table's rows, for Analyze" },
  { id: "connection", label: "Connection", hint: "a database that lists and reads its tables" },
  { id: "snippet", label: "Snippet", hint: "text for a cell, with <<placeholders>>" },
  { id: "secret", label: "Secret", hint: "variables typed each session, never kept" },
];

/** New blade (the owner, 2026-11-21: "we should scaffold a blank blade for the user"): a name and a kind
 *  only; the server writes that kind's blank, working blade. Answers the made blade's name and the line its
 *  body starts on, or null (cancelled). */
export function newBladeDialog(): Promise<{ name: string; line: number } | null> {
  return new Promise((resolve) => {
    const { body, foot, close, dialog } = openDialog("New blade");
    const input = h("input", { type: "text", maxlength: "64", "aria-label": "Name", spellcheck: "false", placeholder: "Orders" }) as HTMLInputElement;
    const said = h("div", { class: "table-name-check", role: "status", "aria-live": "polite" });
    let kind = "table";
    const kinds = h(
      "div",
      { class: "new-blade-kinds", role: "radiogroup", "aria-label": "Kind" },
      ...NEW_KINDS.map((k) => {
        const radio = h("input", { type: "radio", name: "new-blade-kind", value: k.id, checked: k.id === kind }) as HTMLInputElement;
        radio.addEventListener("change", () => (kind = k.id));
        return h("label", { class: "new-blade-kind" }, radio, h("span", {}, h("strong", {}, k.label), h("span", { class: "hint" }, ` ${k.hint}`)));
      }),
    );
    let free = false;
    let timer = 0;
    let mine = 0;
    const check = async (): Promise<void> => {
      const asking = ++mine;
      if (!input.value.trim()) {
        free = false;
        said.textContent = "";
        return;
      }
      const answer = await api<{ available: boolean; said: string }>(`/blades/name-check?name=${encodeURIComponent(input.value)}`).catch(() => ({ available: false, said: "" }));
      if (asking !== mine) return;
      free = answer.available;
      said.textContent = answer.said;
      said.className = `table-name-check ${answer.available ? "ok" : "error"}`;
    };
    input.addEventListener("input", () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void check(), 200);
    });
    body.append(h("label", { class: "field" }, h("span", {}, "Name"), input), said, kinds);
    let answered = false;
    dialog.addEventListener("close", () => {
      if (!answered) resolve(null);
    });
    const go = async (): Promise<void> => {
      window.clearTimeout(timer); // the check a keystroke set off would win over this one's
      await check();
      if (!free) return input.focus();
      try {
        const made = await api<{ name: string; line?: number }>("/blades/new", "POST", { name: input.value.trim(), kind });
        answered = true;
        close();
        resolve({ name: made.name, line: made.line ?? 1 });
      } catch (error) {
        errorHere(error);
      }
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") void go();
    });
    foot.append(button("Cancel", close, { class: "ghost" }), button("Create", busyClick("Creating…", go), { class: "primary" }));
    input.focus();
  });
}

/** "New blade": the templates by group. A pick makes a new .blade.py in the library's blades/ folder;
 *  `onMade` gets its name (the page opens its IDE). */
export async function showTemplatePicker(host: HTMLElement, onMade: (name: string) => void): Promise<void> {
  clear(host, h("h2", {}, "New blade"), loadingBlock("Loading the templates…"));
  let all: NewChoice[];
  try {
    all = (await api<{ choices: NewChoice[] }>("/blades/new")).choices;
  } catch (error) {
    errorHere(error);
    return;
  }
  const groups = new Map<string, NewChoice[]>();
  for (const choice of all) groups.set(choice.group, [...(groups.get(choice.group) ?? []), choice]);
  const make = async (choice: NewChoice): Promise<void> => {
    try {
      const made = await api<BladeSummary>("/blades/new", "POST", { template: choice.id });
      onMade(made.name);
    } catch (error) {
      errorHere(error);
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

// ===== the blade screen: an IDE (the owner, 2026-11-21: "This is an IDE not a save form") =====

const LANGUAGES: Record<string, EditorLanguage> = { dax: "dax", html: "html", markdown: "markdown", python: "python", streamlit: "python", sql: "sql", typescript: "typescript", tsx: "tsx" };

/** Code shown read-only (a connection's listing query): its language's colours, line numbers, as tall as the
 *  code (a few lines at least, about 70% of the window at most, then it scrolls). A plain box until Monaco
 *  has loaded. */
export function codeViewer(code: string, language: string, label: string): HTMLElement {
  const host = h("div", { class: "blade-code", "aria-label": label, "data-lines": String(code.split("\n").length) }, h("pre", { class: "code-box blade-code-plain" }, code));
  void loadEditors().then(
    (m) => {
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
    m.createCodeEditor(box, { language: LANGUAGES[language] ?? "python", value: code, theme: effectiveTheme(), readOnly: true, readOnlyMessage: "Read-only here.", fit: { min: 4, maxShare: 0.7 } });
  }
  return host;
}

/** What secret() is to the lint and the completion (the run gives it): domain/blade_tables.py SECRET_STUB. */
const SECRET_STUB = "def secret(name: str) -> str: ...\n";

/** A run's answer (services/blades.py run). */
interface RunAnswer {
  run: string;
  ok: boolean;
  seconds?: number;
  output: { stream: "stdout" | "stderr"; text: string }[];
  result: RunResult | null;
  error?: string;
  refusal?: Record<string, unknown> & { missing?: Missing };
  error_detail?: ErrorDetail;
  cancelled?: boolean;
  needs?: Record<string, string>;
}

type RunResult =
  | { kind: "table"; type: string; made_by: string | null; columns: string[]; types: string[]; rows: unknown[][]; total: number }
  | { kind: "value"; type: string; made_by: string | null; text: string };

/** A run streamed from the server: each line of output as it comes, then the answer. */
async function streamRun(name: string, body: Record<string, unknown>, onOutput: (stream: "stdout" | "stderr", text: string) => void): Promise<RunAnswer> {
  const response = await fetch(`${path(name)}/run`, { method: "POST", headers: headers(true), body: JSON.stringify({ ...body, stream: true }) });
  if (!response.ok || !response.body) throw new ApiError(response.status, await response.text());
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let done: RunAnswer | null = null;
  for (;;) {
    const { value, done: finished } = await reader.read();
    if (value) pending += decoder.decode(value, { stream: true });
    let at: number;
    while ((at = pending.indexOf("\n")) >= 0) {
      const line = pending.slice(0, at).trim();
      pending = pending.slice(at + 1);
      if (!line) continue;
      const item = JSON.parse(line) as { output?: { stream: "stdout" | "stderr"; text: string }; done?: RunAnswer };
      if (item.output) onOutput(item.output.stream, item.output.text);
      if (item.done) done = item.done;
    }
    if (finished) break;
  }
  if (!done) throw new Error("The run ended without an answer.");
  return done;
}

function cell(value: unknown): string {
  return value === null || value === undefined ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** The Result tab: a table as a grid (its count, Open as grid), a value as its text. */
function resultView(name: string, result: RunResult): HTMLElement {
  const by = result.made_by ? h("code", {}, `${result.made_by}()`) : null;
  if (result.kind === "value") {
    return h("div", { class: "ide-result-value" }, h("p", { class: "hint" }, by, by ? " returned " : "It made ", `a ${result.type}`), h("pre", { class: "code-box" }, result.text));
  }
  const open = button("Open as grid", busyClick("Opening…", async () => {
    try {
      await api(`${path(name)}/result/open`, "POST");
    } catch (error) {
      errorHere(error);
    }
  }), { icon: "export", class: "ide-btn" });
  const shown = result.rows.length;
  const count = `${formatCount(result.total)} row${result.total === 1 ? "" : "s"}, ${result.columns.length} column${result.columns.length === 1 ? "" : "s"}`;
  return h(
    "div",
    { class: "ide-result-table" },
    h("div", { class: "ide-result-head" }, h("span", {}, by, by ? " made a table: " : "A table: ", h("strong", { class: "ide-row-count" }, count)), shown < result.total ? h("span", { class: "hint" }, ` (the first ${formatCount(shown)} shown)`) : null, open),
    h(
      "div",
      { class: "ide-grid-wrap" },
      h(
        "table",
        { class: "ide-grid", "aria-label": "Result rows" },
        h("thead", {}, h("tr", {}, ...result.columns.map((c, i) => h("th", { scope: "col", title: result.types[i] ?? "" }, c)))),
        h("tbody", {}, ...result.rows.map((row) => h("tr", {}, ...row.map((v) => h("td", { class: typeof v === "number" ? "num" : undefined }, cell(v)))))),
      ),
    ),
  );
}

// ===== the pieces a page's tab mounts (the Scripts page's blade tab), each on its own =====

/** A blade's Properties: its file's header (name, description, tags, a table blade's table name checked as
 *  it is typed), its secrets (typed into the system's vault), missing packages, a vault's entries, a
 *  connection's listing query, the file's path. The host's Save sends `header()` with the code. */
export interface BladeProperties {
  element: HTMLElement;
  /** The header's fields as PUT /blades/{name} takes them (and typed secrets, when any). */
  header(): Record<string, unknown>;
  /** Unsaved changes in it. */
  dirty(): boolean;
  /** Before a Save: the table name checked; false (its words shown, the field focused) when it is taken. */
  check(): Promise<boolean>;
  /** The table name's refusal, for the host's note. */
  refusal(): string;
  /** Saved: what it holds now is the saved state. */
  markSaved(table: string): void;
  /** Cancel: back to the blade as read. */
  reset(): void;
}

/** One header field as the server lists it (domain/blade_header.py fields). */
export interface HeaderField {
  key: string;
  label: string;
  type: "text" | "textarea" | "tags" | "choice" | "number" | "bool" | "names" | "mapping" | "code" | "readonly";
  value: unknown;
  choices?: string[];
  hint?: string;
  read_only?: boolean;
}

/** The words a field's aria-label is (the older Properties' own: tests and the agent's snapshot read them). */
const FIELD_LABELS: Record<string, string> = { name: "Blade name", table: "Its table is called" };

/** A field's value as its box's text. */
function fieldText(field: HeaderField): string {
  const v = field.value;
  if (Array.isArray(v)) return v.join(", ");
  return v === null || v === undefined ? "" : String(v);
}

/** A number field's own check (the server checks again): the words, or "". */
function numberCheck(key: string, text: string): string {
  if (!text.trim()) return "";
  if (!/^\d+$/.test(text.trim())) return "A whole number.";
  const n = Number(text);
  if (key === "queries.total" && (n < 1 || n > 64)) return "1 to 64 at once.";
  if (key === "queries.wait" && (n < 1 || n > 3600)) return "1 second to an hour.";
  if (key === "row_limit" && n > 50_000_000) return "At most 50,000,000 (0: every row).";
  return "";
}

const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

export function bladeProperties(detail: BladeDetail, options: { readOnly: boolean; name: () => string; changed: () => void; reopen: () => void; code?: () => string }): BladeProperties {
  const readOnly = options.readOnly;
  const fields: HeaderField[] = detail.header?.length
    ? detail.header
    : [
        { key: "name", label: "Name", type: "text", value: detail.name },
        { key: "description", label: "Description", type: "textarea", value: detail.description ?? "" },
        { key: "tags", label: "Tags", type: "tags", value: detail.tags ?? [] },
        ...(detail.names_table ? [{ key: "table", label: "Its table is called", type: "text", value: detail.table ?? "" } as HeaderField] : []),
      ];
  const boxes = new Map<string, { get: () => string; set: (v: string) => void; focus: () => void; said: HTMLElement }>();
  const problems = new Map<string, string>();
  const typedSecrets = new Map<string, string>();
  const asked = new Map<string, number>();
  const timers = new Map<string, number>();

  /** The live check of one field: its words under it, "" when it is fine. */
  async function checkField(key: string): Promise<void> {
    const box = boxes.get(key);
    if (!box) return;
    const text = box.get().trim();
    const field = fields.find((f) => f.key === key)!;
    const mine = (asked.get(key) ?? 0) + 1;
    asked.set(key, mine);
    let words = "";
    let good = "";
    try {
      if (text === fieldText(field).trim()) words = "";
      else if (key === "name") {
        const answer = text.toLowerCase() === options.name().toLowerCase() ? { available: true, said: "" } : await api<{ available: boolean; said: string }>(`/blades/name-check?name=${encodeURIComponent(text)}`);
        if (!answer.available) words = answer.said;
        else good = answer.said;
      } else if (key === "table" && text) {
        const answer = await api<{ available: boolean; said: string }>(`/blades/table-name?name=${encodeURIComponent(text)}&blade=${encodeURIComponent(options.name())}`);
        if (!answer.available) words = answer.said;
        else good = answer.said;
      } else if (key === "variable") {
        if (!text) words = "Name what the code hands back.";
        else if (options.code) {
          const found = await api<{ assigned?: string[] }>("/blades/inspect", "POST", { code: options.code() }).catch(() => ({ assigned: undefined }));
          if (found.assigned && !found.assigned.includes(text)) words = `The code never makes ${text}. It makes: ${found.assigned.join(", ") || "nothing"}.`;
        }
      } else if (field.type === "number") words = numberCheck(key, text);
      else if (field.type === "names") {
        const bad = text.split(/[\n,]/).map((n) => n.trim()).filter((n) => n && !ENV_NAME.test(n));
        if (bad.length) words = `${bad[0]} is not a variable name: letters, digits and _, not starting with a digit.`;
      } else if (field.type === "mapping") {
        const bad = text.split("\n").filter((l) => l.trim() && !/^\s*[A-Za-z_][A-Za-z0-9_]*\s*=\s*\S/.test(l));
        if (bad.length) words = `Each line reads VARIABLE = secret-name, not ${(bad[0] ?? "").trim()}.`;
      } else if (field.type === "tags") {
        const bad = splitTags(text).find((t) => !/^[\w][\w .+#-]{0,39}$/u.test(t));
        if (bad) words = `Tag ${bad}: 1 to 40 letters, digits, spaces or . + # - _.`;
      }
    } catch (error) {
      words = (error as Error).message;
    }
    if (asked.get(key) !== mine) return; // a newer check is on its way
    if (words) problems.set(key, words);
    else problems.delete(key);
    box.said.textContent = words || good;
    box.said.className = `${key === "table" ? "table-name-check" : "ide-prop-check"} ${words ? "error" : good ? "ok" : ""}`;
  }

  function fieldBox(field: HeaderField): HTMLElement {
    const aria = FIELD_LABELS[field.key] ?? field.label;
    const said = h("div", { class: field.key === "table" ? "table-name-check" : "ide-prop-check", role: "status", "aria-live": "polite" });
    const locked = readOnly || field.read_only || field.type === "readonly";
    let el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
    if (field.type === "readonly") {
      const shown = fieldText(field);
      return h("div", { class: "ide-prop-read", "data-key": field.key }, h("span", { class: "ide-prop-label" }, field.label), shown ? h("code", {}, shown) : h("span", { class: "hint" }, "none"));
    }
    if (field.type === "choice") {
      el = h("select", { "aria-label": aria, disabled: locked }, ...(field.choices ?? []).map((c) => h("option", { value: c }, c))) as HTMLSelectElement;
      el.value = fieldText(field);
    } else if (field.type === "bool") {
      el = h("input", { type: "checkbox", "aria-label": aria, disabled: locked }) as HTMLInputElement;
      (el as HTMLInputElement).checked = field.value === true;
    } else if (["textarea", "names", "mapping", "code"].includes(field.type)) {
      el = h("textarea", { rows: field.type === "code" ? "4" : "3", "aria-label": aria, readonly: locked, spellcheck: "false", class: field.type === "code" ? "mono" : undefined }) as HTMLTextAreaElement;
      el.value = field.type === "names" ? fieldText(field).replace(/, /g, "\n") : fieldText(field);
    } else {
      el = h("input", { type: "text", inputmode: field.type === "number" ? "numeric" : "text", "aria-label": aria, readonly: locked, spellcheck: "false", maxlength: field.key === "name" || field.key === "table" ? "64" : undefined, placeholder: field.key === "table" ? (detail.variable ?? "") : undefined }) as HTMLInputElement;
      el.value = fieldText(field);
    }
    const get = (): string => (el instanceof HTMLInputElement && el.type === "checkbox" ? String(el.checked) : el.value);
    const set = (v: string): void => {
      if (el instanceof HTMLInputElement && el.type === "checkbox") el.checked = v === "true";
      else el.value = v;
    };
    boxes.set(field.key, { get, set, focus: () => el.focus(), said });
    const changed = (): void => {
      options.changed();
      window.clearTimeout(timers.get(field.key));
      timers.set(field.key, window.setTimeout(() => void checkField(field.key), 250));
    };
    el.addEventListener("input", changed);
    el.addEventListener("change", changed);
    const label = h("label", { class: field.type === "bool" ? "ide-prop-bool" : undefined }, h("span", {}, field.label, field.hint ? h("span", { class: "hint" }, ` (${field.hint})`) : null), el);
    return h("div", { class: field.key === "table" ? "table-name-field" : "ide-prop-field", "data-key": field.key }, label, said);
  }

  const original = (field: HeaderField): string => (field.type === "bool" ? String(field.value === true) : field.type === "names" ? fieldText(field).replace(/, /g, "\n") : fieldText(field));
  const now = (): string => JSON.stringify([...boxes.entries()].map(([k, b]) => [k, b.get()]).concat([["secrets", String(typedSecrets.size)]]));
  let saved = now();

  const inspection = detail.inspect ?? null;
  const secretsHost = h("div", { class: "ide-secrets" });
  for (const secret of inspection?.secrets ?? []) {
    const isSaved = detail.secrets[secret] === true;
    const input = h("input", { type: "password", autocomplete: "new-password", placeholder: isSaved ? "Saved" : "Not saved", "aria-label": `secret ${secret}` });
    input.addEventListener("input", () => {
      typedSecrets.set(secret, input.value);
      options.changed();
    });
    const forget = isSaved
      ? button("Forget", () => {
          void api(`${path(options.name())}/secrets`, "PUT", { [secret]: null }).then(() => {
            detail.secrets[secret] = false;
            input.placeholder = "Not saved";
            forget?.remove();
          }, (error: Error) => errorHere(error));
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
        inspection?.missing ? reminder(inspection.missing, { then: options.reopen }) : null,
      )
    : null;
  const starter = detail.source === "starter";
  const shown = fields.filter((f) => f.key !== "kind" && f.key !== "secrets");
  const element = h(
    "div",
    { class: "editor ide-props-form" },
    h("div", { class: "blade-kind-line" }, h("span", { class: `blade-kind ${detail.kind}` }, kindLabel(detail.kind)), starter ? h("span", { class: "warning-text" }, `${detail.family ?? ""} starter: read-only`.trim()) : detail.pack ? h("span", { class: "warning-text" }, `From the pack ${detail.pack}: read-only`) : null),
    ...shown.map(fieldBox),
    secretsHost,
    packagesHost,
    detail.file ? h("p", { class: "hint blade-file-path" }, h("code", {}, detail.file)) : null,
  );
  saved = now();
  return {
    element,
    header: () => {
      const out: Record<string, unknown> = {};
      for (const field of fields) {
        const box = boxes.get(field.key);
        if (!box || field.read_only) continue;
        const text = box.get();
        // name, description and tags always go (the older Save's shape); the rest only when changed.
        if (!["name", "description", "tags", "table"].includes(field.key) && text === original(field)) continue;
        out[field.key] = field.type === "tags" ? splitTags(text) : field.type === "bool" ? text === "true" : field.type === "names" ? text.split(/[\n,]/).map((n) => n.trim()).filter(Boolean) : field.type === "number" ? (text.trim() === "" ? null : Number(text)) : field.key === "description" || field.key === "name" || field.key === "table" ? text.trim() : text;
      }
      const secrets = Object.fromEntries([...typedSecrets].filter(([, value]) => value));
      if (Object.keys(secrets).length) out.secrets = secrets;
      return out;
    },
    dirty: () => now() !== saved,
    check: async () => {
      for (const key of boxes.keys()) await checkField(key);
      const first = [...problems.keys()][0];
      if (first) boxes.get(first)?.focus();
      return problems.size === 0;
    },
    refusal: () => [...problems.values()][0] ?? "",
    markSaved: (table) => {
      detail.table = table;
      for (const field of fields) {
        const box = boxes.get(field.key);
        if (!box) continue;
        const text = box.get();
        field.value = field.type === "tags" ? splitTags(text) : field.type === "bool" ? text === "true" : field.type === "names" ? text.split(/[\n,]/).map((n) => n.trim()).filter(Boolean) : text;
      }
      typedSecrets.clear();
      for (const input of secretsHost.querySelectorAll("input")) input.value = "";
      saved = now();
    },
    reset: () => {
      for (const field of fields) boxes.get(field.key)?.set(original(field));
      typedSecrets.clear();
      problems.clear();
      for (const box of boxes.values()) box.said.textContent = "";
      for (const input of secretsHost.querySelectorAll("input")) input.value = "";
      saved = now();
    },
  };
}

/** Where a blade's run shows: the panel's Result and tabs, and the editor (squiggles, fixes, its lines). */
export interface RunView {
  showResult(content: HTMLElement | null): void;
  showTab(tab: "output" | "result" | "problems"): void;
  setRunProblems(list: Problem[]): void;
  editor: Promise<CodeEditor>;
  /** Run again (a package installed). */
  again: () => void;
}

/** Run a blade's code (the editor's, saved or not) as the IDE's ▶ does: streamed into `output`, then its
 *  result (a table as a grid with its count and Open as grid, a value as its text) or the error panel with
 *  the line marked; a secret blade's values asked for this run; `abort` stops it on the server. */
export async function runBladeCode(name: string, code: string, abort: AbortController, output: IdeOutput, view: RunView): Promise<void> {
  const runId = Math.random().toString(36).slice(2, 12);
  abort.signal.addEventListener("abort", () => void api(`/blades/runs/${runId}/cancel`, "POST").catch(() => undefined), { once: true });
  let env: Record<string, string> = {};
  let answer: RunAnswer;
  for (let attempt = 0; ; attempt++) {
    try {
      answer = await streamRun(name, { code, env, run: runId }, (stream, words) => output.write(stream, words));
    } catch (error) {
      view.showResult(errorNote(error));
      view.showTab("result");
      return;
    }
    if (answer.needs && attempt < 2) {
      const typed = await askTyped(answer.needs, "run");
      if (!typed) return;
      env = { ...env, ...typed };
      continue;
    }
    break;
  }
  if (answer.ok && answer.result) {
    output.write("note", `\nRan in ${answer.seconds ?? 0} s.\n`);
    view.showResult(resultView(name, answer.result));
    view.showTab("result");
    return;
  }
  if (answer.cancelled) {
    output.write("note", "\nStopped.\n");
    return;
  }
  const detailOf = answer.error_detail;
  if (detailOf?.chain?.length) {
    const editor = await view.editor;
    const yours = (f: Frame): { line: number; colShift: number } | null => (f.where === "file" || f.where === "cell" ? { line: f.line, colShift: 0 } : null);
    view.setRunProblems(problemsFor(detailOf, yours));
    view.showResult(
      errorPanel(detailOf, null, {
        fix: (fix) => {
          const wanted = fix.missing ?? detailOf.missing;
          if (fix.kind === "install" && wanted) void promptInstall(wanted, { then: view.again });
          else if (fix.kind === "replace" || fix.kind === "import") editor.applyFix(fix, yourFrame(detailOf.chain[detailOf.chain.length - 1])?.line ?? 1);
        },
        goTo: (frame) => {
          if (frame.where !== "file" && frame.where !== "cell") return false;
          editor.reveal(frame.line, frame.col ?? 1);
          return true;
        },
      }),
    );
    if (detailOf.missing) void promptInstall(detailOf.missing, { then: view.again });
  } else {
    view.showResult(errorNote(answer.refusal ?? answer.error ?? "It did not run."));
    if (answer.refusal?.missing) void promptInstall(answer.refusal.missing, { then: view.again });
  }
  view.showTab("result");
}

/** An edit made outside to an open blade's file (the user's own editor), looked for every 2 s while
 *  `alive()`: with no unsaved changes the editor takes it at once; with some, a note asks Reload or Keep
 *  mine (never saved over by itself). A Save refused with 409 shows the same note (`changed`). */
export interface OutsideEdits {
  /** The stamp a Save sends (the file as the editor last read it, or Keep mine's). */
  stamp(): string;
  /** The file as saved or read now: its stamp. */
  setStamp(stamp: string): void;
  /** The file changed on disk: the note. */
  changed(stamp: string): void;
  stop(): void;
}

export function watchOutsideEdits(options: {
  name: () => string;
  file: string;
  stamp: string;
  alive: () => boolean;
  dirty: () => boolean;
  /** The file's code put in the editor as its saved text. */
  load: (code: string) => void;
  note: (content: HTMLElement | null) => void;
}): OutsideEdits {
  let stamp = options.stamp;
  let seen = options.stamp;
  const changed = (now: string): void => {
    seen = now;
    const file = (options.file || options.name()).split(/[\\/]/).pop();
    options.note(
      h(
        "div",
        { class: "ide-note-row warn", role: "alert" },
        icon("warning"),
        h("span", {}, `${file} changed on disk.`),
        button("Reload", () => void reload(), { class: "primary ide-btn" }),
        button("Keep mine", () => {
          stamp = now; // the next Save goes over it, on this word
          options.note(null);
        }, { class: "ghost ide-btn" }),
      ),
    );
  };
  async function reload(): Promise<void> {
    const found = await api<{ code: string; stamp: string }>(`${path(options.name())}/code`);
    stamp = seen = found.stamp;
    options.load(found.code);
    options.note(null);
  }
  const timer = window.setInterval(() => {
    if (!options.alive()) return window.clearInterval(timer);
    if (window.document.hidden || !options.file) return;
    void api<{ code: string; stamp: string }>(`${path(options.name())}/code`).then((found) => {
      if (!found.stamp || found.stamp === seen) return;
      if (!options.dirty()) {
        stamp = seen = found.stamp;
        options.load(found.code);
        return;
      }
      changed(found.stamp);
    }, () => undefined);
  }, 2000);
  return {
    stamp: () => stamp,
    setStamp: (now) => {
      stamp = seen = now;
    },
    changed,
    stop: () => window.clearInterval(timer),
  };
}

/** The Workbench's intelligence for a blade's Python editor (Jedi with secret() known, signatures, hovers,
 *  the lint reported for workbench_problems, Copilot's ghost text where declared): an editor's options. */
export function bladeEditorIntel(options: { name: () => string; file: string; value: () => string; alive: () => boolean; reveal: (line: number, column: number) => void }): Partial<CodeEditorOptions> {
  const document = (): string => options.file || `blade:${options.name()}`;
  const intel = pythonIntel({ intel: () => ({ kernel: null, path: options.file || null, python: null }) }, { notebook: false, document, before: () => [SECRET_STUB] });
  const key = `${document()}\u0000${Math.random()}`;
  return {
    complete: (text, offset) => intel.complete(text, offset).then((found) => found ?? []),
    intel: {
      signature: intel.signature,
      hover: intel.hover,
      lint: intel.lint,
      onLint: (problems) => showProblems(key, options.alive() ? { document: document(), place: "", problems, reveal: options.reveal } : null),
    },
    inline: inlineSource(() => ({ key: `blade:${options.name()}`, name: `${options.name()}.py`, kind: "script", language: "python", text: options.value() })),
    sendToAgent: (what, ask) => sendToAgent({ kind: "code", title: `${options.name()}, ${what.startLine === what.endLine ? `line ${what.startLine}` : `lines ${what.startLine} to ${what.endLine}`}`, text: what.text }, ask),
  };
}

/** A blade's whole file as its editor's language: Python, a snippet's own, a secret blade's names as text. */
export function bladeLanguage(detail: BladeDetail): EditorLanguage {
  return detail.kind === "secret" ? "plaintext" : detail.kind === "snippet" ? (LANGUAGES[detail.language || "python"] ?? "plaintext") : "python";
}

// ===== the standalone blade screen: the pieces composed in one IDE (codeIde.ts) =====

/** Open the screen of a blade (`name`; null: New blade's templates). `onSaved` gets the name it was saved
 *  under; `onClosed` runs when the user leaves. `back` is the IDE's Back (the page's way out). The arguments
 *  after `name` are the old editor's and ignored. */
export async function editBlade(
  host: HTMLElement,
  name: string | null,
  _template: Template | null,
  _kind: BladeKind,
  onSaved: (name: string) => void,
  onClosed: () => void,
  back?: { label: string; run: () => void },
  /** A brand-new scaffold: Properties open, the cursor at `line` (its working body). */
  fresh?: { line: number },
): Promise<void> {
  if (name === null) {
    await showTemplatePicker(host, (made) => {
      onSaved(made);
      void editBlade(host, made, null, "other", onSaved, onClosed, back);
    });
    return;
  }
  clear(host, loadingBlock(`Opening ${name}…`));
  let detail: BladeDetail;
  try {
    detail = await api<BladeDetail>(path(name));
  } catch (error) {
    clear(host, h("div", { class: "code-ide-missing" }, errorNote(error))); // in place (9.5): its tab says it
    return;
  }
  void whenMode(); // the open project's mode: Copilot's ghost text where an extension declares it
  const readOnly = Boolean(detail.pack);
  const secretKind = detail.kind === "secret";
  let savedName = detail.name;
  const reopen = (): void => void editBlade(host, savedName, null, "other", onSaved, onClosed, back);
  const alive = (): boolean => ide.element.isConnected;
  const props = bladeProperties(detail, { readOnly, name: () => savedName, changed: () => ide.setExtraDirty(props.dirty()), reopen, code: () => ide.value() });
  const language = bladeLanguage(detail);
  const code = secretKind ? detail.env_names.join("\n") : detail.code;
  const closeNote = (): HTMLButtonElement => button("Close", () => ide.note(null), { class: "ghost ide-btn", icon: "close", iconOnly: true });

  async function save(text: string): Promise<boolean> {
    if (!(await props.check())) {
      ide.note(h("div", { class: "ide-note-row", role: "alert" }, errorNote(props.refusal()), closeNote()));
      return false;
    }
    const body: Record<string, unknown> = { ...props.header(), stamp: edits.stamp() };
    if (!secretKind) body.code = text;
    try {
      const saved = await api<BladeSummary & { stamp: string }>(path(savedName), "PUT", body);
      savedName = saved.name;
      edits.setStamp(saved.stamp);
      props.markSaved(saved.table ?? "");
      ide.setExtraDirty(false);
      ide.setName(saved.name);
      ide.note(null);
      toast(`Saved ${saved.name}.`);
      onSaved(saved.name);
      return true;
    } catch (error) {
      const said = error instanceof ApiError ? (error.said as { changed_on_disk?: boolean; stamp?: string; line?: number } | null) : null;
      if (error instanceof ApiError && error.status === 422 && typeof said?.line === "number") {
        // The code lacks its kind's part (or does not compile): refused, the line marked, the note in Result.
        const line = said.line;
        const words = (said as { error?: string }).error ?? "It cannot be saved as it is.";
        ide.setRunProblems([{ line, col: null, endLine: line, endCol: null, message: words, hover: words, severity: "error", fixes: [] }]);
        ide.showResult(errorNote(error));
        ide.showTab("result");
        void ide.ready.then((e) => e.reveal(line, 1));
        return false;
      }
      if (readOnly) {
        ide.note(h("div", { class: "ide-note-row", role: "alert" }, errorNote(error), button("Copy as your own", () => void copyStarter(ide.value() === code ? undefined : ide.value()), { class: "primary ide-btn", icon: "copy" }), closeNote()));
      } else if (said?.changed_on_disk) edits.changed(String(said.stamp ?? ""));
      else ide.note(h("div", { class: "ide-note-row", role: "alert" }, errorNote(error), closeNote()));
      return false;
    }
  }

  async function copyStarter(withCode?: string): Promise<void> {
    let made: string | null;
    if (withCode === undefined) made = await copyAsOwn(detail.name);
    else {
      try {
        made = (await api<{ name: string }>(`${path(detail.name)}/copy`, "POST", { code: withCode })).name;
      } catch (error) {
        errorHere(error);
        made = null;
      }
    }
    if (!made) return;
    onSaved(made);
    await editBlade(host, made, null, "other", onSaved, onClosed, back);
  }

  async function revert(): Promise<string | null> {
    const found = await api<{ code: string; stamp: string }>(`${path(savedName)}/code`).catch((error: unknown) => {
      errorHere(error);
      return null;
    });
    if (!found) return null;
    edits.setStamp(found.stamp);
    props.reset();
    ide.setExtraDirty(false);
    ide.note(null);
    return secretKind ? code : found.code;
  }

  async function remove(): Promise<void> {
    const target = savedName;
    const { body: dialogBody, foot, close } = openDialog(`Remove ${target}?`);
    dialogBody.append(h("p", {}, "Its file and its saved secrets go."));
    foot.append(
      button("Cancel", close, { class: "ghost" }),
      button("Remove", () => {
        close();
        void api(path(target), "DELETE").then(onClosed, (error: Error) => errorHere(error));
      }, { class: "danger" }),
    );
  }

  const runnable = detail.kind !== "snippet" && !secretKind;
  const ide: CodeIde = codeIde({
    name: detail.name,
    badge: readOnly ? h("span", { class: "chip ide-readonly" }, "read-only") : null,
    language,
    value: code,
    theme: effectiveTheme,
    back,
    save,
    saveAs: (text) => saveBladeAs(savedName, secretKind ? undefined : text, (made) => {
      onSaved(made);
      void editBlade(host, made, null, "other", onSaved, onClosed, back);
    }),
    revert,
    run: runnable
      ? (text, abort, output) => runBladeCode(savedName, text, abort, output, { showResult: ide.showResult, showTab: ide.showTab, setRunProblems: ide.setRunProblems, editor: ide.ready, again: () => void ide.run() })
      : undefined,
    runWords: `Running ${detail.name}…`,
    properties: props.element,
    propertiesOpen: fresh ? true : undefined,
    remember: "blade",
    menu: () => [
      ...(readOnly ? [{ label: "Copy as your own", icon: "copy", run: () => void copyStarter() }] : [{ label: "Show its file", icon: "folder", run: () => void showFile(savedName) }]),
      { label: "Export", icon: "export", run: () => void exportBlades(savedName) },
      ...(detail.removable ? [{ label: "Remove", icon: "trash", run: () => void remove() }] : []),
    ],
    editor: {
      readOnly: secretKind,
      readOnlyMessage: "A secret blade holds its variables' names, in its file.",
      ...(language === "python" ? bladeEditorIntel({ name: () => savedName, file: detail.file ?? "", value: () => ide.value(), alive, reveal: (line, column) => void ide.ready.then((e) => e.reveal(line, column)) }) : {}),
    },
  });
  const edits = watchOutsideEdits({ name: () => savedName, file: detail.file ?? "", stamp: detail.stamp ?? "", alive, dirty: () => ide.dirty(), load: (text) => ide.setValue(text, true), note: ide.note });
  clear(host, ide.element);
  const gone = window.setInterval(() => {
    if (alive()) return;
    window.clearInterval(gone);
    edits.stop();
    ide.dispose();
  }, 2000);
  // The editor takes the keyboard once it has loaded, unless the user is typing somewhere else by then.
  void ide.ready.then((e) => {
    const at = window.document.activeElement;
    if (fresh) e.reveal(fresh.line, 5);
    if (!at || at === window.document.body || at.closest(".ide-editor, dialog")) e.focus();
  });
  // Opened with packages missing: the prompt in the user's face.
  if (detail.inspect?.missing) void promptInstall(detail.inspect.missing, { then: reopen });
}

/** Save as…: a new name, checked as it is typed (GET /blades/name-check); `code` under it (none: its own).
 *  `made` gets the new blade's name. */
export function saveBladeAs(name: string, code: string | undefined, made: (name: string) => void): void {
  const { body, foot, close } = openDialog("Save as");
  const input = h("input", { type: "text", maxlength: "64", value: `${name} copy`, "aria-label": "New name", spellcheck: "false" }) as HTMLInputElement;
  const said = h("div", { class: "table-name-check", role: "status", "aria-live": "polite" });
  let free = false;
  let timer = 0;
  let mine = 0;
  const check = async (): Promise<void> => {
    const asking = ++mine;
    const answer = await api<{ available: boolean; said: string }>(`/blades/name-check?name=${encodeURIComponent(input.value)}`).catch(() => ({ available: false, said: "" }));
    if (asking !== mine) return;
    free = answer.available;
    said.textContent = answer.said;
    said.className = `table-name-check ${answer.available ? "ok" : "error"}`;
  };
  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => void check(), 200);
  });
  body.append(h("label", { class: "field" }, h("span", {}, "Name"), input), said);
  const go = async (): Promise<void> => {
    window.clearTimeout(timer);
    await check();
    if (!free) return input.focus();
    try {
      const copied = await api<{ name: string }>(`${path(name)}/copy`, "POST", { name: input.value.trim(), code });
      close();
      toast(`Saved as ${copied.name}.`);
      made(copied.name);
    } catch (error) {
      errorHere(error);
    }
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") void go();
  });
  foot.append(button("Cancel", close, { class: "ghost" }), button("Save", busyClick("Saving…", go), { class: "primary" }));
  void check();
  input.select();
}
