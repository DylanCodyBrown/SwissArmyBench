/**
 * analyzePage.ts: the Analyze page's toolbar and its one guided form (the owner, 2026-11-19: "The new analyze
 * pane's functions should be across the top with its own toolbar for every single analyze option we have" /
 * "make it stupid simple"; design principle 8.13). [WIRE]
 *
 * The toolbar: one button per analysis, grouped with small labels (Describe, Test, Model, Time, Compare,
 * Yours), each its everyday question with the technical name second. A button opens the form in a panel
 * beside the board (never a dialog over it). Everything it shows is the server's (GET /analyze, POST
 * /analyze/plan): which columns fit a slot, the picks, the options, the sentence, the fixes, the made-up
 * sample come from each analysis's contract through the one checker (domain/analyze.py), so this module
 * holds no rule of its own.
 *
 *   [TOOLBAR BUTTON]        -> openAnalysis(id): the form, the table already picked (the grid in front, else
 *                              the last used in Analyze), the columns picked by the app, shown as chips
 *   [WHAT CAN I DO…]        -> the table's columns; a column -> the analyses it fits, each one click
 *   [CHECK THIS TABLE]      -> runs the check (its note lands) and shows the three that suit the table, each
 *                              one click (its fixes applied in that click: "Read when as dates and run")
 *   [CHANGE]                -> another open table, or Find data… for a connection's
 *   [CHIP]                  -> another column that fits; the ones that do not fit are listed with why
 *   [APPLY] (Make it fit)   -> POST /analyze/fix: the fix as steps on the table, then the form again
 *   [RUN]                   -> POST /analyze/run (gated, Cancel): the cards land on the board by themselves
 *   [TRY IT ON THIS SAMPLE] -> the contract's made-up sample opened as a table, and run
 *   a card's actions (aiPanel.ts asks cardActions): Show the math, Open as grid, Copy code, the hand-offs
 *   to the next tool, Run again (the form reopens filled)
 */
import { api, gridId, saidOf, token, type Notice } from "./api";
import { button, clear, formatCount, h, icon, toast } from "./dom";
import { clearError, errorHere, showError, warningNote } from "./errorNote";
import { busy, busyClick, loadingBlock } from "./loading";
import { sentToast } from "./sandboxShow";

interface Listed {
  id: string;
  group: string;
  label: string;
  name: string;
  get: string;
  two_tables: boolean;
}

interface TableRef {
  grid: string;
  dataset: string;
  label: string;
  steps: number;
}

interface Toolbar {
  groups: string[];
  analyses: Listed[];
  tables: TableRef[];
  current: string | null;
}

interface Offered {
  name: string;
  type: string;
  preview: string[];
  cautions?: string[];
}

interface SlotPlan {
  key: string;
  label: string;
  words: string;
  optional: boolean;
  many: boolean;
  table: boolean;
  offered: Offered[];
  rejected: { name: string; type: string; why: string }[];
  value: string | string[] | null;
  said: string;
  cautions?: string[];
}

interface OptionPlan {
  key: string;
  label: string;
  meaning: string;
  value: unknown;
  default: unknown;
  choices: [string, string][];
  type: string;
}

export interface Fix {
  id: string;
  kind: string;
  level: "needed" | "better";
  slot: string;
  column: string;
  label: string;
  sentence: string;
  count: number | null;
}

interface Plan {
  analysis: string;
  label: string;
  name: string;
  get: string;
  rows: number;
  table: string;
  grid: string;
  dataset: string;
  table_label: string;
  one_row_per: string;
  slots: SlotPlan[];
  options: OptionPlan[];
  columns: Record<string, string | string[] | null>;
  settings: Record<string, unknown>;
  missing: string | null;
  ready: boolean;
  cautions: string[];
  gone: string[];
  fixes: Fix[];
  sentence: string | null;
  applied?: string[];
}

interface Sample {
  name: string;
  columns: string[];
  rows: Record<string, unknown>[];
  slots: Record<string, string[]>;
  other?: { name: string; columns: string[]; rows: Record<string, unknown>[] };
}

interface Contract {
  id: string;
  slots: { key: string; label: string; words: string }[];
  table: { one_row_per: string; two_tables: string | null };
  sample: Sample;
}

interface Ranked {
  analysis: string;
  label: string;
  name: string;
  get: string;
  status: "now" | "fixes" | "no";
  reason: string;
  button: string;
  fixes: Fix[];
}

interface Ran {
  run: string;
  analysis: string;
  table: string;
  dataset: string;
  columns: Record<string, unknown>;
  options: Record<string, unknown>;
  cards: string[];
  applied?: string[];
  result: Record<string, unknown>;
}

