/**
 * stepsPanel.ts: the Table Transformations window (applied steps) and its Code tab
 * (plan sections 7, 9, 10). [WIRE]
 * It shows only in a window of its own (?panel=steps, opened by the strip's View steps), and holds
 * only the steps: the step list, Add a SQL step and the Code tab. The grid's page has the ribbon.
 *
 * ROUTING: [ADD SQL STEP]    -> editStep("sql") (a SQL step's own form)
 *          [COPY AS SQL OR PYTHON]           -> showCode() (the Code tab: the verified query + Copy as SQL / Python)
 *          [STEP ROW]        click text -> state.setPreview(i + 1); click again -> full view
 *          [ON/OFF BOX]      -> toggle(i)        [DRAG GRIP] -> drop(from, to)
 *          [EDIT / DELETE]   -> editStep(kind, i) / remove(i)
 *          [ROW COUNTS]      -> read-only, from GET /grids/{id}/step-counts
 *          [STEP ERROR]      -> read-only, from state.info.step_error
 *          [CATEGORIZE INFO] -> read-only, from GET /grids/{id}/categorize-stats
 *          [CODE TAB]        -> renderCode(); the Copy buttons only when the code verified identical
 */
import { api, clientId, grid, query, type StepJson } from "./api";
import { button, clear, formatCount, h, toast } from "./dom";
import { KIND_LABELS, editStep } from "./stepForms";
import { state } from "./state";

let tab: "steps" | "code" = "steps";
let counts: number[] = [];
let dragFrom: number | null = null;
let host: HTMLElement;

export function mountStepsPanel(element: HTMLElement): void {
  host = element;
  // Switching tabs announces both: one render (and one step-counts request), not two.
  state.on("info", scheduleRender);
  state.on("preview", scheduleRender);
  document.body.classList.add("popout");
}

let renderQueued = false;

function scheduleRender(): void {
  if (renderQueued) return;
  renderQueued = true;
  queueMicrotask(() => {
    renderQueued = false;
    void render();
  });
}

/** A SQL step in a window of its own (?panel=sql, &step=N to edit one): resizable, the box filling it. */
function openSqlWindow(step?: number): void {
  const at = new URL(location.pathname, location.origin);
  at.searchParams.set("panel", "sql");
  if (step !== undefined) at.searchParams.set("step", String(step));
  const opened = window.open(`${at.pathname}${at.search}`, `sql-${location.pathname}`, "popup,width=960,height=680");
  if (opened) opened.focus();
  else toast("The browser blocked the SQL window: allow pop-ups for this address.", "error");
}

async function render(): Promise<void> {
  const info = state.info;
  if (!info || !host) return;
  const header = h("div", { class: "panel-header" }, h("h2", { id: "steps-title" }, "Transformations"));
  const body = h("div", { class: "panel-body" });
  clear(
    host,
    header,
    h(
      "div",
      { class: "panel-actions" },
      // A window of its own, as big as you like: room for a long SQL transformation (the owner, 2026-11-16).
      button("Add a SQL step", () => openSqlWindow(), { icon: "sql" }),
    ),
    h(
      "div",
      { class: "tabs", role: "tablist", "aria-labelledby": "steps-title" },
      h("button", { class: "tab", role: "tab", "aria-selected": String(tab === "steps"), onclick: () => { tab = "steps"; void render(); } }, "Steps"),
      h("button", { class: "tab", role: "tab", "aria-selected": String(tab === "code"), onclick: () => { tab = "code"; void render(); } }, "Code"),
    ),
    body,
  );
  if (tab === "code") {
    await renderCode(body);
    return;
  }
  try {
    counts = (await api<{ counts: number[] }>(`${grid}/step-counts${query({ gen: state.gen, client: clientId })}`)).counts;
  } catch {
    counts = [];
  }
  const list = h("ol", { class: "step-list", "aria-label": "Steps, in order" });
  list.append(
    h(
      "li",
      { class: "step source" },
      h("span", { class: "num", "aria-hidden": "true" }, "0"),
      h("span", { class: "text", onclick: () => state.setPreview(state.previewUpto === 0 ? null : 0) }, `Source: ${info.dataset} (${formatCount(info.row_count)} rows, version ${info.version})`),
    ),
  );
  info.steps.forEach((step, index) => {
    list.append(stepRow(step, index));
  });
  body.append(list);
  if (info.steps.length) body.append(countLine(info.steps.length, true));
  for (const [index, step] of info.steps.entries()) {
    if (step.kind === "categorize" && step.enabled !== false) void categorizeStats(index);
  }
}

function countLine(index: number, final = false): HTMLElement {
  const total = counts[index];
  return h("div", { class: "step-count" }, final && total !== undefined ? `${formatCount(total)} rows in the view` : "");
}

