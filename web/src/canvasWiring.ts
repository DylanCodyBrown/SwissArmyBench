/**
 * canvasWiring.ts: a widget instance's contract on the Canvas (the owner, 2026-11-21: "Make a way for input and
 * out from widgets to be defined and clear"): its Inputs, Outputs and Events in the Properties pane, the marks
 * on the board (a selected widget's sources and readers lit, a broken wire marked on both ends), and the Wiring
 * view's lines between widgets. Everything comes from the canvas's state (`wiring`, services/canvas.py): the
 * page never decides a rule; a wire is sent and refused in place with the server's reason.
 *
 *   Inputs    each In's source: not wired (its starting value; an automatic wire said), a table (the
 *             project's sandbox tables among them), another widget's Out of a fitting type on this page or
 *             another ("<page> · <widget>.<port>": an app-wide value), the viewer (app.viewer), a GET
 *             endpoint's answer, a variable, a value typed; a list[Table] In an ordered list of tables
 *   Outputs   each Out, its type, who reads it
 *   Events    each Event's actions in order: call an endpoint (the body: the payload, a part of it, or a field
 *             each; a typed payload's fields offered), set a page value, rerun
 *   Wiring    lines from the exact Out port to the In port (dots on each widget's edges: Ins left, Outs and
 *             Events right); a wire from another page a stub with that page's name; a broken one marked
 */
import { button, h } from "./dom";
import type { FieldContext } from "./widgetFields";

export interface Port {
  name: string;
  direction: "in" | "out" | "event";
  type: string;
  words: string;
  default: unknown;
  help: string;
  line: number;
  problem: string | null;
  /** A typed payload's or a Table[Row]'s fields, and the record's name. */
  fields?: { name: string; type: string }[];
  schema?: string;
}

export interface Wiring {
  sources: Record<string, Record<string, Wire>>;
  readers: Record<string, string[]>;
  wires: { from: string; to: string; auto: boolean; cross?: boolean; page?: string }[];
  broken: { instance: string; port: string; reason: string; source: string | null }[];
  outs: Record<string, { type: string; instance: string; widget: string; port: string; direction: string; page?: string }>;
  /** Each Out holding a table: its columns (declared, else as Play last ran it). */
  columns?: Record<string, string[]>;
  ports: Record<string, { page: string; widget: string; ins: Port[]; outs: Port[]; events: Port[] }>;
}

type Wire = Record<string, unknown>;
type Action = { do: "call" | "set" | "rerun"; endpoint?: string; body?: string | Record<string, string>; params?: Record<string, string>; key?: string; value?: string };

export interface WiringContext extends FieldContext {
  endpoint_fields?: Record<string, string[]>;
  /** The canvas's pages' names by id (a wire from another page is said by its page's name). */
  page_names?: Record<string, string>;
}

export const VIEWER = "app.viewer";

export type SendWire = (port: string, wire: Wire | null) => Promise<void>;

/** Whether an Out (or a source) of type `given` can feed an In of type `wanted` (widget_contract.fits). */
export function fits(given: string, wanted: string): boolean {
  if (given === wanted) return true;
  if (wanted === "float" && given === "int") return true;
  if (wanted === "Table" && (given === "list[dict]" || given === "list")) return true;
  if (wanted === "list" && given.startsWith("list")) return true;
  if (wanted.startsWith("list[") && given === "list") return true;
  return wanted === "list[float]" && given === "list[int]";
}

/** An Out in words: "w3 sales_filter · region"; one from another page "Reports · w3 sales_filter.region"; the
 *  app's own "The viewer". */
export const outWords = (ref: string, wiring: Wiring, page = "", names: Record<string, string> = {}): string => {
  if (ref === VIEWER) return "The viewer (who is viewing)";
  const out = wiring.outs[ref];
  if (!out) return ref;
  if (out.page && out.page !== page) return `${names[out.page] ?? out.page} · ${out.instance} ${out.widget}.${out.port}`;
  return `${out.instance} ${out.widget} · ${out.port}`;
};

function line(): { element: HTMLElement; said: (text: string) => void } {
  const element = h("div", { class: "wg-field-line", "aria-live": "polite", hidden: true });
  return {
    element,
    said: (text: string) => {
      element.textContent = text;
      element.hidden = !text;
    },
  };
}

async function sending(said: (text: string) => void, work: () => Promise<void>): Promise<void> {
  try {
    said("");
    await work();
  } catch (e) {
    said(e instanceof Error ? e.message : String(e));
  }
}