/** What a card of a run carries (services/charts.py land): enough to act on it and to run it again. */
export interface CardAnalysis {
  run: string;
  analysis: string;
  table: string;
  dataset: string;
  columns: Record<string, unknown>;
  options: Record<string, unknown>;
  label: string;
  name: string;
  actions: string[];
  next: { label: string; step?: Record<string, unknown>; analysis?: string; columns?: Record<string, unknown> }[];
  first: boolean;
}

type Mode =
  | { kind: "form"; analysis: string; table: string | null; columns?: Record<string, unknown>; options?: Record<string, unknown> }
  | { kind: "columns"; table: string | null; column?: string }
  | { kind: "check"; table: string | null };

const bar = h("div", { class: "analyze-toolbar", role: "toolbar", "aria-label": "Analyses" });
const side = h("aside", { class: "analyze-side", id: "analyze-side", "aria-label": "Analysis", hidden: true });
const errors = h("div", { class: "analyze-errors" });
let toolbar: Toolbar | null = null;
let mode: Mode | null = null;
let plan: Plan | null = null;
let waitingForTable = false; // Find data… was opened from the form: the next table that arrives is taken
let seq = 0; // only the newest plan is drawn (8.5)
const contracts = new Map<string, Contract>();

const ICON: Record<string, string> = {
  profile: "profile", check: "check", benford: "fit", fit: "fit", together: "link", outliers: "outliers", odds: "bucket",
  predictors: "lineage", regression: "chart", whatif: "sliders", time_series: "calendar", forecast: "forward",
  tie_out: "columns", key_finder: "key",
};

/** Your own analyses are blades: made and edited on the Scripts page's Blades (its own window). */
function openBladesPage(): void {
  window.open(`/scripts?pane=blades#token=${encodeURIComponent(token)}`, "sab-scripts")?.focus();
}

// ===== the toolbar =====

/** The toolbar's element (kept across the board's redraws) and its side panel. */
export function analyzeParts(): { toolbar: HTMLElement; side: HTMLElement } {
  void loadToolbar();
  return { toolbar: bar, side };
}

let loading: Promise<void> | null = null;

function loadToolbar(force = false): Promise<void> {
  if (loading && !force) return loading;
  loading = (async () => {
    try {
      toolbar = await api<Toolbar>(`/analyze?front=${encodeURIComponent(gridId)}`);
      drawToolbar();
    } catch (e) {
      loading = null;
      if (!bar.childElementCount) showError(bar, e);
    }
  })();
  return loading;
}

function analysisButton(a: Listed): HTMLElement {
  const btn = h(
    "button",
    {
      type: "button",
      class: "analyze-btn",
      "data-analysis": a.id,
      title: a.get,
      "aria-pressed": String(mode?.kind === "form" && mode.analysis === a.id),
      onclick: () => (a.id === "check" ? openCheck() : openAnalysis(a.id)),
    },
    icon(ICON[a.id] ?? "blade"),
    h("span", { class: "analyze-btn-words" }, h("span", { class: "analyze-btn-label" }, a.label), h("span", { class: "analyze-btn-name" }, a.name)),
  );
  return btn;
}

function drawToolbar(): void {
  if (!toolbar) return;
  const groups = toolbar.groups.map((group) => {
    const mine = toolbar!.analyses.filter((a) => a.group === group);
    const extra: HTMLElement[] = [];
    if (group === "Describe") {
      extra.push(
        h(
          "button",
          { type: "button", class: "analyze-btn", "data-analysis": "columns", "aria-pressed": String(mode?.kind === "columns"), onclick: () => openColumns() },
          icon("columns"),
          h("span", { class: "analyze-btn-words" }, h("span", { class: "analyze-btn-label" }, "What can I do with a column?"), h("span", { class: "analyze-btn-name" }, "by column")),
        ),
      );
    }
    if (group === "Yours") {
      extra.push(
        h(
          "button",
          { type: "button", class: "analyze-btn ghost", "data-analysis": "make", onclick: () => openBladesPage() },
          icon("plus"),
          h("span", { class: "analyze-btn-words" }, h("span", { class: "analyze-btn-label" }, mine.length ? "Make another…" : "Make your own…"), h("span", { class: "analyze-btn-name" }, "an analysis blade")),
        ),
      );
    }
    return h("div", { class: "analyze-group", role: "group", "aria-label": group }, h("span", { class: "analyze-group-label" }, group), h("div", { class: "analyze-group-buttons" }, ...extra.filter(() => group === "Describe"), ...mine.map(analysisButton), ...extra.filter(() => group !== "Describe")));
  });
  clear(bar, ...groups);
}

/** The analyses as [label, open], for the command palette (one list feeds every door, 8.3). */
export function analysisEntries(): [string, () => void][] {
  return (toolbar?.analyses ?? []).map((a) => [`${a.label} (${a.name})`, () => (a.id === "check" ? openCheck() : openAnalysis(a.id))]);
}