function stepRow(step: StepJson, index: number): HTMLElement {
  const info = state.info!;
  const broken = info.step_error?.index === index;
  const blocked = info.step_error !== null && index > info.step_error.index;
  const previewing = state.previewUpto === index + 1;
  const before = counts[index];
  const after = counts[index + 1];
  const row = h(
    "li",
    {
      class: `step ${step.enabled === false ? "off" : ""} ${broken ? "broken" : ""} ${previewing ? "previewing" : ""}`,
      draggable: "true",
      ondragstart: (e: DragEvent) => { dragFrom = index; e.dataTransfer?.setData("text/plain", String(index)); },
      ondragover: (e: DragEvent) => { e.preventDefault(); row.classList.add("drag-over"); },
      ondragleave: () => row.classList.remove("drag-over"),
      ondrop: (e: DragEvent) => { e.preventDefault(); row.classList.remove("drag-over"); if (dragFrom !== null) void move(dragFrom, index); },
    },
    h("span", { class: "num" }, String(index + 1)),
    h("input", {
      type: "checkbox",
      checked: step.enabled !== false,
      title: step.enabled === false ? "Turn this step on" : "Turn this step off",
      "aria-label": `Step ${index + 1} on`,
      onchange: () => void toggle(index),
    }),
    h(
      "span",
      {
        class: "text",
        role: "button",
        tabindex: "0",
        title: "Preview",
        onclick: () => state.setPreview(previewing ? null : index + 1),
        onkeydown: (e: KeyboardEvent) => { if (e.key === "Enter") state.setPreview(previewing ? null : index + 1); },
      },
      step.description ?? step.kind,
      step.params.header ? h("span", { class: "hint" }, " (header)") : null,
      step.params.from_chart ? h("span", { class: "hint" }, " (chart)") : null,
      previewing ? h("span", { class: "badge preview-tag" }, "previewing") : null,
    ),
    h(
      "span",
      { class: "actions" },
      step.kind in KIND_LABELS && step.kind !== "distinct" ? button(`Edit step ${index + 1}`, () => (step.kind === "sql" ? openSqlWindow(index) : editStep(step.kind, index)), { icon: "edit", iconOnly: true, class: "ghost" }) : null,
      button(`Delete step ${index + 1}`, () => void remove(index), { icon: "trash", iconOnly: true, class: "ghost" }),
    ),
    before !== undefined && after !== undefined && before !== after
      ? h("span", { class: "meta" }, `${formatCount(before)} → ${formatCount(after)} rows`)
      : null,
    h("span", { class: "meta", "data-categorize": String(index) }),
    broken ? h("span", { class: "error-text" }, info.step_error!.message) : null,
    blocked ? h("span", { class: "meta" }, "Not applied: earlier step broken") : null,
  );
  return row;
}

async function categorizeStats(index: number): Promise<void> {
  try {
    const stats = await api<{ unmatched: number; overlapping: number }>(`${grid}/categorize-stats${query({ step: index })}`);
    const slot = host.querySelector(`[data-categorize="${index}"]`);
    if (slot) {
      slot.textContent = `${formatCount(stats.unmatched)} rows matched no rule`;
      if (stats.overlapping) slot.append(h("span", { class: "warning-text" }, ` · ⚠ ${formatCount(stats.overlapping)} matched more than one (first wins)`));
    }
  } catch {
    // Shown only when it can be computed.
  }
}

async function toggle(index: number): Promise<void> {
  const steps = [...state.info!.steps];
  const step = steps[index]!;
  steps[index] = { ...step, enabled: step.enabled === false };
  await state.saveSteps(steps).catch((e: Error) => toast(e.message, "error"));
}

async function remove(index: number): Promise<void> {
  const steps = state.info!.steps.filter((_, i) => i !== index);
  await state.saveSteps(steps).catch((e: Error) => toast(e.message, "error"));
}

async function move(from: number, to: number): Promise<void> {
  if (from === to) return;
  const steps = [...state.info!.steps];
  const [moved] = steps.splice(from, 1);
  steps.splice(to, 0, moved!);
  dragFrom = null;
  await state.saveSteps(steps).catch((e: Error) => toast(e.message, "error"));
}

interface CodeResult {
  code: string;
  sql: string;
  reads: string;
  verified: boolean;
  difference: string | null;
  note: string | null;
  rows_checked: number;
}

/** What the user pastes into their own Python: one DuckDB query over their table by its variable
 * name ("Copy as SQL"), or `import duckdb` plus the one line that runs it ("Copy as Python"). */
async function renderCode(body: HTMLElement): Promise<void> {
  const status = h("span", { class: "hint" }, "Verifying…");
  const pre = h("pre", { class: "mono" });
  let result: CodeResult | null = null;
  const copyText = (text: string, what: string): void =>
    void navigator.clipboard.writeText(text).then(
      () => toast(`Copied the verified ${what}.`),
      () => toast("The browser blocked the clipboard.", "error"),
    );
  const copySql = button("Copy as SQL", () => result && copyText(result.sql.trim() + "\n", "SQL query"), {
    icon: "copy",
    class: "primary",
  });
  const copyPython = button("Copy as Python", () => result && copyText(result.code, "Python"), {
    icon: "copy",
  });
  copySql.hidden = copyPython.hidden = true;
  body.append(h("div", { class: "code-view" }, h("div", { class: "code-toolbar" }, copySql, copyPython, status), pre));
  try {
    result = await api<CodeResult>(`${grid}/code`);
    const shown = result;
    pre.textContent = shown.code;
    if (shown.verified) {
      // Checked and the same: the Copy buttons say so by being there. Only a difference is words.
      copySql.hidden = copyPython.hidden = false;
      clear(status);
    } else {
      clear(status, h("span", { class: "badge error" }, "Not verified"), " ", shown.difference ?? "");
    }
    body.append(h("p", { class: "hint" }, shown.reads));
    if (shown.note) body.append(h("p", { class: "hint" }, shown.note));
  } catch (e) {
    status.textContent = (e as Error).message;
    status.className = "status-error";
  }
}
