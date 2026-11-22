/**
 * endpointWizard.ts: New endpoint, the ONE wizard for a local sandbox API's endpoints (the owner, 2026-11-21: "one
 * uniform wizard for creating a sandbox api" / "Steps are different depending on the API"). It replaced New endpoint
 * from a table.
 *
 *   [TABLE]    a sandbox table (Reconcile asks for the second one among its own steps)
 *   [PATTERN]  every pattern ranked by the table's shape, each with one sentence why (the way Analyze ranks by its
 *              contracts); one that does not fit says what it needs and cannot be picked
 *   [STEPS]    THAT pattern's own steps, drawn from its data: a column, several columns, a choice, a word, the
 *              totals, the columns an action sets. Each starts on what the table's shape suggests
 *   [CODE]     the code as it will be added, kept current; the one thing still missing in its place
 *   [FOOT]     Cancel, Add to API.py (the file opens on the new block)
 *
 * No rule of its own: the tables, the ranking, the steps, their columns and defaults, the code and the problem all
 * come from POST /local-api/plan; Add is POST /local-api/scaffold (the agent's api(plan) and api(scaffold) are the
 * same two). `table` and `pattern`: where to start (the sandbox panel's row).
 */
import { api } from "./api";
import { button, h, openDialog, toast } from "./dom";
import { errorHere } from "./errorNote";
import { busyClick } from "./loading";
import { openOnPage } from "./workbenchPages";

type Field = string | string[] | Record<string, string>[] | null;
interface Step {
  id: string;
  label: string;
  kind: "column" | "columns" | "choice" | "text" | "table" | "totals" | "sets";
  help: string;
  required: boolean;
  choices: { value: string; label: string }[];
  options: string[];
  value: Field;
}
interface Ranked { pattern: string; label: string; question: string; fits: boolean; why: string }
interface Plan {
  tables: { name: string; rows: number | null; data: string }[];
  table?: string;
  ranked?: Ranked[];
  plan?: { pattern: string; label: string; steps: Step[]; fields: Record<string, Field>; widgets: { widget: string; words: string }[] };
  others?: string[];
  problem?: string | null;
  code?: string;
  imports?: string;
  added?: string[];
  words?: string;
}

const TOTALS: [string, string][] = [["count", "Count"], ["sum", "Sum"], ["avg", "Average"], ["min", "Smallest"], ["max", "Largest"], ["count_distinct", "Count of different values"]];

function select(label: string, options: [string, string][], value: string, onchange: (v: string) => void): HTMLSelectElement {
  const box = h("select", { "aria-label": label }, ...options.map(([v, w]) => h("option", { value: v, selected: v === value }, w))) as HTMLSelectElement;
  box.addEventListener("change", () => onchange(box.value));
  return box;
}