// ===== opening =====

let show: () => void = () => undefined;

/** How the page brings Analyze to the front (main.ts: showAgentView), for a form opened from elsewhere. */
export function onOpenAnalyze(handler: () => void): void {
  show = handler;
}

function defaultTable(): string | null {
  return (mode && mode.table) || gridId || toolbar?.current || null;
}

/** Open an analysis's form: the table and the columns already picked (given ones kept: Run again). */
export function openAnalysis(analysis: string, given: { table?: string | null; columns?: Record<string, unknown>; options?: Record<string, unknown> } = {}): void {
  show();
  mode = { kind: "form", analysis, table: given.table ?? defaultTable(), columns: given.columns, options: given.options };
  plan = null;
  open();
  void replan();
}

function openColumns(column?: string): void {
  show();
  mode = { kind: "columns", table: defaultTable(), column };
  open();
  void drawColumns();
}

function openCheck(): void {
  show();
  mode = { kind: "check", table: defaultTable() };
  open();
  void drawCheck();
}

function open(): void {
  side.hidden = false;
  clearError(errors);
  drawToolbar();
}

function close(): void {
  mode = null;
  plan = null;
  side.hidden = true;
  clear(side);
  drawToolbar();
}

function head(label: string, name: string): HTMLElement {
  return h(
    "div",
    { class: "analyze-side-head" },
    h("div", {}, h("h2", {}, label), h("span", { class: "analyze-side-name" }, name)),
    button("Close", close, { icon: "close", iconOnly: true, class: "ghost" }),
  );
}

// ===== the table line =====

function tableLine(label: string, rows: number | null, current: string | null): HTMLElement {
  const none = toolbar?.tables.length ? "Pick a table" : "No table is open";
  const words = label ? `${label}${rows === null ? "" : ` · ${formatCount(rows)} row${rows === 1 ? "" : "s"}`}` : none;
  return h(
    "div",
    { class: "analyze-table" },
    icon("table"),
    h("span", { class: "analyze-table-name", title: words }, words),
    button("Change", (event) => changeTable(event, current), { class: "ghost analyze-change" }),
  );
}

/** The table line when the form could not be read: the table by its name when it is still open (a step of
 * it is broken), else that one is to be picked; Change is there either way (never a dead end). */
function lostTable(grid: string | null): HTMLElement {
  const still = toolbar?.tables.find((t) => t.grid === grid) ?? null;
  return tableLine(still?.label ?? "", null, still?.grid ?? null);
}

function changeTable(event: MouseEvent, current: string | null): void {
  document.querySelector(".menu")?.remove();
  const anchor = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const pick = (grid: string): void => {
    menu.remove();
    setTable(grid);
  };
  const tables = toolbar?.tables ?? [];
  const menu = h(
    "div",
    { class: "menu analyze-tables", role: "menu", "aria-label": "Table" },
    ...tables.map((t) => h("button", { type: "button", role: "menuitemradio", "aria-checked": String(t.grid === current), onclick: () => pick(t.grid) }, icon("table"), t.label)),
    tables.length ? h("div", { class: "menu-rule", role: "separator" }) : null,
    h("button", { type: "button", role: "menuitem", onclick: () => { menu.remove(); findData(); } }, icon("data"), "Find data…"),
  );
  document.body.append(menu);
  menu.style.top = `${anchor.bottom + 4}px`;
  menu.style.left = `${Math.max(8, Math.min(anchor.left, window.innerWidth - menu.offsetWidth - 8))}px`;
  (menu.querySelector("button") as HTMLButtonElement | null)?.focus();
  setTimeout(() =>
    document.addEventListener("click", function away(e) {
      if (!menu.contains(e.target as Node)) {
        menu.remove();
        document.removeEventListener("click", away);
      }
    }),
  );
  menu.addEventListener("keydown", (e) => { if (e.key === "Escape") menu.remove(); });
}

let findDataOpener: () => void = () => undefined;

/** How Find data… opens (gridCommands.ts): the Data Explorer, where a connection's table is opened. */
export function onFindData(opener: () => void): void {
  findDataOpener = opener;
}

function findData(): void {
  waitingForTable = true;
  findDataOpener();
}

function setTable(grid: string): void {
  if (!mode) return;
  mode = mode.kind === "form" ? { kind: "form", analysis: mode.analysis, table: grid } : { ...mode, table: grid, ...(mode.kind === "columns" ? { column: undefined } : {}) };
  redraw();
}

function redraw(): void {
  if (!mode) return;
  if (mode.kind === "form") void replan();
  else if (mode.kind === "columns") void drawColumns();
  else void drawCheck();
}

