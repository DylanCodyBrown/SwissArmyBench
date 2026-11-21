/**
 * widgetFields.ts: one property's box by its mask (domain/widget_properties.py TYPES), shared by the Widgets
 * window's Properties pane (a default, written into the code) and the Canvas's (an instance's value).
 *
 *   switch    a checkbox switch                 number   a number box (its range and step)
 *   text      a text box                        colour   a colour picker beside its #rrggbb
 *   date, datetime, time  the browser's pickers  dropdown its choices
 *   table     one picker, grouped: the open tables, data.ipynb's, each connection's (`[Conn].table`, as DuckDB SQL
 *             names it; a connection not listed yet: its table typed) (empty: made-up sample data)
 *   column    the columns of the table its `of` property names
 *   variable  the variables (the Variables page's names)
 *   path      a text box                        json     a small JSON editor, checked as it is typed
 *   endpoint  one of the project's local sandbox API's endpoints ("GET /orders": API.py's)
 *
 * A change is handed to `onValue` with `said`: the caller checks it (the server's check-value) and says what is
 * wrong under the box, with the fix, before anything is kept.
 */
import { h, icon } from "./dom";

export interface Prop {
  name: string;
  type: string;
  mask: string;
  default: unknown;
  help: string;
  minimum: number | null;
  maximum: number | null;
  step: number | null;
  choices: string[];
  of: string | null;
  annotated: boolean;
  line: number;
  problem: string | null;
}

export interface FieldContext {
  tables: Record<string, string[] | null>;
  variables: string[];
  /** The groups of the table picker (GET /streamlit/widgets/context); without them, every table is one list. */
  open_tables?: string[];
  data_tables?: string[];
  /** Each connection's tables as SQL names them; null: its catalog is not listed yet (the table is typed). */
  connection_tables?: Record<string, string[] | null>;
  /** The project's local sandbox API's endpoints, "GET /orders/{region}" (API.py's). */
  endpoints?: string[];
}

/** The table picker: Sample, Open tables, data.ipynb, then a group per connection. */
function tablePicker(context: FieldContext, value: string, readOnly: boolean, send: (next: string) => void): HTMLElement {
  const box = h("select", { class: "wg-input wg-table-picker", disabled: readOnly });
  const known = new Set<string>([""]);
  const add = (parent: HTMLElement, v: string, label: string): void => {
    known.add(v);
    parent.append(h("option", { value: v, selected: v === value }, label));
  };
  add(box, "", "Sample data (made up)");
  const group = (label: string, values: string[]): void => {
    if (!values.length) return;
    const g = h("optgroup", { label });
    for (const v of values) add(g, v, v);
    box.append(g);
  };
  const grouped = context.open_tables !== undefined;
  if (grouped) {
    group("Open tables", context.open_tables ?? []);
    group("data.ipynb", context.data_tables ?? []);
  } else group("Tables", Object.keys(context.tables).sort());
  const TYPE = "sab-type:";
  for (const [connection, tables] of Object.entries(context.connection_tables ?? {}).sort(([a], [b]) => a.localeCompare(b))) {
    const g = h("optgroup", { label: connection, "data-connection": connection });
    for (const t of tables ?? []) add(g, t, t);
    g.append(h("option", { value: `${TYPE}${connection}` }, tables === null ? `Type a table of ${connection}…` : `Another table of ${connection}…`));
    box.append(g);
  }
  if (value && !known.has(value)) box.append(h("option", { value, selected: true }, value.startsWith("[") ? value : `${value} (not here)`));
  const typed = h("input", { type: "text", class: "wg-input wg-table-typed", hidden: true, spellcheck: "false", "aria-label": "The connection's table", "data-no-variables": "" }) as HTMLInputElement;
  box.addEventListener("change", () => {
    const picked = (box as HTMLSelectElement).value;
    if (picked.startsWith(TYPE)) {
      typed.hidden = false;
      typed.value = `[${picked.slice(TYPE.length)}].`;
      typed.focus();
      return;
    }
    typed.hidden = true;
    send(picked);
  });
  const done = (): void => {
    if (typed.value.trim() && !/\]\.$/.test(typed.value.trim())) send(typed.value.trim());
  };
  typed.addEventListener("change", done);
  typed.addEventListener("keydown", (e) => {
    if (e.key === "Enter") done();
  });
  return h("span", { class: "wg-table-field" }, box, typed);
}

type OnValue = (value: unknown, said: (text: string) => void) => Promise<void> | void;

const text = (value: unknown): string => (value === null || value === undefined ? "" : String(value));

function select(options: { value: string; label: string }[], value: string, disabled: boolean): HTMLSelectElement {
  const box = h("select", { class: "wg-input", disabled });
  for (const option of options) box.append(h("option", { value: option.value, selected: option.value === value }, option.label));
  if (value && !options.some((o) => o.value === value)) box.append(h("option", { value, selected: true }, `${value} (not here)`));
  return box;
}