/** One step's control, writing its value into `fields` and saying when it changed. */
function control(step: Step, fields: Record<string, Field>, others: string[], other: { name: string }, changed: (redraw?: boolean) => void): HTMLElement {
  const columns = (none: boolean): [string, string][] => [...(none ? [["", "(none)"] as [string, string]] : []), ...step.options.map((c) => [c, c] as [string, string])];
  if (step.kind === "table") {
    return select(step.label, others.map((n) => [n, n]), other.name, (v) => {
      other.name = v;
      changed(true);
    });
  }
  if (step.kind === "column") return select(step.label, columns(!step.required), String(fields[step.id] ?? ""), (v) => { fields[step.id] = v; changed(); });
  if (step.kind === "choice") return select(step.label, step.choices.map((c) => [c.value, c.label]), String(fields[step.id] ?? ""), (v) => { fields[step.id] = v; changed(); });
  if (step.kind === "text") {
    const box = h("input", { type: "text", "aria-label": step.label, value: String(fields[step.id] ?? ""), spellcheck: "false", "data-no-variables": "" }) as HTMLInputElement;
    box.addEventListener("input", () => { fields[step.id] = box.value; changed(); });
    return box;
  }
  if (step.kind === "columns") {
    const picked = new Set((fields[step.id] as string[] | null) ?? []);
    return h("div", { class: "wizard-chips", role: "group", "aria-label": step.label },
      ...step.options.map((c) => {
        const tick = h("input", { type: "checkbox", checked: picked.has(c) }) as HTMLInputElement;
        tick.addEventListener("change", () => {
          if (tick.checked) picked.add(c);
          else picked.delete(c);
          fields[step.id] = step.options.filter((o) => picked.has(o));
          changed();
        });
        return h("label", { class: "wizard-chip" }, tick, h("span", {}, c));
      }),
      step.options.length ? null : h("span", { class: "muted" }, "No column fits."),
    );
  }
  // totals (a total and its column) and sets (a column and the value it is set to): rows that are added and removed
  const totals = step.kind === "totals";
  const rows = ((fields[step.id] as Record<string, string>[] | null) ?? []).map((r) => ({ ...r }));
  const host = h("div", { class: "wizard-rows", role: "group", "aria-label": step.label });
  const keep = (): void => {
    fields[step.id] = rows.map((r) => ({ ...r }));
    changed();
  };
  const draw = (): void => {
    host.replaceChildren(
      ...rows.map((row, at) => h("div", { class: "wizard-row" },
        totals
          ? select(`Total ${at + 1}`, TOTALS, row.fn ?? "count", (v) => { row.fn = v; keep(); })
          : select(`Column ${at + 1}`, columns(false), row.column ?? "", (v) => { row.column = v; keep(); }),
        totals
          ? select(`Column of total ${at + 1}`, columns(true), row.column ?? "", (v) => { row.column = v; keep(); })
          : (() => {
              const value = h("input", { type: "text", "aria-label": `Value ${at + 1}`, value: row.value ?? "", placeholder: "set to", "data-no-variables": "" }) as HTMLInputElement;
              value.addEventListener("input", () => { row.value = value.value; keep(); });
              return value;
            })(),
        button("Remove", () => { rows.splice(at, 1); keep(); draw(); }, { icon: "close", iconOnly: true, class: "ghost", title: "Remove" }),
      )),
      button(totals ? "Add a total" : "Add a column", () => {
        rows.push(totals ? { fn: "count", column: "" } : { column: step.options[0] ?? "", value: "" });
        keep();
        draw();
      }, { icon: "plus", class: "ghost" }),
    );
  };
  draw();
  return host;
}