// ===== the form =====

async function contractOf(analysis: string): Promise<Contract | null> {
  const known = contracts.get(analysis);
  if (known) return known;
  try {
    const found = await api<Contract>(`/analyze/contracts/${encodeURIComponent(analysis)}`);
    contracts.set(analysis, found);
    return found;
  } catch {
    return null;
  }
}

/** Ask the server for the form as it stands (the picks, what is missing, the fixes) and draw it. */
async function replan(columns?: Record<string, unknown>, options?: Record<string, unknown>): Promise<void> {
  if (!mode || mode.kind !== "form") return;
  const mine = ++seq;
  const asked = mode;
  const body: Record<string, unknown> = { analysis: asked.analysis, table: asked.table, front: gridId };
  const cols = columns ?? asked.columns;
  const opts = options ?? asked.options;
  if (cols) body.columns = cols;
  if (opts) body.options = opts;
  if (!side.childElementCount) clear(side, head(labelOf(asked.analysis), nameOf(asked.analysis)), loadingBlock("Reading the table…"));
  try {
    const work = api<Plan>("/analyze/plan", "POST", body);
    const found = side.querySelector<HTMLElement>(".analyze-form") ? await busy(side.querySelector<HTMLElement>(".analyze-form")!, "Checking…", work, { errorIn: false }) : await work;
    if (mine !== seq) return;
    plan = found;
    mode = { kind: "form", analysis: found.analysis, table: found.grid, columns: found.columns, options: found.settings };
    await drawForm();
  } catch (e) {
    if (mine !== seq) return;
    plan = null;
    await loadToolbar(true);
    clear(side, head(labelOf(asked.analysis), nameOf(asked.analysis)), errors, lostTable(asked.table));
    // Never a dead end (8.13): what is wrong in one sentence, and Change (another table, or Find data…).
    showError(errors, e, { dismiss: false, agent: false });
  }
}

const labelOf = (id: string): string => toolbar?.analyses.find((a) => a.id === id)?.label ?? "Analysis";
const nameOf = (id: string): string => toolbar?.analyses.find((a) => a.id === id)?.name ?? "";

function offeredLabel(o: Offered): string {
  const preview = o.preview.length ? `: ${o.preview.join(", ")}` : "";
  return `${o.name} · ${o.type}${preview}`;
}

/** A slot as a chip: its label, the column picked (a list: only the columns that fit), and why the app
 * picked it. The columns that do not fit are in the same list, each with why, and cannot be chosen. */
function chip(slot: SlotPlan): HTMLElement {
  if (!plan) return h("span");
  const now = plan;
  const change = (value: unknown): void => void replan({ ...now.columns, [slot.key]: value }, now.settings);
  const rejected = slot.rejected.length
    ? h("optgroup", { label: "Does not fit" }, ...slot.rejected.map((r) => h("option", { value: "", disabled: true }, `${r.name}: ${whyOf(r)}`)))
    : null;
  const fits = (taken: string[] = []): HTMLElement[] =>
    slot.offered.filter((o) => !taken.includes(o.name)).map((o) => h("option", { value: o.name }, slot.table ? o.preview[0] ?? o.name : offeredLabel(o)));
  if (slot.many) {
    const values = (slot.value as string[] | null) ?? [];
    const add = h(
      "select",
      { class: "chip-add", "aria-label": `Add to ${slot.label}`, onchange: (e: Event) => change([...values, (e.target as HTMLSelectElement).value]) },
      h("option", { value: "" }, values.length ? "Add…" : slot.optional ? slot.said || "Add…" : "Pick…"),
      ...fits(values),
      rejected,
    );
    return h(
      "div",
      { class: "analyze-chip-row", "data-slot": slot.key },
      h("span", { class: "chip-label", title: slot.words }, slot.label),
      h(
        "span",
        { class: "chips" },
        ...values.map((name) =>
          h("span", { class: "chip", "data-column": name }, name, h("button", { type: "button", class: "chip-remove", "aria-label": `Remove ${name}`, title: `Remove ${name}`, onclick: () => change(values.length > 1 || slot.optional ? values.filter((v) => v !== name) : values) }, "×")),
        ),
        add,
      ),
      slot.said && values.length ? h("span", { class: "chip-said" }, slot.said) : null,
    );
  }
  const value = (slot.value as string | null) ?? "";
  const select = h(
    "select",
    { class: `chip-select${value ? "" : " empty"}`, "aria-label": slot.label, title: slot.words, onchange: (e: Event) => change((e.target as HTMLSelectElement).value) },
    slot.optional || !value ? h("option", { value: "" }, slot.optional ? "(none)" : "Pick…") : null,
    ...fits(),
    rejected,
  );
  select.value = value;
  return h(
    "div",
    { class: "analyze-chip-row", "data-slot": slot.key },
    h("span", { class: "chip-label", title: slot.words }, slot.label),
    h("span", { class: "chips" }, h("span", { class: `chip${value ? "" : " empty"}` }, select)),
    slot.said ? h("span", { class: "chip-said" }, slot.said) : null,
    ...(slot.cautions ?? []).map((c) => h("span", { class: "chip-caution" }, icon("warning"), withStop(c))),
  );
}