/** The box for one property, its label, its help and the line that says what is wrong. */
export function propertyField(prop: Prop, values: Record<string, unknown>, context: FieldContext, readOnly: boolean, onValue: OnValue, options: { marked?: string | null; overridden?: boolean; onReset?: () => void } = {}): HTMLElement {
  const value = values[prop.name] ?? prop.default;
  const line = h("div", { class: "wg-field-line", "aria-live": "polite" });
  const said = (words: string): void => {
    line.textContent = words;
    line.hidden = !words;
  };
  said(options.marked ?? prop.problem ?? "");
  const send = (next: unknown): void => {
    void Promise.resolve(onValue(next, said)).catch((e: unknown) => said(e instanceof Error ? e.message : String(e)));
  };
  let box: HTMLElement;
  switch (prop.mask) {
    case "switch": {
      const input = h("input", { type: "checkbox", class: "wg-switch", role: "switch", checked: Boolean(value), disabled: readOnly });
      input.addEventListener("change", () => send(input.checked));
      box = input;
      break;
    }
    case "number": {
      const input = h("input", { type: "number", class: "wg-input", value: text(value), disabled: readOnly, min: prop.minimum ?? undefined, max: prop.maximum ?? undefined, step: prop.step ?? (prop.type === "int" ? 1 : "any") });
      input.addEventListener("change", () => {
        if (input.value.trim() === "" || Number.isNaN(Number(input.value))) return said(`${prop.name} is a number.`);
        send(prop.type === "int" && Number.isInteger(Number(input.value)) ? Math.trunc(Number(input.value)) : Number(input.value));
      });
      box = input;
      break;
    }
    case "colour": {
      const shown = /^#[0-9a-fA-F]{6}$/.test(text(value)) ? text(value) : "#000000";
      const picker = h("input", { type: "color", class: "wg-colour", value: shown, disabled: readOnly, "aria-label": `${prop.name}: pick` });
      const typed = h("input", { type: "text", class: "wg-input wg-colour-text", value: text(value), disabled: readOnly, spellcheck: "false", "aria-label": prop.name, "data-no-variables": "" });
      picker.addEventListener("change", () => {
        typed.value = picker.value;
        send(picker.value);
      });
      typed.addEventListener("change", () => send(typed.value.trim()));
      box = h("span", { class: "wg-colour-pair" }, picker, typed);
      break;
    }
    case "date":
    case "time": {
      const input = h("input", { type: prop.mask, class: "wg-input", value: text(value), disabled: readOnly });
      input.addEventListener("change", () => send(input.value));
      box = input;
      break;
    }
    case "datetime": {
      const input = h("input", { type: "datetime-local", class: "wg-input", value: text(value).replace(" ", "T"), disabled: readOnly });
      input.addEventListener("change", () => send(input.value.replace("T", " ")));
      box = input;
      break;
    }
    case "dropdown": {
      const box2 = select(prop.choices.map((c) => ({ value: c, label: c })), text(value), readOnly);
      box2.addEventListener("change", () => send(box2.value));
      box = box2;
      break;
    }
    case "table": {
      box = tablePicker(context, text(value), readOnly, (next) => send(next));
      break;
    }
    case "column": {
      const table = text(prop.of ? values[prop.of] : "");
      const columns = (table ? context.tables[table] : SAMPLE_COLUMNS) ?? [];
      if (table && !columns.length) {
        // Its table comes from another widget or a connection not listed yet: the column typed.
        const input = h("input", { type: "text", class: "wg-input", value: text(value), disabled: readOnly, spellcheck: "false", "data-no-variables": "" });
        input.addEventListener("change", () => send(input.value.trim()));
        box = input;
        break;
      }
      const box2 = select([{ value: "", label: "(none)" }, ...columns.map((c) => ({ value: c, label: c }))], text(value), readOnly);
      box2.addEventListener("change", () => send(box2.value));
      box = box2;
      break;
    }
    case "endpoint": {
      const listed = context.endpoints ?? [];
      const known = listed.includes(text(value)) || !text(value) ? listed : [text(value), ...listed];
      const box2 = select([{ value: "", label: listed.length ? "(pick an endpoint)" : "(API.py has no endpoints yet)" }, ...known.map((e) => ({ value: e, label: e }))], text(value), readOnly);
      box2.addEventListener("change", () => send(box2.value));
      box = box2;
      break;
    }
    case "variable": {
      const box2 = select(context.variables.map((v) => ({ value: v, label: v })), text(value), readOnly);
      box2.addEventListener("change", () => send(box2.value));
      box = box2;
      break;
    }
    case "json": {
      const area = h("textarea", { class: "wg-input wg-json", rows: 3, spellcheck: "false", disabled: readOnly, "data-no-variables": "" }, JSON.stringify(value));
      area.addEventListener("input", () => {
        try {
          JSON.parse(area.value);
          said("");
        } catch {
          said("Not JSON yet: [\"a\", \"b\"] or {\"name\": 1}.");
        }
      });
      area.addEventListener("change", () => {
        try {
          send(JSON.parse(area.value));
        } catch {
          /* said as it is typed */
        }
      });
      box = area;
      break;
    }
    default: {
      const input = h("input", { type: "text", class: "wg-input", value: text(value), disabled: readOnly, spellcheck: "false" });
      input.addEventListener("change", () => send(input.value));
      box = input;
    }
  }
  box.setAttribute("aria-label", prop.name);
  const reset = options.overridden && options.onReset ? h("button", { type: "button", class: "wg-reset", title: "Back to the widget's default", "aria-label": `${prop.name}: back to the default`, onclick: options.onReset }, icon("undo")) : null;
  return h(
    "div",
    { class: `wg-prop${options.marked ? " marked" : ""}`, "data-property": prop.name, "data-mask": prop.mask },
    h("div", { class: "wg-prop-head" }, h("span", { class: "wg-prop-name" }, prop.name), h("span", { class: "wg-prop-mask" }, prop.type), reset),
    prop.help ? h("div", { class: "wg-prop-help" }, prop.help) : null,
    box,
    line,
  );
}

/** The made-up sample's columns (sab_canvas.sample): a column property with no table picks among these. */
export const SAMPLE_COLUMNS = ["month", "region", "product", "revenue", "units", "margin", "lat", "lon"];