function tableOptions(context: WiringContext, value: string): HTMLOptGroupElement[] {
  const groups: HTMLOptGroupElement[] = [];
  const group = (label: string, names: string[]): void => {
    if (!names.length) return;
    groups.push(h("optgroup", { label }, ...names.map((n) => h("option", { value: `table:${n}`, selected: value === `table:${n}` }, n))));
  };
  group("Open tables", context.open_tables ?? Object.keys(context.tables).sort());
  group("data.ipynb", context.data_tables ?? []);
  // The project's sandbox first (made-up copies a local sandbox API reads and writes: never live data).
  for (const [connection, tables] of Object.entries(context.connection_tables ?? {}).sort(([a], [b]) => (a === "Sandbox" ? -1 : b === "Sandbox" ? 1 : a.localeCompare(b)))) group(connection, tables ?? []);
  return groups;
}

/** The Outs an In can read, grouped: this page's ("Page values"), each other page's (by its name: an app-wide
 *  value), and the app's own (the viewer). */
function outOptions(port: Port, id: string, page: string, wiring: Wiring, value: string, tablesOnly = false, names: Record<string, string> = {}): HTMLOptGroupElement[] {
  const wanted = tablesOnly ? "Table" : port.type;
  const refs = Object.entries(wiring.outs).filter(([, o]) => o.instance !== id && fits(o.type, wanted));
  const groups: HTMLOptGroupElement[] = [];
  const option = ([ref, o]: [string, Wiring["outs"][string]]): HTMLOptionElement =>
    h("option", { value: `out:${ref}`, selected: value === `out:${ref}` }, ref === VIEWER ? "viewer: who is viewing" : `${o.instance} ${o.widget} · ${o.port} (${o.direction === "event" ? "its last payload" : o.type})`);
  const pageOf = (o: Wiring["outs"][string]): string => o.page ?? wiring.ports[o.instance]?.page ?? "";
  const here = refs.filter(([ref, o]) => ref !== VIEWER && pageOf(o) === page);
  if (here.length) groups.push(h("optgroup", { label: "Page values" }, ...here.map(option)));
  const others = [...new Set(refs.filter(([ref, o]) => ref !== VIEWER && pageOf(o) !== page).map(([, o]) => pageOf(o)))];
  for (const other of others) groups.push(h("optgroup", { label: `${names[other] ?? other} (another page)`, "data-page": other }, ...refs.filter(([ref, o]) => ref !== VIEWER && pageOf(o) === other).map(option)));
  const app = refs.filter(([ref]) => ref === VIEWER);
  if (app.length) groups.push(h("optgroup", { label: "The app" }, ...app.map(option)));
  return groups;
}

const keyOf = (wire: Wire | undefined): string => {
  if (!wire) return "";
  const [kind, value] = Object.entries(wire)[0] ?? ["", ""];
  return kind === "value" || kind === "page" || kind === "tables" ? kind : `${kind}:${String(value)}`;
};

function wireOf(picked: string): Wire | null {
  if (!picked) return null;
  const at = picked.indexOf(":");
  return at < 0 ? null : { [picked.slice(0, at)]: picked.slice(at + 1) };
}

