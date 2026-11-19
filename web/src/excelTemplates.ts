/**
 * excelTemplates.ts: templates from existing workbooks and the statements and invoices built from them
 * (the Accounting extension's front-end plug-in, beside excelCanvas.ts). [EXCEL]
 *
 *   [TEMPLATES]  the project's templates (templates/<name>.xlsx); Import… an existing workbook (its
 *                layout, formats, merged cells and named ranges kept); one shown as its sheets, its named
 *                ranges marked, its bound places marked with what fills them
 *   [BIND]       a click on a cell names its place (its named range, else Sheet!B3); bind it to a value
 *                (a column of the group's row, text, the number, the date) or to a table that grows
 *                (the lines' columns, left to right); Unbind
 *   [BUILD]      Statements and invoices: a template, the groups' table and the lines' table (open tables),
 *                grouped by columns, named from them, numbered, dated, one workbook each or one of sheets.
 *                Dry run first (the files, their rows and totals: nothing written); then Build; then the
 *                register as a grid
 *
 * ROUTING: POST /accounting/templates, /templates/import, /templates/show, /templates/bind,
 *          /accounting/build, /accounting/register (the extension's routes.py)
 */
import { api } from "./api";
import { button, clear, h, openDialog, toast } from "./dom";
import { drawSheet, type Preview } from "./excelPreview";
import { chooseFile } from "./fileChooser";
import { errorHere } from "./errorNote";

interface Binding {
  kind: "value" | "table";
  place: string;
  value?: { column?: string; text?: string; number?: boolean; date?: boolean };
  format?: string;
  columns?: string[];
  rows?: number;
  grow?: boolean;
}

interface Template {
  name: string;
  folder: string;
  path: string;
  bindings: Binding[];
  preview: Preview;
  needs: { data: string[]; lines: string[] };
}

interface PlanEntry {
  file: string;
  sheet: string | null;
  group: Record<string, unknown>;
  rows: number;
  totals: Record<string, number>;
  number: string | number | null;
  date: string;
}

interface Built {
  dry_run: boolean;
  folder: string;
  files: PlanEntry[];
  count: number;
  totals: Record<string, number>;
}

const said = (b: Binding): string =>
  b.kind === "table" ? `lines: ${(b.columns ?? []).join(", ")}` : b.value?.column ? b.value.column : b.value?.number ? "number" : b.value?.date ? "date" : `"${b.value?.text ?? ""}"`;

