/**
 * workbenchDocModes.ts: Notebook, Script and Data mode (the Workbench's modes, 2026-11-15). [WIRE]
 *
 *   [OUTLINE]    a notebook's Markdown headings and its named cells, each marked when it is edited or
 *                out of date (an amber dot: the run order, domain/notebook_flow.py); a click goes there
 *   [RUN SETTINGS] a script's arguments and the environment variables it needs (those it reads, by
 *                line; each connection's password), each with where it comes from: This computer, a
 *                Plain value, or a Key vault's secret. Never a value but a plain one's
 *   [RUN HISTORY] the script's runs (Run as scheduled and Run file): when, how, how long, the exit code;
 *                a run's variables by source and the end of its log; Run again
 *   [DICTIONARY] data.ipynb's tables: each column's plain type, its description (typed here, kept in
 *                data.ipynb and written into data.py) and where it comes from
 *   [LINEAGE]    its place while there is no cell to trace (the view is workbenchLineage.ts's, in place)
 *
 * ROUTING: POST /workbench/notebook/flow; /workbench/scripts/... (routes_script_runs.py);
 *          POST /projects/dictionary (routes_projects.py)
 */
import { api } from "./api";
import { askText, button, clear, h, icon, plural } from "./dom";
import { variableBox } from "./variableBox";
import { errorHere, errorNote } from "./errorNote";

// ===== Notebook mode: the run order and the Outline =====

export interface FlowState {
  number: number;
  state: string;
  because: string[];
}

export interface OutlineItem {
  kind: "heading" | "cell";
  level?: number;
  text: string;
  number: number | null;
}

export async function readFlow(cells: unknown[]): Promise<{ cells: FlowState[]; outline: OutlineItem[] }> {
  return api<{ cells: FlowState[]; outline: OutlineItem[] }>("/workbench/notebook/flow", "POST", { cells });
}

export function drawOutline(body: HTMLElement, outline: OutlineItem[], states: FlowState[], selected: number | null, tables: boolean, goTo: (number: number) => void, goToTables: () => void): void {
  const stale = new Set(states.filter((s) => s.state === "edited" || s.state === "outOfDate").map((s) => s.number));
  const level = Math.min(...outline.filter((o) => o.kind === "heading").map((o) => o.level ?? 1), 6);
  let depth = 0;
  const items = outline.map((o) => {
    if (o.kind === "heading") depth = (o.level ?? 1) - level;
    const indent = o.kind === "heading" ? depth : depth + 1;
    const mark = o.number !== null && stale.has(o.number);
    return h(
      "li",
      {},
      h(
        "button",
        {
          type: "button",
          class: `wb-outline-item ${o.kind}${o.number === selected ? " active" : ""}`,
          style: { paddingLeft: `${10 + indent * 14}px` },
          onclick: () => o.number !== null && goTo(o.number),
          dataset: { number: String(o.number ?? "") },
        },
        o.kind === "cell" ? icon("notebook") : null,
        h("span", { class: o.kind === "cell" ? "mono" : "" }, o.text),
        mark ? h("span", { class: "wb-outline-stale", title: "Edited or out of date", "aria-label": "Edited or out of date" }) : null,
      ),
    );
  });
  clear(
    body,
    h(
      "ul",
      { class: "wb-outline", "aria-label": "Outline" },
      tables ? h("li", {}, h("button", { type: "button", class: "wb-outline-item tables", onclick: goToTables }, icon("rows"), h("span", {}, "Tables"))) : null,
      ...items,
    ),
    outline.length || tables ? null : h("p", { class: "hint app-empty" }, "No headings or named cells"),
  );
}

// ===== Script mode: run settings, Run as scheduled, run history =====

export interface Variable {
  name: string;
  /** "line 23", the connection or blade that needs it, or "added". */
  why: string;
  /** Its name reads like a password's: no plain value is offered. */
  looks_secret: boolean;
  required?: boolean;
  from: "env" | "value" | "vault";
  value?: string;
  vault?: string;
  /** A vault's secret's name (never its value). */
  secret?: string;
  words: string;
}

export interface RunSettings {
  path: string;
  arguments: string;
  variables: Variable[];
}