/** One In's source picker (a list[Table] In: its tables in order). */
function inputField(port: Port, id: string, page: string, given: Wire | undefined, wiring: Wiring, context: WiringContext, editable: boolean, send: SendWire): HTMLElement {
  const { element: note, said } = line();
  const broken = wiring.broken.find((b) => b.instance === id && b.port === port.name);
  if (broken) said(`${broken.reason} It takes its starting value until it is wired again.`);
  const auto = !given ? wiring.wires.find((w) => w.auto && w.to === `${id}.${port.name}`) : undefined;
  const head = h("div", { class: "wg-prop-head" }, h("span", { class: "wg-prop-name" }, port.name), h("span", { class: "wg-prop-mask" }, `In · ${port.words}`));
  const body: HTMLElement[] = [];
  if (port.type.startsWith("list[Table")) {
    const items = Array.isArray(given?.tables) ? (given!.tables as Wire[]) : [];
    const put = (next: Wire[]): void => void sending(said, () => send(port.name, next.length ? { tables: next } : null));
    items.forEach((item, at) => {
      const box = h("select", { class: "wg-input", disabled: !editable, "aria-label": `${port.name}: table ${at + 1}` }, ...tableOptions(context, keyOf(item)));
      box.append(...outOptions(port, id, page, wiring, keyOf(item), true, context.page_names));
      box.addEventListener("change", () => {
        const next = [...items];
        next[at] = wireOf(box.value) ?? item;
        put(next);
      });
      const move = (by: number): void => {
        const next = [...items];
        const [one] = next.splice(at, 1);
        next.splice(Math.max(0, Math.min(next.length, at + by)), 0, one!);
        put(next);
      };
      body.push(
        h(
          "div",
          { class: "cvs-wire-row", "data-at": String(at) },
          box,
          button("Up", () => move(-1), { icon: "up", iconOnly: true, class: "ghost" }),
          button("Down", () => move(1), { icon: "down", iconOnly: true, class: "ghost" }),
          button("Remove", () => put(items.filter((_, i) => i !== at)), { icon: "close", iconOnly: true, class: "ghost" }),
        ),
      );
    });
    const add = h("select", { class: "wg-input cvs-wire-add", disabled: !editable, "aria-label": `${port.name}: add a table` }, h("option", { value: "" }, "Add a table…"), ...tableOptions(context, ""));
    add.append(...outOptions(port, id, page, wiring, "", true, context.page_names));
    add.addEventListener("change", () => {
      const made = wireOf(add.value);
      if (made) put([...items, made]);
    });
    body.push(add);
  } else {
    const current = keyOf(given);
    const box = h("select", { class: "wg-input cvs-source", disabled: !editable, "aria-label": `${port.name}: its source` });
    box.append(h("option", { value: "", selected: !current }, auto ? `Automatic: ${outWords(auto.from, wiring, page, context.page_names)}` : `Not wired (${port.default === null ? "none" : JSON.stringify(port.default)})`));
    if (port.type === "Table") box.append(...tableOptions(context, current));
    box.append(...outOptions(port, id, page, wiring, current, false, context.page_names));
    const gets = (context.endpoints ?? []).filter((e) => e.startsWith("GET "));
    if (gets.length && (port.type === "Table" || port.type === "dict" || port.type.startsWith("list"))) {
      box.append(h("optgroup", { label: "Local sandbox API" }, ...gets.map((e) => h("option", { value: `endpoint:${e}`, selected: current === `endpoint:${e}` }, e))));
    }
    if (context.variables.length && ["str", "int", "float", "bool", "date", "datetime"].includes(port.type)) {
      box.append(h("optgroup", { label: "Variables" }, ...context.variables.map((v) => h("option", { value: `variable:${v}`, selected: current === `variable:${v}` }, v))));
    }
    box.append(h("option", { value: "page", selected: current === "page" }, "A page value by its key…"));
    if (port.type !== "Table") box.append(h("option", { value: "value", selected: current === "value" }, "A value…"));
    if (current.startsWith("out:") && !box.querySelector(`option[value="${CSS.escape(current)}"]`)) box.append(h("option", { value: current, selected: true }, `${current.slice(4)} (not there any more)`));
    if (current.startsWith("table:") && !box.querySelector(`option[value="${CSS.escape(current)}"]`)) box.append(h("option", { value: current, selected: true }, current.slice(6)));
    const typed = h("input", { type: "text", class: "wg-input cvs-source-typed", hidden: current !== "value" && current !== "page", disabled: !editable, spellcheck: "false", "data-no-variables": "", "aria-label": `${port.name}: ${current === "page" ? "the key" : "the value"}` }) as HTMLInputElement;
    if (current === "value") typed.value = port.type === "str" ? String(given?.value ?? "") : JSON.stringify(given?.value);
    if (current === "page") typed.value = String(given?.page ?? "");
    const typedSend = (): void => {
      const raw = typed.value;
      if (box.value === "page") return void sending(said, () => send(port.name, { page: raw.trim() }));
      let value: unknown = raw;
      if (port.type !== "str") {
        try {
          value = JSON.parse(raw);
        } catch {
          return said(`${port.name} takes ${port.words}: as JSON, such as ${port.type === "bool" ? "true" : port.type.startsWith("list") ? '["a"]' : "3"}.`);
        }
      }
      void sending(said, () => send(port.name, { value }));
    };
    typed.addEventListener("change", typedSend);
    box.addEventListener("change", () => {
      if (box.value === "value" || box.value === "page") {
        typed.hidden = false;
        typed.setAttribute("aria-label", `${port.name}: ${box.value === "page" ? "the key" : "the value"}`);
        typed.focus();
        return;
      }
      typed.hidden = true;
      void sending(said, () => send(port.name, wireOf(box.value)));
    });
    body.push(box, typed);
  }
  return h("div", { class: `wg-prop cvs-port${broken ? " marked" : ""}`, "data-port": port.name, "data-direction": "in" }, head, port.help ? h("div", { class: "wg-prop-help" }, port.help) : null, ...body, note);
}

