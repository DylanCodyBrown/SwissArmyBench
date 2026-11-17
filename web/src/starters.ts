/**
 * starters.ts: the built-in starter pack's blades and snippets in the page. [FUNCTION + VIEW]
 *
 *   [LIST]     the pack by family (GET /blades/starters), for the blade list (catalogRail.ts)
 *   [COPY]     Copy as your own: the starter copied into the user's blades, to change (POST .../copy)
 *   [DRAG]     a snippet carries SNIPPET_DRAG ({name, language}); a cell of its language takes it
 *              (workbenchNotebook.ts, workbenchScript.ts), any other refuses it with a short message
 *   [FORM]     a snippet's placeholders as a small form (GET .../snippet): a DAX one's from its cell's
 *              dataset (tables, columns, measures), the others' from the open tables; Insert sends the
 *              values and gets the filled text (POST .../snippet): the rules are the server's
 *              (domain/snippets.py)
 *   [PICK]     "Insert a snippet…" from a cell's menu: the snippets of its language to pick from
 */
import { api } from "./api";
import { button, clear, h, openDialog, toast } from "./dom";

/** The type a snippet's drag carries: {"name", "language"}. */
export const SNIPPET_DRAG = "application/x-sab-snippet";

export type SnippetLanguage = "dax" | "html" | "markdown" | "streamlit" | "python";
/** The cell kind each language goes into, and how it is said. */
export const SNIPPET_CELL: Record<SnippetLanguage, "dax" | "html" | "markdown" | "code"> = { dax: "dax", html: "html", markdown: "markdown", streamlit: "code", python: "code" };
const CELL_WORDS: Record<SnippetLanguage, string> = { dax: "a DAX cell", html: "an HTML cell", markdown: "a Markdown cell", streamlit: "a Python cell", python: "a Python cell" };

export interface Placeholder {
  name: string;
  label: string;
  kind: "table" | "column" | "measure" | "name" | "connection" | "number" | "text";
  default: string;
  follows: string;
}

export interface StarterSummary {
  name: string;
  kind: string;
  family: string;
  description: string;
  tags: string[];
  variable: string | null;
  language?: SnippetLanguage;
  cell_name?: string;
  placeholders?: Placeholder[];
  source: string;
  pack?: string | null;
}

interface SnippetFormData {
  name: string;
  language: SnippetLanguage;
  cell: string;
  cell_words: string;
  text: string;
  placeholders: Placeholder[];
  options: { tables: { name: string; columns: string[]; measures: string[] }[]; dataset?: string; connections?: string[] };
}

export interface FilledSnippet {
  name: string;
  language: SnippetLanguage;
  text: string;
  /** The name a Streamlit piece gives its cell. */
  cell_name: string | null;
}

const path = (name: string): string => `/blades/${encodeURIComponent(name)}`;

/** The starter pack, by family. */
export async function starters(): Promise<{ family: string; blades: StarterSummary[] }[]> {
  return (await api<{ families: { family: string; blades: StarterSummary[] }[] }>("/blades/starters")).families;
}

/** Copy a starter as the user's own; the copy's name. */
export async function copyAsOwn(name: string): Promise<string | null> {
  try {
    const copied = await api<{ name: string }>(`${path(name)}/copy`, "POST", {});
    toast(`Copied as ${copied.name}.`);
    return copied.name;
  } catch (error) {
    toast((error as Error).message, "error");
    return null;
  }
}

/** Whether a snippet of `language` goes into a cell of `kind`; the message when it does not. */
export function refusal(language: SnippetLanguage, kind: string): string | null {
  if (SNIPPET_CELL[language] === kind) return null;
  return `${{ dax: "A DAX snippet", html: "An HTML snippet", markdown: "A Markdown snippet", streamlit: "A Streamlit starter", python: "A Python snippet" }[language]} goes in ${CELL_WORDS[language]}.`;
}

/** What a drag carries, when it is a snippet. */
export function draggedSnippet(data: DataTransfer | null): { name: string; language: SnippetLanguage } | null {
  if (!data?.types.includes(SNIPPET_DRAG)) return null;
  try {
    const found = JSON.parse(data.getData(SNIPPET_DRAG)) as { name?: string; language?: SnippetLanguage };
    return found.name && found.language ? { name: found.name, language: found.language } : null;
  } catch {
    return null;
  }
}

/** A column's words as a Python name, as the server writes them (domain/snippets.py python_name). */
function pythonName(text: string): string {
  let word = text.trim().replace(/[^0-9a-zA-Z_]+/g, "_").replace(/^_+|_+$/g, "").toLowerCase() || "value";
  if (/^\d/.test(word)) word = `_${word}`;
  return word;
}