const settingsUrl = (path: string): string => `/workbench/scripts/settings?path=${encodeURIComponent(path)}`;

export const runSettings = (path: string): Promise<RunSettings> => api<RunSettings>(settingsUrl(path));

/** What a variable row sends back (its source; a vault's names; a plain value). */
type Row = { name: string; from: string; value?: string; vault?: string; secret?: string };

export function drawRunSettings(body: HTMLElement, path: string | null, vaults: string[], saved: () => void): void {
  if (!path) return void clear(body, h("p", { class: "hint app-empty" }, "Save the script first"));
  void runSettings(path).then(
    (settings) => draw(settings),
    (e: Error) => clear(body, errorNote(e)),
  );
  const draw = (settings: RunSettings): void => {
    const rows: Row[] = settings.variables.map((v) => ({ name: v.name, from: v.from, value: v.value, vault: v.vault, secret: v.secret }));
    const send = (): void => {
      void api<RunSettings>("/workbench/scripts/settings", "PUT", { path, arguments: args.value, variables: rows.filter((r) => r.from !== "env" || settings.variables.some((v) => v.name === r.name && v.why === "added")) }).then(
        (next) => {
          draw(next);
          saved();
        },
        (e: Error) => errorHere(e),
      );
    };
    const args = h("input", { type: "text", class: "app-input mono wb-run-args", value: settings.arguments, placeholder: "--date 2026-11-14", "aria-label": "Arguments" }) as HTMLInputElement;
    args.addEventListener("change", send);
    args.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter" && args.getAttribute("aria-expanded") !== "true") args.blur(); // not a pick from the list
    });
    const variable = (v: RunSettings["variables"][number], row: Row): HTMLElement => {
      const choose = h(
        "select",
        { class: "wb-run-source", "aria-label": `${v.name}: where it comes from` },
        h("option", { value: "env", selected: row.from === "env" }, "This computer"),
        v.looks_secret ? null : h("option", { value: "value", selected: row.from === "value" }, "Plain value"),
        ...vaults.map((vault) => h("option", { value: `vault:${vault}`, selected: row.from === "vault" && row.vault === vault }, `Key vault · ${vault}`)),
      ) as HTMLSelectElement;
      const detail = row.from === "value"
        ? (h("input", { type: "text", class: "app-input", value: row.value ?? "", "aria-label": `${v.name}'s value` }) as HTMLInputElement)
        : row.from === "vault"
          ? (h("input", { type: "text", class: "app-input mono", value: row.secret ?? "", placeholder: "the secret's name", "aria-label": `${v.name}'s secret in ${row.vault ?? "the vault"}` }) as HTMLInputElement)
          : null;
      detail?.addEventListener("keydown", (e) => e.stopPropagation());
      detail?.addEventListener("change", () => {
        if (row.from === "value") row.value = detail.value;
        else row.secret = detail.value;
        if (row.from !== "vault" || row.secret) send();
      });
      choose.addEventListener("change", () => {
        if (choose.value.startsWith("vault:")) {
          row.from = "vault";
          row.vault = choose.value.slice(6);
          row.secret = row.secret ?? v.name.toLowerCase().replace(/_/g, "-");
        } else row.from = choose.value;
        send();
      });
      const icons: Record<string, string> = { env: "desktop", value: "edit", vault: "key" };
      return h(
        "div",
        { class: "wb-run-var", dataset: { variable: v.name } },
        h("div", { class: "wb-run-var-head" }, h("span", { class: "mono" }, v.name), h("span", { class: "hint" }, v.why === "added" ? "" : v.why)),
        h("div", { class: "wb-run-var-source" }, icon(icons[row.from] ?? "desktop"), choose),
        detail,
      );
    };
    const add = button("Variable", async () => {
      const name = await askText("The variable's name");
      if (!name) return;
      rows.push({ name: name.trim(), from: "env" });
      settings.variables.push({ name: name.trim(), why: "added", looks_secret: false, from: "env", words: "This computer" });
      send();
    }, { icon: "plus", class: "ghost wb-run-add" });
    clear(
      body,
      h("section", { class: "app-section" }, h("h3", { class: "app-heading" }, "Arguments"), variableBox(args, { label: "Arguments" })),
      h(
        "section",
        { class: "app-section" },
        h("div", { class: "app-heading-row" }, h("h3", { class: "app-heading" }, "Environment variables"), add),
        ...settings.variables.map((v, i) => variable(v, rows[i]!)),
      ),
    );
  };
}