function outputField(port: Port, id: string, wiring: Wiring): HTMLElement {
  const readers = wiring.readers[`${id}.${port.name}`] ?? [];
  const named = readers.map((r) => {
    const [instance, name] = r.split(".");
    return `${instance} ${wiring.ports[instance!]?.widget ?? ""} · ${name}`;
  });
  return h(
    "div",
    { class: "wg-prop cvs-port", "data-port": port.name, "data-direction": "out" },
    h("div", { class: "wg-prop-head" }, h("span", { class: "wg-prop-name" }, port.name), h("span", { class: "wg-prop-mask" }, `Out · ${port.words}`)),
    port.help ? h("div", { class: "wg-prop-help" }, port.help) : null,
    h("div", { class: "cvs-readers" }, named.length ? `Read by ${named.join(", ")}` : "Nothing reads it yet."),
  );
}

function eventField(port: Port, given: Wire | undefined, context: WiringContext, editable: boolean, send: SendWire): HTMLElement {
  const { element: note, said } = line();
  const actions: Action[] = Array.isArray(given?.actions) ? (given!.actions as Action[]) : [];
  const put = (next: Action[]): void => void sending(said, () => send(port.name, next.length ? { actions: next } : null));
  const change = (at: number, part: Partial<Action>): void => put(actions.map((a, i) => (i === at ? { ...a, ...part } : a)));
  // A typed payload's fields (saved: Event[Order]) offered in every box that names a part of it.
  const payload = (port.fields ?? []).map((f) => f.name);
  const listId = payload.length ? `cvs-payload-${port.name}-${Math.random().toString(36).slice(2, 8)}` : "";
  const text = (label: string, value: string, done: (v: string) => void, placeholder = "", suggest = false): HTMLElement => {
    const input = h("input", { type: "text", class: "wg-input", value, placeholder, disabled: !editable, spellcheck: "false", "data-no-variables": "", "aria-label": label, list: suggest && listId ? listId : undefined }) as HTMLInputElement;
    input.addEventListener("change", () => done(input.value.trim()));
    return h("label", { class: "wg-field" }, h("span", { class: "wg-label" }, label), input);
  };
  const rows = actions.map((action, at) => {
    const parts: HTMLElement[] = [];
    if (action.do === "call") {
      const endpoint = h("select", { class: "wg-input", disabled: !editable, "aria-label": "Endpoint" }, h("option", { value: "" }, "(pick an endpoint)"), ...(context.endpoints ?? []).map((e) => h("option", { value: e, selected: e === action.endpoint }, e)));
      endpoint.addEventListener("change", () => change(at, { endpoint: endpoint.value, body: "", params: {} }));
      parts.push(h("label", { class: "wg-field" }, h("span", { class: "wg-label" }, "Call"), endpoint));
      const fields = action.endpoint ? context.endpoint_fields?.[action.endpoint] : undefined;
      const mapped = typeof action.body === "object" && action.body !== null ? action.body : null;
      if (fields?.length) {
        for (const field of fields) {
          parts.push(
            text(field, mapped?.[field] ?? "", (v) => {
              const next = { ...(mapped ?? {}) };
              if (v) next[field] = v;
              else delete next[field];
              change(at, { body: Object.keys(next).length ? next : "" });
            }, payload.includes(field) ? field : payload.length ? `a field: ${payload.slice(0, 3).join(", ")}` : "a part of the payload, as values." + field, true),
          );
        }
      }
      if (!mapped) parts.push(text("Body", typeof action.body === "string" ? action.body : "", (v) => change(at, { body: v }), "empty: the whole payload", true));
      for (const name of (action.endpoint ?? "").match(/\{(\w+)\}/g) ?? []) {
        const bare = name.slice(1, -1);
        parts.push(text(`Path: ${bare}`, action.params?.[bare] ?? "", (v) => change(at, { params: { ...(action.params ?? {}), [bare]: v } }), `the payload's ${bare}`, true));
      }
    } else if (action.do === "set") {
      parts.push(text("Page value", action.key ?? "", (v) => change(at, { key: v }), "its key, as last_saved"));
      parts.push(text("To", action.value ?? "", (v) => change(at, { value: v }), "empty: the whole payload", true));
    } else {
      parts.push(h("div", { class: "wg-prop-help" }, "The page runs again."));
    }
    return h(
      "div",
      { class: "cvs-action", "data-action": action.do, "data-at": String(at) },
      h("div", { class: "cvs-action-head" }, h("span", {}, { call: "Call an API endpoint", set: "Set a page value", rerun: "Rerun the page" }[action.do]), button("Remove the action", () => put(actions.filter((_, i) => i !== at)), { icon: "close", iconOnly: true, class: "ghost" })),
      ...parts,
    );
  });
  const add = h("select", { class: "wg-input cvs-action-add", disabled: !editable, "aria-label": `${port.name}: add an action` }, h("option", { value: "" }, "Add an action…"), h("option", { value: "call" }, "Call an API endpoint"), h("option", { value: "set" }, "Set a page value"), h("option", { value: "rerun" }, "Rerun the page"));
  add.addEventListener("change", () => {
    const made: Action | null = add.value === "call" ? { do: "call", endpoint: (context.endpoints ?? []).find((e) => !e.startsWith("GET ")) ?? context.endpoints?.[0] ?? "", body: "" } : add.value === "set" ? { do: "set", key: `${port.name}_payload`, value: "" } : add.value === "rerun" ? { do: "rerun" } : null;
    if (made) put([...actions, made]);
  });
  return h(
    "div",
    { class: "wg-prop cvs-port", "data-port": port.name, "data-direction": "event" },
    h("div", { class: "wg-prop-head" }, h("span", { class: "wg-prop-name" }, port.name), h("span", { class: "wg-prop-mask" }, port.schema ? `Event · ${port.schema}` : "Event")),
    port.help ? h("div", { class: "wg-prop-help" }, port.help) : null,
    payload.length ? h("div", { class: "cvs-payload" }, `Its payload: ${(port.fields ?? []).map((f) => `${f.name} (${f.type})`).join(", ")}`) : null,
    listId ? h("datalist", { id: listId }, ...payload.map((f) => h("option", { value: f }))) : null,
    ...rows,
    add,
    note,
  );
}