const whyOf = (r: { name: string; why: string }): string => (r.why.startsWith(`${r.name} `) ? r.why.slice(r.name.length + 1) : r.why);
const sentenceCase = (text: string): string => (text ? `${text[0]!.toUpperCase()}${text.slice(1)}${/[.!?]$/.test(text) ? "" : "."}` : text);
/** A reason as a sentence: its stop added, its first word left as it is (it is often a column's name). */
const withStop = (text: string): string => (text && !/[.!?]$/.test(text) ? `${text}.` : text);

function optionField(option: OptionPlan): HTMLElement {
  if (!plan) return h("span");
  const now = plan;
  const change = (value: unknown): void => void replan(now.columns, { ...now.settings, [option.key]: value });
  let control: HTMLElement;
  if (option.type === "choice" || option.choices.length) {
    const select = h("select", { "aria-label": option.label, onchange: (e: Event) => change((e.target as HTMLSelectElement).value) }, ...option.choices.map(([value, words]) => h("option", { value }, words)));
    select.value = String(option.value ?? "");
    control = select;
  } else {
    control = h("input", {
      type: option.type === "number" ? "number" : "text",
      "aria-label": option.label,
      value: option.value === null || option.value === undefined ? "" : String(option.value),
      onchange: (e: Event) => change((e.target as HTMLInputElement).value),
    });
  }
  return h("label", { class: "field analyze-option", "data-option": option.key }, h("span", {}, option.label), control, h("small", {}, option.meaning));
}

function fixRow(fix: Fix): HTMLElement {
  return h(
    "li",
    { class: "analyze-fix", "data-fix": fix.id },
    h("span", { class: "analyze-fix-words" }, fix.sentence),
    button("Apply", busyClick("Applying…", () => applyFix(fix)), { class: fix.level === "needed" ? "primary" : "" }),
  );
}

async function applyFix(fix: Fix): Promise<void> {
  if (!plan) return;
  try {
    const again = await api<Plan>("/analyze/fix", "POST", { analysis: plan.analysis, table: plan.grid, columns: plan.columns, options: plan.settings, fixes: [fix.id] });
    plan = again;
    if (mode?.kind === "form") mode = { kind: "form", analysis: again.analysis, table: again.grid, columns: again.columns, options: again.settings };
    await drawForm();
  } catch (e) {
    takePlan(e);
    showError(errors, e);
  }
}

/** A refusal that carries the form as it stands now (the table changed under it): drawn, then the error. */
function takePlan(e: unknown): boolean {
  const said = saidOf(e);
  const sent = said && typeof said.plan === "object" && said.plan ? (said.plan as Plan) : null;
  if (!sent || !mode || mode.kind !== "form") return false;
  plan = sent;
  mode = { kind: "form", analysis: sent.analysis, table: sent.grid, columns: sent.columns, options: sent.settings };
  void drawForm();
  return true;
}

function sampleTable(sample: { columns: string[]; rows: Record<string, unknown>[] }, slots: Record<string, string[]>, labels: Record<string, string>): HTMLElement {
  const slotOf = (column: string): string | null => Object.keys(slots).find((key) => slots[key]!.includes(column)) ?? null;
  return h(
    "div",
    { class: "analyze-sample-wrap" },
    h(
      "table",
      { class: "small analyze-sample" },
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          ...sample.columns.map((c) => {
            const slot = slotOf(c);
            return h("th", { scope: "col", class: slot ? "slot" : "" }, slot ? h("span", { class: "sample-slot" }, labels[slot] ?? slot) : null, c);
          }),
        ),
      ),
      h(
        "tbody",
        {},
        ...sample.rows.slice(0, 8).map((row) => h("tr", {}, ...sample.columns.map((c) => h("td", { class: `${slotOf(c) ? "slot" : ""}${typeof row[c] === "number" ? " num" : ""}` }, row[c] === null ? "" : String(row[c]))))),
      ),
    ),
    sample.rows.length > 8 ? h("small", {}, `${sample.rows.length} rows in all`) : null,
  );
}