/** The Templates dialog: the project's templates, one shown and its places bound. */
export async function openTemplates(name?: string): Promise<void> {
  const { dialog, body, foot, close } = openDialog("Templates", true);
  dialog.classList.add("xc-templates");
  const list = h("ul", { class: "xc-template-list", "aria-label": "Templates" });
  const shown = h("div", { class: "xc-template" });
  const form = h("div", { class: "xc-bind" });
  body.append(h("div", { class: "xc-template-body" }, h("div", { class: "xc-template-side" }, list, button("Import…", () => void importOne(), { icon: "import", class: "xc-import" })), h("div", { class: "xc-template-main" }, shown, form)));
  foot.append(button("Statements and invoices…", () => {
    close();
    void openStatements(current?.name);
  }, { icon: "copy", class: "xc-to-build" }), button("Close", () => close(), { class: "ghost" }));
  let current: Template | null = null;
  let sheetIndex = 0;

  async function listAll(): Promise<void> {
    const found = await api<{ folder: string; templates: string[] }>("/accounting/templates", "POST", {});
    clear(list, ...found.templates.map((t) => h("li", {}, button(t, () => void show(t), { class: `ghost xc-template-name ${current?.name === t ? "active" : ""}`, pressed: current?.name === t }))));
    if (!found.templates.length) list.append(h("li", { class: "hint" }, "None yet"));
  }

  async function importOne(): Promise<void> {
    const source = await chooseFile({ title: "Import a template: an existing workbook", mode: "file", suffixes: [".xlsx", ".xlsm"] });
    if (!source) return;
    try {
      const made = await api<Template>("/accounting/templates/import", "POST", { source });
      toast(`Imported ${made.name}`);
      await listAll();
      take(made);
    } catch (e) {
      errorHere(e);
    }
  }

  async function show(t: string): Promise<void> {
    try {
      take(await api<Template>("/accounting/templates/show", "POST", { name: t }));
      void listAll();
    } catch (e) {
      errorHere(e);
    }
  }

  function take(t: Template): void {
    current = t;
    sheetIndex = Math.min(sheetIndex, t.preview.sheets.length - 1);
    drawTemplate();
    drawForm(null, null);
  }

  function drawTemplate(): void {
    if (!current) return clear(shown, h("p", { class: "cv-empty" }, "Import an existing workbook: a statement, an invoice"));
    const t = current;
    const marks = new Map<string, string>();
    for (const b of t.bindings) {
      const place = (b.place.includes("!") ? b.place.split("!")[1] : b.place) ?? b.place;
      marks.set(place.toUpperCase(), said(b));
      marks.set(b.place, said(b));
    }
    const tabs = h("div", { class: "cv-tabs", role: "tablist", "aria-label": "Sheets" }, ...t.preview.sheets.map((s, i) => h("button", { type: "button", role: "tab", class: `tab-item cv-tab ${i === sheetIndex ? "active" : ""}`, "aria-selected": String(i === sheetIndex), onclick: () => { sheetIndex = i; drawTemplate(); } }, s.name)));
    const sheet = t.preview.sheets[sheetIndex];
    const named = Object.keys(t.preview.names);
    clear(
      shown,
      h("div", { class: "xc-template-head" }, h("h3", {}, t.name), named.length ? h("span", { class: "hint" }, `Named ranges: ${named.join(", ")}`) : null),
      tabs,
      sheet ? drawSheet(sheet, { names: t.preview.names, marks, pick: (cell, name) => drawForm(name ?? `${sheet.name}!${cell}`, cell) }) : null,
      h("ul", { class: "xc-bindings", "aria-label": "Bindings" }, ...t.bindings.map((b) => h("li", { dataset: { place: b.place } }, h("span", { class: "mono" }, b.place), h("span", {}, ` ← ${said(b)}`), button(`Unbind ${b.place}`, () => void bind({ unbind: b.place }), { icon: "close", iconOnly: true, class: "ghost" })))),
    );
  }

  async function bind(body: Record<string, unknown>): Promise<void> {
    if (!current) return;
    try {
      take(await api<Template>("/accounting/templates/bind", "POST", { name: current.name, ...body }));
    } catch (e) {
      errorHere(e);
    }
  }

  function drawForm(place: string | null, cell: string | null): void {
    if (!current || !place) return clear(form);
    const existing = current.bindings.find((b) => b.place.toLowerCase() === place.toLowerCase());
    const placeInput = h("input", { type: "text", value: place, class: "xc-bind-place mono", "aria-label": "Place" }) as HTMLInputElement;
    const kind = h("select", { class: "xc-bind-kind", "aria-label": "Bound to" }, ...[["value", "A value"], ["table", "A table of lines"]].map(([v, l]) => h("option", { value: v, selected: (existing?.kind ?? "value") === v }, l))) as HTMLSelectElement;
    const from = h("select", { class: "xc-bind-from", "aria-label": "From" }, ...[["column", "A column"], ["text", "Text"], ["number", "The number"], ["date", "The date"]].map(([v, l]) => h("option", { value: v }, l))) as HTMLSelectElement;
    from.value = existing?.value?.number ? "number" : existing?.value?.date ? "date" : existing?.value?.text !== undefined ? "text" : "column";
    const what = h("input", { type: "text", class: "xc-bind-what", "aria-label": "Column or text", value: existing?.value?.column ?? existing?.value?.text ?? (existing?.columns ?? []).join(", "), spellcheck: "false" }) as HTMLInputElement;
    const fmt = h("input", { type: "text", class: "xc-bind-format", "aria-label": "Format", placeholder: "keep", value: existing?.format ?? "" }) as HTMLInputElement;
    const rows = h("input", { type: "number", min: 1, class: "xc-bind-rows", "aria-label": "Rows in the template", value: String(existing?.rows ?? 1) }) as HTMLInputElement;
    for (const input of [placeInput, what, fmt, rows]) input.addEventListener("keydown", (e) => e.stopPropagation());
    const sync = (): void => {
      const table = kind.value === "table";
      from.hidden = table;
      rows.hidden = !table;
      fmt.hidden = table;
      what.hidden = !table && (from.value === "number" || from.value === "date");
      what.placeholder = table ? "the lines' columns, left to right" : from.value === "text" ? "Statement for {cedant}" : "a column";
    };
    kind.addEventListener("change", sync);
    from.addEventListener("change", sync);
    sync();
    const go = (): void => {
      const binding: Binding =
        kind.value === "table"
          ? { kind: "table", place: placeInput.value.trim(), columns: what.value.split(",").map((c) => c.trim()).filter(Boolean), rows: Number(rows.value) || 1, grow: true }
          : { kind: "value", place: placeInput.value.trim(), value: from.value === "number" ? { number: true } : from.value === "date" ? { date: true } : from.value === "text" ? { text: what.value } : { column: what.value.trim() }, ...(fmt.value.trim() ? { format: fmt.value.trim() } : {}) };
      void bind({ binding });
    };
    clear(form, h("h4", {}, cell ? `${place}` : place), placeInput, kind, from, what, fmt, rows, button("Bind", go, { icon: "link", class: "primary xc-bind-go" }));
    what.focus();
  }

  drawTemplate();
  await listAll();
  if (name) await show(name);
}