/** The INPUTS, OUTPUTS and EVENTS sections of one instance (empty ones left out). */
export function wiringSections(id: string, wires: Record<string, Wire> | undefined, wiring: Wiring | undefined, context: WiringContext, editable: boolean, send: SendWire, section: (title: string, ...children: HTMLElement[]) => HTMLElement): HTMLElement[] {
  const ports = wiring?.ports[id];
  if (!wiring || !ports) return [];
  const out: HTMLElement[] = [];
  if (ports.ins.length) out.push(section("INPUTS", ...ports.ins.map((p) => inputField(p, id, ports.page, wires?.[p.name], wiring, context, editable, send))));
  if (ports.outs.length) out.push(section("OUTPUTS", ...ports.outs.map((p) => outputField(p, id, wiring))));
  if (ports.events.length) out.push(section("EVENTS", ...ports.events.map((p) => eventField(p, wires?.[p.name], context, editable, send))));
  return out;
}

/** A node's marks: lit as the selected widget's source or reader, or broken (either end of a broken wire). */
export function nodeMarks(id: string, selected: string[], wiring: Wiring | undefined): string {
  if (!wiring) return "";
  const marks: string[] = [];
  const mine = (ref: string): string => ref.split(".")[0]!;
  if (selected.some((s) => wiring.wires.some((w) => mine(w.to) === s && mine(w.from) === id))) marks.push("wire-source");
  if (selected.some((s) => wiring.wires.some((w) => mine(w.from) === s && mine(w.to) === id))) marks.push("wire-reader");
  if (wiring.broken.some((b) => b.instance === id || (b.source && mine(b.source) === id))) marks.push("wire-broken");
  return marks.map((m) => ` ${m}`).join("");
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Where each port's dot is on its widget's edges: its Ins down the left edge, its Outs and Events down the
 *  right, evenly spaced, in the order the widget declares them. */
export function portPoints(id: string, box: Box, wiring: Wiring): Record<string, { x: number; y: number; side: "in" | "out" }> {
  const ports = wiring.ports[id];
  const found: Record<string, { x: number; y: number; side: "in" | "out" }> = {};
  if (!ports) return found;
  const place = (names: string[], x: number, side: "in" | "out"): void => {
    names.forEach((name, at) => {
      found[`${id}.${name}`] = { x, y: Math.round(box.y + ((at + 1) * box.h) / (names.length + 1)), side };
    });
  };
  place(ports.ins.map((p) => p.name), box.x, "in");
  place([...ports.outs, ...ports.events].map((p) => p.name), box.x + box.w, "out");
  return found;
}

/** The Wiring view: a line from the exact Out port to each In port that reads it on this page (automatic ones
 *  dashed), a small dot on each widget's edge per port; a wire from another page (or the app's own viewer)
 *  is a stub at its In with the page's name; a broken wire's stub is marked. */
export function wiresOverlay(wiring: Wiring | undefined, boxOf: (id: string) => Box | null, page: string, width: number, height: number, names: Record<string, string> = {}): SVGSVGElement {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "cvs-wires");
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.setAttribute("aria-hidden", "true");
  if (!wiring) return svg;
  const points: Record<string, { x: number; y: number; side: "in" | "out" }> = {};
  for (const [id, ports] of Object.entries(wiring.ports)) {
    if (ports.page !== page) continue;
    const box = boxOf(id);
    if (box) Object.assign(points, portPoints(id, box, wiring));
  }
  const make = (tag: string, attrs: Record<string, string>): SVGElement => {
    const made = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) made.setAttribute(k, v);
    return made;
  };
  const stub = (to: { x: number; y: number }, label: string, cls: string, data: Record<string, string>): void => {
    // Out to the left when there is room for the page's name; at the board's left edge, up and over the widget.
    const room = to.x >= 64;
    const d = room ? `M ${to.x - 56} ${to.y} L ${to.x} ${to.y}` : `M ${to.x} ${to.y - 22} L ${to.x} ${to.y}`;
    svg.append(make("path", { d, class: `cvs-wire cvs-wire-stub ${cls}`.trim(), ...data }));
    const at = room ? { x: String(to.x - 59), y: String(to.y + 3), "text-anchor": "end" } : { x: String(to.x + 4), y: String(to.y - 14), "text-anchor": "start" };
    const text = make("text", { ...at, class: `cvs-wire-label ${cls}`.trim() });
    text.textContent = label;
    svg.append(text);
  };
  for (const wire of wiring.wires) {
    const b = points[wire.to];
    if (!b) continue;
    const a = points[wire.from];
    const data = { "data-from": wire.from, "data-to": wire.to };
    if (!a || wire.cross) {
      const label = wire.from === VIEWER ? "viewer" : (names[wire.page ?? ""] ?? wire.page ?? wire.from);
      stub(b, label, `cross${wire.auto ? " auto" : ""}`, data);
      continue;
    }
    // Out of the right edge, into the left one; the bends kept on the board (an In left of its Out curves back).
    const bend = Math.max(40, Math.min(160, Math.abs(b.x - a.x) / 2));
    const c1 = Math.min(width - 2, a.x + bend);
    const c2 = Math.max(2, b.x - bend);
    svg.append(make("path", { d: `M ${a.x} ${a.y} C ${c1} ${a.y}, ${c2} ${b.y}, ${b.x} ${b.y}`, class: `cvs-wire${wire.auto ? " auto" : ""}`, ...data }));
  }
  for (const broken of wiring.broken) {
    const b = points[`${broken.instance}.${broken.port}`];
    if (b) stub(b, "broken", "broken", { "data-to": `${broken.instance}.${broken.port}`, "data-from": broken.source ?? "" });
  }
  for (const [ref, at] of Object.entries(points)) {
    const dot = make("circle", { cx: String(at.x), cy: String(at.y), r: "4", class: `cvs-port-dot ${at.side}`, "data-port": ref });
    const title = make("title", {});
    title.textContent = ref;
    dot.append(title);
    svg.append(dot);
  }
  return svg;
}

/** Before Play: the broken wires, one line each. */
export function brokenWords(wiring: Wiring | undefined): string {
  const broken = wiring?.broken ?? [];
  if (!broken.length) return "";
  return `${broken.length === 1 ? "A wire is" : `${broken.length} wires are`} broken: ${broken.map((b) => `${b.instance}.${b.port}: ${b.reason}`).join(" ")}`;
}