/** The column a placeholder of this name most likely wants, among `columns`. */
function likely(placeholder: Placeholder, columns: string[], taken: string[]): string {
  if (placeholder.default && columns.includes(placeholder.default)) return placeholder.default;
  const words = placeholder.name.toLowerCase();
  const hints: [RegExp, RegExp][] = [
    [/date table/, /date|calendar/i],
    [/date|day|month|year|period/, /date|day|time|month|year|period/i],
    [/latitude/, /^lat/i],
    [/longitude/, /^(lon|lng)/i],
    [/flag/, /^(is|has)_|shipped|active|open|done|flag/i],
    [/value|number|\by\b|total/, /amount|value|sales|total|price|revenue|qty|quantity|count/i],
    [/category|group|colour|\bx\b/, /region|category|type|group|product|segment|country|status/i],
    [/search/, /name|product|customer|description|title/i],
  ];
  for (const [wanted, found] of hints) {
    if (!wanted.test(words)) continue;
    const match = columns.find((c) => found.test(c) && !taken.includes(c)) ?? columns.find((c) => found.test(c));
    if (match) return match;
  }
  // No hint fits: the first column not taken that is not an identifier (a filter on order_id, a total of
  // customer_id mean nothing; the test bed's invoices start with three of them).
  const identifier = /(^|_)id$|[a-z]Id$|ID$/;
  return columns.find((c) => !taken.includes(c) && !identifier.test(c)) ?? columns.find((c) => !taken.includes(c)) ?? columns[0] ?? placeholder.default;
}

/** A snippet's form; Insert gives its filled text (null: closed without inserting). With no
 *  placeholders it is filled at once. `dataset`: a DAX cell's (`Finance/Sales model`). */
export async function fillSnippet(name: string, dataset: string | null = null): Promise<FilledSnippet | null> {
  let form: SnippetFormData;
  try {
    form = await api<SnippetFormData>(`${path(name)}/snippet${dataset ? `?dataset=${encodeURIComponent(dataset)}` : ""}`);
  } catch (error) {
    toast((error as Error).message, "error");
    return null;
  }
  const send = (values: Record<string, string>): Promise<FilledSnippet> => api<FilledSnippet>(`${path(name)}/snippet`, "POST", { values });
  if (!form.placeholders.length) {
    try {
      return await send({});
    } catch (error) {
      toast((error as Error).message, "error");
      return null;
    }
  }
  const tables = form.options.tables;
  const tableOf = (n: string): { name: string; columns: string[]; measures: string[] } | undefined => tables.find((t) => t.name === n);
  const inputs = new Map<string, HTMLInputElement>();
  const edited = new Set<string>();
  const lists = new Map<string, HTMLDataListElement>();
  const value = (n: string): string => inputs.get(n)?.value.trim() ?? "";
  /** A default made of others' values (by_{column}), as the server works it out. */
  const fromTemplate = (text: string): string => text.replace(/\{([a-z][a-z0-9_ ]{0,39})\}/g, (_, other: string) => pythonName(value(other) || other));
  const labelOf = (column: string): string => {
    const words = column.replace(/_/g, " ").trim();
    return words.charAt(0).toUpperCase() + words.slice(1);
  };

  // The choices each placeholder offers, and its value while the user has not typed one.
  const refill = (): void => {
    const taken: string[] = [];
    // The tables, columns and measures first: a name or a label follows what they hold.
    const picked = (p: Placeholder): boolean => p.kind === "table" || p.kind === "column" || p.kind === "measure";
    for (const p of [...form.placeholders.filter(picked), ...form.placeholders.filter((q) => !picked(q))]) {
      const input = inputs.get(p.name)!;
      const list = lists.get(p.name)!;
      let choices: string[] = [];
      if (p.kind === "table") choices = tables.map((t) => t.name);
      if (p.kind === "column") choices = (p.follows ? tableOf(value(p.follows))?.columns : undefined) ?? [...new Set(tables.flatMap((t) => t.columns))];
      if (p.kind === "measure") choices = [...new Set(tables.flatMap((t) => t.measures))];
      if (p.kind === "connection") choices = form.options.connections ?? [];
      clear(list, ...choices.map((c) => h("option", { value: c })));
      if (edited.has(p.name)) {
        if (p.kind === "column") taken.push(input.value);
        continue;
      }
      if (p.kind === "table") input.value = likely(p, choices, []);
      else if (p.kind === "column") input.value = likely(p, choices, taken);
      else if (p.kind === "measure" || p.kind === "connection") input.value = choices[0] ?? p.default;
      else if (p.default) input.value = /\{[a-z]/.test(p.default) ? fromTemplate(p.default) : p.default;
      else if (p.follows && p.kind === "name") input.value = pythonName(value(p.follows));
      else if (p.follows) input.value = labelOf(value(p.follows));
      if (p.kind === "column") taken.push(input.value);
    }
    // A measure picked: the table it is defined on is where a new measure goes, unless that was typed.
    const measure = form.placeholders.find((p) => p.kind === "measure");
    const home = form.placeholders.find((p) => p.name === "table");
    if (measure && home && !edited.has("table") && form.language === "dax") {
      const owner = tables.find((t) => t.measures.includes(value(measure.name)));
      if (owner) inputs.get("table")!.value = owner.name;
    }
  };

  const { body, foot, close } = openDialog(form.name);
  const error = h("p", { class: "status-error", role: "alert" });
  const fields = h("div", { class: "form-grid snippet-fields" });
  form.placeholders.forEach((p, i) => {
    const id = `snippet-choice-${i}`;
    const list = h("datalist", { id }) as HTMLDataListElement;
    const input = h("input", { type: p.kind === "number" ? "number" : "text", list: id, spellcheck: "false", "aria-label": p.label, "data-placeholder": p.name }) as HTMLInputElement;
    input.addEventListener("input", () => {
      edited.add(p.name);
      refill();
    });
    inputs.set(p.name, input);
    lists.set(p.name, list);
    fields.append(h("label", { class: "field" }, h("span", {}, p.label), input, list));
  });
  refill();
  body.append(fields, error);
  return await new Promise<FilledSnippet | null>((resolve) => {
    let done = false;
    const finish = (result: FilledSnippet | null): void => {
      if (done) return;
      done = true;
      close();
      resolve(result);
    };
    const insert = async (): Promise<void> => {
      error.textContent = "";
      const values = Object.fromEntries(form.placeholders.map((p) => [p.name, value(p.name)]));
      try {
        finish(await send(values));
      } catch (e) {
        error.textContent = `⚠ ${(e as Error).message}`;
      }
    };
    body.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.target as HTMLElement).tagName === "INPUT") {
        e.preventDefault();
        void insert();
      }
    });
    foot.append(button("Cancel", () => finish(null), { class: "ghost" }), button("Insert", () => void insert(), { class: "primary", icon: "plus" }));
    const dialog = body.closest("dialog");
    dialog?.addEventListener("close", () => finish(null));
    (fields.querySelector("input") as HTMLInputElement | null)?.focus();
  });
}