/** New endpoint: the wizard. */
export async function newEndpoint(table?: string, pattern?: string): Promise<void> {
  const { body, foot, close } = openDialog("New endpoint", true);
  body.classList.add("endpoint-wizard");
  let got: Plan;
  try {
    got = await api<Plan>("/local-api/plan", "POST", {});
  } catch (e) {
    close();
    errorHere(e);
    return;
  }
  if (!got.tables.length) {
    body.append(h("p", { class: "empty-note" }, "The sandbox has no tables yet: Add to sandbox first."));
    foot.append(button("Close", () => close()));
    return;
  }
  const state = { table: got.tables.find((t) => t.name === table)?.name ?? got.tables[0]!.name, pattern: pattern ?? "", other: { name: "" } };
  let fields: Record<string, Field> = {};
  const ranking = h("div", { class: "wizard-patterns", role: "radiogroup", "aria-label": "Pattern" });
  const steps = h("div", { class: "wizard-steps" });
  const code = h("pre", { class: "wizard-code", "aria-label": "The code it adds", tabindex: "0" });
  const said = h("p", { class: "wizard-said", role: "status" });
  let add: HTMLButtonElement;
  let asked = 0;
  let timer = 0;

  /** The server's answer drawn: the ranking and the steps when the table or the pattern changed, the code always. */
  const read = async (redraw: boolean): Promise<void> => {
    const mine = ++asked;
    let plan: Plan;
    try {
      plan = await api<Plan>("/local-api/plan", "POST", {
        table: state.table,
        pattern: state.pattern || undefined,
        other: state.other.name || undefined,
        fields: redraw ? {} : fields,
      });
    } catch (e) {
      if (mine === asked) errorHere(e, {}, said);
      return;
    }
    if (mine !== asked) return;
    if (!state.pattern) {
      state.pattern = (plan.ranked ?? []).find((r) => r.fits)?.pattern ?? "table";
      return read(true);
    }
    if (redraw) {
      fields = { ...(plan.plan?.fields ?? {}) };
      state.other.name = String(plan.plan?.steps.find((s) => s.kind === "table")?.value ?? "");
      ranking.replaceChildren(...(plan.ranked ?? []).map((r) => {
        const radio = h("input", { type: "radio", name: "wizard-pattern", value: r.pattern, checked: r.pattern === state.pattern, disabled: !r.fits }) as HTMLInputElement;
        radio.addEventListener("change", () => {
          state.pattern = r.pattern;
          state.other.name = "";
          void read(true);
        });
        return h("label", { class: `wizard-pattern${r.fits ? "" : " unfit"}`, "data-pattern": r.pattern, title: r.question },
          radio, h("span", { class: "wizard-pattern-name" }, r.label), h("span", { class: "wizard-pattern-why" }, r.why));
      }));
      const pairs = plan.plan?.widgets ?? [];
      steps.replaceChildren(
        ...(plan.plan?.steps ?? []).map((s) => h("div", { class: "field wizard-step", "data-step": s.id },
          h("span", {}, s.label, s.required ? "" : " (optional)"),
          control(s, fields, plan.others ?? [], state.other, (again) => {
            window.clearTimeout(timer);
            timer = window.setTimeout(() => void read(again === true), again ? 0 : 250);
          }),
          s.help ? h("small", { class: "muted" }, s.help) : null,
        )),
        ...(pairs.length ? [h("p", { class: "muted wizard-pairs" }, `On the Canvas: ${pairs.map((w) => w.words).join(" ")}`)] : []),
      );
    }
    code.textContent = plan.problem ? "" : `${plan.imports ?? ""}${plan.imports ? "\n" : ""}${plan.code ?? ""}`;
    code.hidden = Boolean(plan.problem);
    const count = plan.added?.length ?? 0;
    said.textContent = plan.problem ?? `${count} endpoint${count === 1 ? "" : "s"} for API.py${plan.words ? ` (${plan.words})` : ""}.`;
    said.classList.toggle("bad", Boolean(plan.problem));
    add.disabled = Boolean(plan.problem);
  };

  const pick = select("Table", got.tables.map((t) => [t.name, t.rows == null ? t.name : `${t.name} (${t.rows.toLocaleString()} rows)`]), state.table, (v) => {
    state.table = v;
    state.pattern = "";
    state.other.name = "";
    void read(true);
  });
  add = button("Add to API.py", busyClick("Adding…", async (b) => {
    try {
      const done = await api<{ added: string[]; line: number; file: string; note?: string }>("/local-api/scaffold", "POST", {
        table: state.table,
        pattern: state.pattern,
        other: state.other.name || undefined,
        fields,
      });
      close();
      toast(`API.py has ${done.added.length} new endpoint${done.added.length === 1 ? "" : "s"} for ${state.table}.${done.note ? ` ${done.note}` : ""}`);
      if (done.file) void openOnPage(done.file, { line: done.line });
    } catch (e) {
      errorHere(e, {}, b);
    }
  }), { class: "primary" });
  body.append(
    h("label", { class: "field" }, h("span", {}, "Table (the sandbox's)"), pick),
    h("div", { class: "field" }, h("span", {}, "What the endpoint is for"), ranking),
    steps,
    h("div", { class: "field" }, h("span", {}, "The code it adds"), said, code),
  );
  foot.append(button("Cancel", () => close()), add);
  await read(true);
}