async function drawForm(): Promise<void> {
  if (!plan || !mode || mode.kind !== "form") return;
  const now = plan;
  const contract = await contractOf(now.analysis);
  if (plan !== now) return;
  const needed = now.fixes.filter((f) => f.level === "needed");
  const better = now.fixes.filter((f) => f.level === "better");
  const runButton = button(now.ready ? "Run" : "Run", () => void run(), { class: "primary analyze-run", icon: "play" });
  runButton.disabled = !now.ready;
  const form = h(
    "div",
    { class: "analyze-form", "data-analysis": now.analysis },
    tableLine(now.table_label, now.rows, now.grid),
    ...now.slots.map(chip),
    now.gone.length ? warningNote({ what: `${now.gone.join(", ")} is not in ${now.dataset} any more: picked again.`, dismiss: false }) : null,
    now.missing ? warningNote({ what: now.missing, where: now.dataset, dismiss: false }) : null,
    needed.length ? h("div", { class: "analyze-fixes" }, h("strong", {}, "Make it fit:"), h("ul", {}, ...needed.map(fixRow))) : null,
    ...now.cautions.map((c) => h("p", { class: "chip-caution" }, icon("warning"), c)),
    now.sentence ? h("p", { class: "analyze-sentence" }, now.sentence) : null,
    h("div", { class: "analyze-run-row" }, runButton),
    better.length ? h("div", { class: "analyze-fixes better" }, h("strong", {}, "Suggestions:"), h("ul", {}, ...better.map(fixRow))) : null,
    now.options.length ? h("details", { class: "analyze-more" }, h("summary", {}, "More options"), ...now.options.map(optionField)) : null,
    contract
      ? h(
          "details",
          { class: "analyze-needs" },
          h("summary", {}, "What your data should look like"),
          h("p", { class: "analyze-one-row" }, sentenceCase(contract.table.one_row_per)),
          contract.slots.length ? h("ul", { class: "analyze-slots" }, ...contract.slots.map((s) => h("li", {}, h("strong", {}, s.label), `: ${s.words}`))) : null,
          sampleTable(contract.sample, contract.sample.slots, Object.fromEntries(contract.slots.map((s) => [s.key, s.label]))),
          contract.sample.other ? h("p", { class: "analyze-one-row" }, `And ${contract.sample.other.name}: ${contract.table.two_tables ?? ""}`) : null,
          contract.sample.other ? sampleTable(contract.sample.other, {}, {}) : null,
          button("Try it on this sample", () => void run(true), { icon: "play", class: "analyze-try" }),
        )
      : null,
  );
  const keepOpen = [...side.querySelectorAll<HTMLDetailsElement>("details[open]")].map((d) => d.className);
  clear(side, head(now.label, now.name), errors, form);
  for (const name of keepOpen) side.querySelector<HTMLDetailsElement>(`details.${name.split(" ")[0]}`)?.setAttribute("open", "");
  drawToolbar();
}

let runs = 0;

/** Run the form (or the contract's sample): gated with Cancel while it runs (8.12); its cards land on the
 * board by themselves (the board hears the server's notice and marks them); an error stays in the form. */
async function run(sample = false, extra: Record<string, unknown> = {}): Promise<Ran | null> {
  if (!mode || mode.kind !== "form") return null;
  const asked = mode;
  const form = side.querySelector<HTMLElement>(".analyze-form") ?? side;
  const token = `page-${Date.now().toString(36)}-${++runs}`;
  const abort = new AbortController();
  const body: Record<string, unknown> = sample
    ? { analysis: asked.analysis, sample: true, token }
    : { analysis: asked.analysis, table: plan?.grid ?? asked.table, columns: plan?.columns, options: plan?.settings, token, ...extra };
  clearError(errors);
  try {
    const ran = await busy(form, sample ? "Running on the sample…" : "Running…", (signal) => api<Ran>("/analyze/run", "POST", body, signal), {
      abort,
      onCancel: () => void api("/analyze/cancel", "POST", { token }).catch(() => undefined),
      errorIn: false,
    });
    await loadToolbar(true);
    if (sample || extra.apply_fixes) {
      // The sample is a table now, and the form is on it: the chips show what the sample's columns are for.
      mode = { kind: "form", analysis: ran.analysis, table: ran.table, columns: ran.columns, options: ran.options };
      await replan();
    }
    return ran;
  } catch (e) {
    if ((e as Error | null)?.name === "AbortError") return null;
    takePlan(e);
    showError(errors, e);
    return null;
  }
}

// ===== what can I do with a column? =====

interface ColumnsAnswer {
  grid: string;
  dataset: string;
  table_label: string;
  rows: number;
  columns: { name: string; type: string; preview: string[]; analyses: { analysis: string; label: string; name: string; get: string; columns: Record<string, unknown> }[] }[];
}