// ===== Data mode: the dictionary and lineage =====

export type Descriptions = Record<string, { description: string; columns: Record<string, string> }>;

export interface DictionaryTable {
  table: string;
  rows: number;
  source: string;
  steps: number;
  description: string;
  columns: { name: string; type: string; description: string; comes_from: string }[];
}

export async function readDictionary(tables: { name: string; source: string }[], descriptions: Descriptions): Promise<DictionaryTable[]> {
  return (await api<{ tables: DictionaryTable[] }>("/projects/dictionary", "POST", { tables, descriptions })).tables;
}

/** Set one description (a table's, or a column's): a copy of the descriptions with it changed. */
export function described(all: Descriptions, table: string, column: string | null, text: string): Descriptions {
  const next: Descriptions = JSON.parse(JSON.stringify(all)) as Descriptions;
  const entry = (next[table] ??= { description: "", columns: {} });
  if (column === null) entry.description = text.trim();
  else if (text.trim()) entry.columns[column] = text.trim();
  else delete entry.columns[column];
  if (!entry.description && !Object.keys(entry.columns).length) delete next[table];
  return next;
}


export function drawDictionary(host: HTMLElement, tables: DictionaryTable[], chosen: { table: string | null }, change: (table: string, column: string | null, text: string) => void): void {
  if (!tables.length) return void clear(host, h("p", { class: "hint app-empty" }, "No tables in data.ipynb"));
  const table = tables.find((t) => t.table === chosen.table) ?? tables[0]!;
  chosen.table = table.table;
  const field = (value: string, label: string, column: string | null): HTMLInputElement => {
    const input = h("input", { type: "text", class: "dict-input", value, placeholder: "Add a description", "aria-label": label, maxlength: 500 }) as HTMLInputElement;
    input.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") input.blur();
    });
    input.addEventListener("change", () => change(table.table, column, input.value));
    return input;
  };
  clear(
    host,
    h(
      "nav",
      { class: "dict-tables", "aria-label": "Tables" },
      ...tables.map((t) =>
        h("button", { type: "button", class: `dict-table${t === table ? " active" : ""}`, onclick: () => ((chosen.table = t.table), drawDictionary(host, tables, chosen, change)) }, h("span", {}, t.table), h("span", { class: "hint" }, String(t.columns.length))),
      ),
    ),
    h(
      "section",
      { class: "dict-page", "aria-label": table.table },
      h("h2", {}, table.table),
      h("p", { class: "hint dict-meta" }, icon("file"), h("span", {}, [table.source, table.steps ? plural(table.steps, "step") : "", plural(table.rows, "row")].filter(Boolean).join(" · "))),
      field(table.description, `${table.table}'s description`, null),
      h(
        "table",
        { class: "dict-columns" },
        h("thead", {}, h("tr", {}, h("th", {}, "Column"), h("th", {}, "Type"), h("th", {}, "Description"), h("th", {}, "Comes from"))),
        h(
          "tbody",
          {},
          ...table.columns.map((c) =>
            h(
              "tr",
              { dataset: { column: c.name } },
              h("td", { class: "mono" }, c.name),
              h("td", {}, c.type),
              h("td", {}, field(c.description, `${c.name}'s description`, c.name)),
              h("td", { class: "dict-from" }, h("span", {}, icon(/^Step \d+$/.test(c.comes_from) ? "steps" : "file"), h("span", {}, c.comes_from))),
            ),
          ),
        ),
      ),
    ),
  );
}

/** Lineage's place in Data mode while data.ipynb has no cell to trace (the view itself is
 *  workbenchLineage.ts's, drawn in place: workbenchPage.ts dataLineage). */
export function drawLineageEmpty(host: HTMLElement): void {
  clear(host, h("div", { class: "dict-lineage-empty" }, icon("lineage"), h("p", { class: "hint" }, "Lineage")));
}