/** Statements and invoices: a template and two open tables, a dry run, then the build and its register. */
export async function openStatements(template?: string): Promise<void> {
  const { dialog, body, foot, close } = openDialog("Statements and invoices", true);
  dialog.classList.add("xc-statements");
  const [templates, open] = await Promise.all([
    api<{ templates: string[] }>("/accounting/templates", "POST", {}).catch(() => ({ templates: [] as string[] })),
    api<{ datasets: { name: string }[] }>("/datasets").catch(() => ({ datasets: [] as { name: string }[] })),
  ]);
  const tables = open.datasets.map((d) => d.name);
  const select = (cls: string, options: string[], value?: string, blank = false): HTMLSelectElement =>
    h("select", { class: cls }, ...(blank ? [h("option", { value: "" }, "—")] : []), ...options.map((o) => h("option", { value: o, selected: o === value }, o))) as HTMLSelectElement;
  const input = (cls: string, value = "", placeholder = ""): HTMLInputElement => {
    const el = h("input", { type: "text", class: cls, value, placeholder, spellcheck: "false" }) as HTMLInputElement;
    el.addEventListener("keydown", (e) => e.stopPropagation());
    return el;
  };
  const pick = select("xc-b-template", templates.templates, template ?? templates.templates[0]);
  const data = select("xc-b-data", tables, tables.find((t) => /statement|invoice|header|part/i.test(t)) ?? tables[0]);
  const lines = select("xc-b-lines", tables, tables.find((t) => /line|item|cession/i.test(t)), true);
  const groupBy = input("xc-b-group", "", "cedant, period");
  const name = input("xc-b-name", "", "{cedant} {period}.xlsx");
  const start = input("xc-b-start", "", "1001");
  const pattern = input("xc-b-pattern", "", "INV-{n:05d}");
  const date = h("input", { type: "date", class: "xc-b-date" }) as HTMLInputElement;
  const oneBook = h("input", { type: "checkbox", class: "xc-b-one" }) as HTMLInputElement;
  const plan = h("div", { class: "xc-plan" });
  const lab = (text: string, el: HTMLElement): HTMLElement => h("label", { class: "xc-field" }, h("span", {}, text), el);
  body.append(
    h(
      "div",
      { class: "xc-build-form" },
      lab("Template", pick),
      lab("One per row of", data),
      lab("Lines from", lines),
      lab("Grouped by", groupBy),
      lab("File name", name),
      lab("Numbered from", start),
      lab("Number as", pattern),
      lab("Dated", date),
      h("label", { class: "xc-check" }, oneBook, "One workbook, a sheet each"),
    ),
    plan,
  );
  const request = (): Record<string, unknown> => {
    const groups = groupBy.value.split(",").map((g) => g.trim()).filter(Boolean);
    return {
      template: pick.value,
      data: data.value,
      ...(lines.value ? { lines: lines.value } : {}),
      group_by: groups,
      ...(name.value.trim() ? { name: name.value.trim() } : {}),
      ...(start.value.trim() ? { number: { start: Number(start.value), pattern: pattern.value.trim() || "{n}" } } : {}),
      ...(date.value ? { date: date.value } : {}),
      one_workbook: oneBook.checked,
    };
  };
  let dry: string | null = null; // the request the last dry run was for
  const buildButton = button("Build", () => void build(false), { icon: "check", class: "primary xc-build" });
  buildButton.disabled = true;
  const registerButton = button("Register", () => void register(), { icon: "rows", class: "ghost xc-register", title: "What was built, as a grid" });
  const dryButton = button("Dry run", () => void build(true), { icon: "eye", class: "xc-dry-run" });
  for (const el of [pick, data, lines, groupBy, name, start, pattern, date, oneBook])
    el.addEventListener("input", () => {
      buildButton.disabled = JSON.stringify(request()) !== dry;
    });
  foot.append(registerButton, dryButton, buildButton, button("Close", () => close(), { class: "ghost" }));

  const money = (n: number): string => n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  function drawPlan(done: Built): void {
    const columns = [...new Set(done.files.flatMap((f) => Object.keys(f.totals)))].slice(0, 5);
    clear(
      plan,
      h("p", { class: "xc-plan-head" }, `${done.dry_run ? "Dry run" : "Built"}: ${done.count} ${done.files[0]?.sheet ? "sheets" : "files"} in ${done.folder}`),
      h(
        "table",
        { class: "xc-plan-table", "aria-label": done.dry_run ? "Dry run" : "Built" },
        h("thead", {}, h("tr", {}, h("th", {}, done.files[0]?.sheet ? "Sheet" : "File"), h("th", {}, "No."), h("th", { class: "num" }, "Rows"), ...columns.map((c) => h("th", { class: "num" }, c)))),
        h("tbody", {}, ...done.files.map((f) => h("tr", {}, h("td", {}, f.sheet ?? f.file), h("td", {}, f.number === null ? "" : String(f.number)), h("td", { class: "num" }, String(f.rows)), ...columns.map((c) => h("td", { class: "num" }, f.totals[c] === undefined ? "" : money(f.totals[c])))))),
        h("tfoot", {}, h("tr", {}, h("td", {}, "Total"), h("td", {}), h("td", { class: "num" }, String(done.files.reduce((n, f) => n + f.rows, 0))), ...columns.map((c) => h("td", { class: "num" }, money(done.totals[c] ?? 0))))),
      ),
    );
  }

  async function build(dryRun: boolean): Promise<void> {
    const asked = request();
    try {
      const done = await api<Built>("/accounting/build", "POST", { ...asked, dry_run: dryRun });
      drawPlan(done);
      dry = dryRun ? JSON.stringify(asked) : null;
      buildButton.disabled = !dryRun;
      const word = dryRun ? `Build ${done.count}` : "Build";
      buildButton.querySelector(".btn-label")!.textContent = word;
      buildButton.setAttribute("aria-label", word);
      if (!dryRun) toast(`Built ${done.count} in ${done.folder}`);
    } catch (e) {
      errorHere(e);
    }
  }

  async function register(): Promise<void> {
    try {
      await api("/accounting/register", "POST", { open: true });
      toast("The register is open as a grid");
    } catch (e) {
      errorHere(e);
    }
  }
}