async function drawColumns(): Promise<void> {
  if (!mode || mode.kind !== "columns") return;
  const mine = ++seq;
  const asked = mode;
  const title = head("What can I do with a column?", "by column");
  if (!side.childElementCount) clear(side, title, loadingBlock("Reading the table…"));
  try {
    const found = await api<ColumnsAnswer>("/analyze/column", "POST", { table: asked.table, front: gridId });
    if (mine !== seq || mode !== asked) return;
    asked.table = found.grid;
    const picked = found.columns.find((c) => c.name === asked.column) ?? null;
    const list = h(
      "div",
      { class: "analyze-columns", role: "listbox", "aria-label": "Columns" },
      ...found.columns.map((c) =>
        h(
          "button",
          { type: "button", class: "analyze-column", role: "option", "aria-selected": String(c.name === asked.column), "data-column": c.name, disabled: !c.analyses.length, title: c.analyses.length ? "" : "Nothing analyses this column (an identifier, or all one value)", onclick: () => { asked.column = c.name; void drawColumns(); } },
          h("strong", {}, c.name),
          h("span", { class: "analyze-column-type" }, c.type),
          h("span", { class: "analyze-column-preview" }, c.preview.join(", ")),
        ),
      ),
    );
    const big = picked
      ? h(
          "div",
          { class: "analyze-big", "aria-label": `What fits ${picked.name}` },
          ...picked.analyses.map((a) => bigButton(a.label, a.name, a.get, "Run", () => oneClick(found.grid, a.analysis, a.columns))),
        )
      : null;
    clear(side, title, errors, h("div", { class: "analyze-form" }, tableLine(found.table_label, found.rows, found.grid), list, big));
  } catch (e) {
    if (mine !== seq) return;
    await loadToolbar(true);
    clear(side, title, errors, lostTable(asked.table));
    showError(errors, e, { dismiss: false, agent: false });
  }
}

function bigButton(label: string, name: string, reason: string, verb: string, run: () => Promise<unknown>): HTMLElement {
  return h(
    "button",
    { type: "button", class: "analyze-big-btn", title: reason, onclick: busyClick("Running…", run) },
    h("span", { class: "analyze-big-label" }, label),
    h("span", { class: "analyze-big-name" }, name),
    h("span", { class: "analyze-big-reason" }, reason),
    h("span", { class: "analyze-big-verb" }, icon("play"), verb),
  );
}

/** One click: run with the rest defaulted (its fixes applied first when the button said so). */
async function oneClick(table: string, analysis: string, columns: Record<string, unknown> | null, fixes = false): Promise<void> {
  clearError(errors);
  try {
    const body: Record<string, unknown> = { analysis, table };
    if (columns && Object.keys(columns).length) body.columns = columns;
    if (fixes) body.apply_fixes = true;
    await api<Ran>("/analyze/run", "POST", body);
    if (fixes) redraw(); // the table has steps now: what suits it is read again
  } catch (e) {
    showError(errors, e);
  }
}

// ===== check this table =====

interface CheckAnswer {
  grid: string;
  dataset: string;
  table_label: string;
  rows: number;
  notes: { level: string; text: string }[];
  ranked: Ranked[];
  top: Ranked[];
}

async function drawCheck(): Promise<void> {
  if (!mode || mode.kind !== "check") return;
  const mine = ++seq;
  const asked = mode;
  const title = head("Check this table", "data shape check");
  if (!side.childElementCount) clear(side, title, loadingBlock("Checking the table…"));
  try {
    const found = await api<CheckAnswer>("/analyze/check", "POST", { table: asked.table, front: gridId });
    if (mine !== seq || mode !== asked) return;
    asked.table = found.grid;
    const others = found.ranked.filter((r) => !found.top.includes(r) && !found.top.some((t) => t.analysis === r.analysis));
    const big = found.top.map((r) => bigButton(r.label, r.name, withStop(r.reason), r.button, () => oneClick(found.grid, r.analysis, null, r.status === "fixes")));
    const warnings = found.notes.filter((n) => n.level === "warn");
    clear(
      side,
      title,
      errors,
      h(
        "div",
        { class: "analyze-form" },
        tableLine(found.table_label, found.rows, found.grid),
        ...warnings.map((n) => h("p", { class: "chip-caution" }, icon("warning"), n.text)),
        found.top.length ? h("div", { class: "analyze-big", "aria-label": "What suits this table" }, ...big) : warningNote({ what: `Nothing suits ${found.dataset} as it is.`, dismiss: false }),
        h(
          "details",
          { class: "analyze-rest" },
          h("summary", {}, "Every analysis"),
          h(
            "ul",
            { class: "analyze-ranked" },
            ...others.map((r) =>
              h(
                "li",
                { "data-analysis": r.analysis, "data-status": r.status },
                r.status === "no" ? h("span", { class: "analyze-ranked-label" }, r.label) : h("button", { type: "button", class: "link", onclick: () => openAnalysis(r.analysis, { table: found.grid }) }, r.label),
                h("small", {}, withStop(r.reason)),
              ),
            ),
          ),
        ),
        button("Put this check on the board", busyClick("Checking…", () => oneClick(found.grid, "check", null)), { icon: "note" }),
      ),
    );
  } catch (e) {
    if (mine !== seq) return;
    await loadToolbar(true);
    clear(side, title, errors, lostTable(asked.table));
    showError(errors, e, { dismiss: false, agent: false });
  }
}

