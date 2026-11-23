/**
 * structureDocMenus.ts: a structure tab's menus and its one small form, which need none of the tab's own
 * state: a node's right-click menu (Copy path, Copy as code, Add key…, Duplicate, Move up and down, Delete),
 * the Transform menu (Pick, Filter…, Sort…, Flatten, Open as grid) and the dialog that asks for a step's or a
 * key's fields. Each takes what it does as a small host. Pulled out of structureDoc.ts's mountStructureDoc
 * (the craft review of 2026-11-22, refactor 8). [VIEW]
 */
import { button, h, icon, openDialog, type MenuItem } from "./dom";
import { isRecords, kindOf, nodeAt, pathText, type Part, type Value } from "./structureTree";

/** What a node's menu does: the tab's own actions. */
export interface NodeActions {
  pythonBeside: boolean;
  copyPath: () => void;
  copyCode: () => void;
  addKey: (p: Part[]) => void;
  edit: (body: Record<string, unknown>) => void;
}

/** A node's right-click menu, on the file's value (`file`: Move up and down know its list's size). */
export function nodeMenuItems(p: Part[], v: Value, file: Value, act: NodeActions): MenuItem[] {
  const last = p[p.length - 1];
  const items: MenuItem[] = [["copy", "Copy path", () => act.copyPath()], ...(act.pythonBeside ? ([["code", "Copy as code", () => act.copyCode()]] as MenuItem[]) : []), "-"];
  if (kindOf(v) === "object") items.push(["plus", "Add key…", () => act.addKey(p)]);
  if (p.length) {
    items.push(["duplicate", "Duplicate", () => act.edit({ op: "duplicate", path: pathText(p) })]);
    if (typeof last === "number") {
      const parent = nodeAt(file, p.slice(0, -1));
      const size = Array.isArray(parent) ? parent.length : 0;
      if (last > 0) items.push(["up", "Move up", () => act.edit({ op: "move", path: pathText(p), to: last - 1 })]);
      if (last < size - 1) items.push(["down", "Move down", () => act.edit({ op: "move", path: pathText(p), to: last + 1 })]);
    }
    items.push(["trash", "Delete", () => act.edit({ op: "remove", path: pathText(p) })]);
  }
  return items;
}

/** What the Transform menu does. `grid`: Open as grid is offered (the tree shows the steps' result, or
 *  there are no steps). */
export interface TransformActions {
  grid: boolean;
  addStep: (step: Record<string, unknown>) => void;
  openGrid: (at: string) => void;
}

/** The Transform menu for the node at path `at`: steps that make a view of the file, or a grid. */
export function transformItems(node: Value, at: string, act: TransformActions): MenuItem[] {
  const fields = isRecords(node) ? [...new Set((node as Record<string, Value>[]).slice(0, 50).flatMap((r) => Object.keys(r)))] : [];
  const list = Array.isArray(node);
  const items: MenuItem[] = [];
  if (at !== "$") items.push(["zoom", "Pick: only this branch", () => act.addStep({ op: "pick", path: at })]);
  if (list) {
    items.push(
      ["filter", "Filter…", () => askFields(
        "Filter…",
        [
          { name: "field", label: "Field", value: fields[0] ?? "" },
          { name: "test", label: "Test", value: "=", options: ["=", "!=", ">", ">=", "<", "<=", "contains", "starts with", "exists", "missing"] },
          { name: "value", label: "Value" },
        ],
        (v) => act.addStep({ op: "filter", path: at, field: v.field, test: v.test, value: v.value }),
      )],
      ["sortup", "Sort…", () => askFields(
        "Sort…",
        [
          { name: "field", label: "Field", value: fields[0] ?? "" },
          { name: "order", label: "Order", value: "Smallest first", options: ["Smallest first", "Largest first"] },
        ],
        (v) => act.addStep({ op: "sort", path: at, field: v.field, descending: v.order === "Largest first" }),
      )],
    );
    if (isRecords(node)) items.push(["rows", "Flatten", () => act.addStep({ op: "flatten", path: at })]);
  }
  if (list && (node as Value[]).length && act.grid) items.push(["grids", "Open as grid", () => act.openGrid(at)]);
  if (!items.length) items.push(["info", "Pick a list or a branch to transform it", () => undefined]);
  return items;
}

export interface Field {
  name: string;
  label: string;
  value?: string;
  options?: string[];
}

/** A small dialog of fields (a box each, or a choice); its button is the title less its "…"; Enter goes. */
export function askFields(title: string, fields: Field[], run: (values: Record<string, string>) => void): void {
  const { body, foot, close } = openDialog(title);
  const inputs = new Map<string, HTMLInputElement | HTMLSelectElement>();
  for (const f of fields) {
    const input = f.options
      ? (h("select", { "aria-label": f.label }, ...f.options.map((o) => h("option", { value: o, selected: o === f.value }, o))) as HTMLSelectElement)
      : (h("input", { "aria-label": f.label, value: f.value ?? "", spellcheck: false }) as HTMLInputElement);
    inputs.set(f.name, input);
    body.append(h("label", { class: "structures-field" }, h("span", {}, f.label), input));
  }
  const go = (): void => {
    const values: Record<string, string> = {};
    for (const [k, v] of inputs) values[k] = v.value;
    close();
    run(values);
  };
  body.addEventListener("keydown", (e) => {
    if (e.key === "Enter") (e.preventDefault(), go());
  });
  foot.append(button("Cancel", () => close()), button(title.replace(/…$/, ""), go, { class: "primary" }));
  (body.querySelector("input, select") as HTMLElement | null)?.focus();
}

/** The steps bar's chips: each step's words and its ×, `remove` taking the step away by its place. */
export function stepChips(steps: { op: string; words: string }[], remove: (index: number) => void): HTMLElement[] {
  return [
    h("span", { class: "muted sd-steps-label" }, "Steps"),
    ...steps.map((s, i) => h("span", { class: "structures-step", role: "listitem", "data-op": s.op }, h("span", {}, s.words), h("button", { type: "button", class: "structures-step-x", "aria-label": `Remove step ${i + 1}`, title: "Remove", onclick: () => remove(i) }, icon("close")))),
  ];
}

/** A note over the editor: the warning mark, its words, its buttons (codeIde.ts's ide.note). */
export const noteRow = (cls: string, words: string, ...buttons: HTMLElement[]): HTMLElement => h("div", { class: `ide-note-row ${cls}`, role: "status" }, icon("warning"), h("span", {}, words), ...buttons);