/** "Insert a snippet…": the snippets of a cell's language (the starters' and the user's own), to pick
 *  one. Its name, or null. */
export async function pickSnippet(language: SnippetLanguage): Promise<string | null> {
  let found: StarterSummary[];
  try {
    const [pack, mine] = await Promise.all([starters(), api<{ blades: StarterSummary[] }>("/blades")]);
    const fits = (b: StarterSummary): boolean => !!b.language && SNIPPET_CELL[b.language] === SNIPPET_CELL[language];
    found = [...mine.blades.filter((b) => b.kind === "snippet" && fits(b)), ...pack.flatMap((f) => f.blades.filter(fits))];
  } catch (error) {
    toast((error as Error).message, "error");
    return null;
  }
  const { body, foot, close } = openDialog(`Insert ${{ dax: "a DAX snippet", html: "an HTML snippet", markdown: "a Markdown snippet", streamlit: "a Streamlit starter", python: "a Python snippet" }[language]}`);
  return await new Promise<string | null>((resolve) => {
    let done = false;
    const finish = (name: string | null): void => {
      if (done) return;
      done = true;
      close();
      resolve(name);
    };
    const search = h("input", { type: "search", class: "cat-search", placeholder: "Search", "aria-label": "Search snippets", spellcheck: "false" }) as HTMLInputElement;
    const list = h("ul", { class: "snippet-list", role: "listbox", "aria-label": "Snippets" });
    const draw = (): void => {
      const text = search.value.trim().toLowerCase();
      const shown = found.filter((b) => !text || `${b.name} ${b.description} ${(b.tags ?? []).join(" ")}`.toLowerCase().includes(text));
      clear(
        list,
        ...shown.map((b) =>
          h("li", {}, h("button", { type: "button", class: "snippet-choice", role: "option", onclick: () => finish(b.name) }, h("span", { class: "snippet-choice-name" }, b.name), h("span", { class: "hint" }, b.description))),
        ),
      );
      if (!shown.length) list.append(h("li", { class: "empty" }, "No snippet matches"));
    };
    search.addEventListener("input", draw);
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        (list.querySelector("button") as HTMLButtonElement | null)?.click();
      }
    });
    draw();
    body.append(search, list);
    foot.append(button("Cancel", () => finish(null), { class: "ghost" }));
    body.closest("dialog")?.addEventListener("close", () => finish(null));
    search.focus();
  });
}