// ===== a card's actions =====

async function showMath(run: string): Promise<void> {
  const proof = await api<{ title: string; markdown: string }>(`/analyze/runs/${encodeURIComponent(run)}/math`);
  const made = await api("/cards", "POST", { kind: "note", title: proof.title, body: proof.markdown, size: { w: 8, h: 14 } });
  sentToast("On the Analyze board: the math, step by step.", made);
}

async function openAsGrid(run: string): Promise<void> {
  const opened = await api<{ dataset: string }>(`/analyze/runs/${encodeURIComponent(run)}/grid`, "POST", {});
  toast(`Opened as ${opened.dataset}.`);
}

async function copyCode(run: string): Promise<void> {
  const made = await api<{ code: string; imports: string[] }>(`/analyze/runs/${encodeURIComponent(run)}/code`);
  const text = made.imports.length ? [...made.imports, "", made.code].join("\n") : made.code;
  await navigator.clipboard.writeText(text);
  toast("Copied.");
}

async function handOff(a: CardAnalysis, next: CardAnalysis["next"][number]): Promise<void> {
  if (next.analysis) {
    openAnalysis(next.analysis, { table: a.table || a.dataset, columns: next.columns });
    return;
  }
  if (!next.step) return;
  const tables = (await api<Toolbar>("/analyze")).tables;
  const table = tables.find((t) => t.grid === a.table) ?? tables.find((t) => t.dataset === a.dataset);
  if (!table) throw new Error(`${a.dataset} is not open any more.`);
  await api(`/grids/${encodeURIComponent(table.grid)}/step-ops`, "POST", { op: "add", step: next.step });
  toast(`Added a step to ${table.dataset}.`);
}

/** The actions of a run's first card (aiPanel.ts puts them under it): Show the math, Open as grid, Copy
 * code, the hand-offs to the next tool (8.8), Run again (its form reopens filled). */
export function cardActions(a: CardAnalysis | undefined): HTMLElement | null {
  if (!a || !a.first) return null;
  const guarded = (work: () => Promise<void>) => busyClick("Working…", () => work().catch((e: unknown) => errorHere(e)));
  const out: HTMLElement[] = [];
  if (a.actions.includes("math")) out.push(button("Show the math", guarded(() => showMath(a.run)), { icon: "steps", class: "ghost" }));
  if (a.actions.includes("grid")) out.push(button("Open as grid", guarded(() => openAsGrid(a.run)), { icon: "rows", class: "ghost" }));
  if (a.actions.includes("code")) out.push(button("Copy code", guarded(() => copyCode(a.run)), { icon: "copy", class: "ghost", title: "This analysis as Python, for a notebook" }));
  for (const next of a.next ?? []) out.push(button(next.label, guarded(() => handOff(a, next)), { icon: "forward", class: "ghost" }));
  if (a.actions.includes("again")) out.push(button("Run again…", () => openAnalysis(a.analysis, { table: a.table || a.dataset, columns: a.columns, options: a.options }), { icon: "play", class: "ghost", title: "Its form, filled with what it ran with" }));
  return out.length ? h("div", { class: "card-analysis", "data-run": a.run }, ...out) : null;
}

// ===== live =====

/** The tables changing under the form: a table that arrives after Find data… is taken; a table closed,
 * renamed or given a step has its form read again (the checker reruns). */
export function handleAnalyzeNotice(notice: Notice): void {
  if (!["grid_shown", "grid_closed", "grid_updated", "dataset_closed", "dataset_renamed", "dataset_updated", "blades_changed"].includes(notice.type)) return;
  void loadToolbar(true).then(() => {
    if (!mode) return;
    if (notice.type === "grid_shown" && notice.grid && (waitingForTable || !mode.table)) {
      waitingForTable = false;
      setTable(notice.grid);
      show();
      return;
    }
    const mine = mode.table;
    const about = notice.grid === mine || (notice.dataset !== undefined && toolbar?.tables.find((t) => t.grid === mine)?.dataset === notice.dataset);
    const gone = mine !== null && !toolbar?.tables.some((t) => t.grid === mine);
    if (about || gone) {
      if (mode.kind === "form" && plan) void replan(plan.columns, plan.settings);
      else redraw();
    }
  });
}
