/**
 * canvasProps.ts: the Canvas's Properties pane, for what is selected. Moved out of canvasPage.ts along its own
 * heading (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [CONTAINER] its title, border, scrollable, resizable, height, padding, columns inside, background, size
 *   [WIDGET]    its name with Edit widget, its description; each property by its mask (widgetFields.ts), a
 *               value checked by the server before it is kept; an In[Table]'s columns from what it is wired to;
 *               Inputs, Outputs and Events (canvasWiring.ts); its size
 *   [LAYOUT]    Show on (both layouts, or one) and Hidden in the app
 *
 * ROUTING: POST /streamlit/widgets/check-value, POST /streamlit/canvases/{canvas}/command (kind wire)
 */
import { api, ApiError, saidOf } from "./api";
import type { CanvasNode as Node, CanvasState as State, ContainerProps } from "./canvasPage";
import { type WiringContext, wiringSections } from "./canvasWiring";
import { button, clear, h } from "./dom";
import { openWidgets } from "./rail";
import { type Prop, propertyField } from "./widgetFields";
import type { Context, WidgetEntry } from "./widgetPage";

/** What the pane asks of the page: its pane, the canvas and what is selected, a command sent, the canvas read
 *  again, and the page's number box. */
export interface PropsHost {
  pane: HTMLElement;
  window: string;
  editable: () => boolean;
  send: (kind: string, body: Record<string, unknown>) => Promise<State | null>;
  take: (next: State) => void;
  reload: () => Promise<void>;
  find: (id: string) => { node: Node; parent: Node | null } | null;
  entry: (name: string) => WidgetEntry | undefined;
  pageNames: () => Record<string, string>;
  numberBox: (label: string, value: number, min: number, max: number, change: (v: number) => void) => HTMLElement;
  readonly state: State | null;
  readonly selected: string[];
  readonly context: Context & WiringContext;
}

export function canvasProps(host: PropsHost) {
  function section(title: string, ...children: (HTMLElement | null)[]): HTMLElement {
    return h("section", { class: "cvs-props-section" }, h("h3", {}, title), ...children);
  }

  function sizeFields(node: Node): HTMLElement {
    const boxes = (["x", "y", "w", "h"] as const).map((key) => {
      const input = h("input", { type: "number", class: "cvs-num", value: String(node[key]), min: key === "w" || key === "h" ? 1 : 0, "aria-label": { x: "Left", y: "Top", w: "Width", h: "Height" }[key], disabled: !host.editable() });
      input.addEventListener("change", () => {
        const v = Math.round(Number(input.value));
        if (Number.isFinite(v)) void host.send("move", { id: node.id, [key]: v });
      });
      return h("label", { class: "cvs-field" }, h("span", {}, { x: "X", y: "Y", w: "W", h: "H" }[key]), input);
    });
    return h("div", { class: "cvs-size" }, ...boxes, h("span", { class: "cvs-px" }, "px"));
  }

  function containerFields(node: Node): HTMLElement[] {
    const p = node.props!;
    const set = (props: Partial<ContainerProps>): void => void host.send("set_container", { id: node.id, props });
    const flag = (label: string, key: "border" | "scrollable" | "resizable"): HTMLElement => {
      const input = h("input", { type: "checkbox", role: "switch", class: "wg-switch", checked: p[key], disabled: !host.editable(), "aria-label": label, "data-prop": key });
      input.addEventListener("change", () => set({ [key]: input.checked }));
      return h("label", { class: "cvs-flag" }, input, h("span", {}, label));
    };
    const title = h("input", { class: "wg-input", value: p.title, "aria-label": "Title", disabled: !host.editable(), "data-no-variables": "" });
    title.addEventListener("change", () => set({ title: title.value }));
    const height = h("select", { class: "wg-input", "aria-label": "Height", disabled: !host.editable() }, h("option", { value: "fit", selected: p.height === "fit" }, "Fit"), h("option", { value: "fixed", selected: p.height === "fixed" }, "Fixed"));
    height.addEventListener("change", () => set({ height: height.value as ContainerProps["height"] }));
    const background = h("input", { type: "text", class: "wg-input", value: p.background, placeholder: "none", "aria-label": "Background", disabled: !host.editable(), "data-no-variables": "" });
    background.addEventListener("change", () => set({ background: background.value.trim() }));
    return [
      h("label", { class: "wg-field" }, h("span", { class: "wg-label" }, "Title"), title),
      flag("Border", "border"),
      flag("Scrollable", "scrollable"),
      flag("Resizable", "resizable"),
      h("label", { class: "wg-field" }, h("span", { class: "wg-label" }, "Height"), height),
      host.numberBox("Padding", p.padding, 0, 64, (v) => set({ padding: v })),
      host.numberBox("Columns inside", p.columns, 1, 48, (v) => set({ columns: v })),
      h("label", { class: "wg-field" }, h("span", { class: "wg-label" }, "Background"), background),
      h("div", { class: "wg-label" }, "Size"),
      sizeFields(node),
    ];
  }

  function drawProps(): void {
    if (!host.state) return;
    clear(host.pane, h("div", { class: "cvs-pane-head" }, h("h2", {}, "Properties")));
    const nodes = host.selected.map((id) => host.find(id)).filter((x): x is { node: Node; parent: Node | null } => x !== null);
    if (!nodes.length) {
      host.pane.append(h("p", { class: "cvs-props-none" }, "Select a container or a widget."));
      return;
    }
    const first = nodes[0]!.node;
    const same = nodes.every((n) => n.node.kind === first.kind && n.node.widget === first.widget);
    if (!same) {
      host.pane.append(h("p", { class: "cvs-props-none" }, `${nodes.length} selected: they share no properties.`));
      return;
    }
    if (first.kind === "container") {
      host.pane.append(section(nodes.length > 1 ? `CONTAINERS (${nodes.length})` : "CONTAINER", ...containerFields(first)));
      if (nodes.length === 1) host.pane.append(section("LAYOUT", showOn(first), hiddenInApp(first)));
      return;
    }
    const known = host.entry(first.widget ?? "");
    host.pane.append(
      section(
        "WIDGET",
        h("div", { class: "cvs-widget-line" }, h("span", { class: "cvs-widget-title" }, first.widget ?? ""), button("Edit widget", () => openWidgets(first.widget), { class: "ghost cvs-edit-widget" })),
        known ? h("div", { class: "wg-prop-help" }, known.description) : h("div", { class: "wg-field-line" }, "This widget is not in the library any more."),
      ),
    );
    if (known) {
      const marks = host.state.marks[first.id] ?? {};
      const values: Record<string, unknown> = { ...Object.fromEntries(known.properties.map((p) => [p.name, p.default])), ...(first.values ?? {}) };
      // A column property of an In[Table]: the columns of the table it is wired to; wired from an Out (or by
      // itself), that Out's columns once known (declared Table[Row], else as Play last ran it); else typed.
      const fieldContext = { ...host.context, tables: { ...host.context.tables } };
      for (const port of host.state.wiring?.ports[first.id]?.ins ?? []) {
        if (port.type !== "Table") continue;
        const source = host.state.wiring?.sources[first.id]?.[port.name] as { table?: string; out?: string } | undefined;
        if (source?.out) {
          values[port.name] = `out:${source.out}`;
          fieldContext.tables[`out:${source.out}`] = host.state.wiring?.columns?.[source.out] ?? null;
        } else values[port.name] = source?.table ?? (source ? "?" : "");
      }
      const fields = known.properties.map((prop: Prop) =>
        propertyField(
          prop,
          values,
          fieldContext,
          !host.editable(),
          async (value, said) => {
            const checked = await api<{ ok: boolean; said?: string; fix?: string }>("/streamlit/widgets/check-value", "POST", { name: known.name, property: prop.name, value, values });
            if (!checked.ok) return said(`${checked.said ?? ""} ${checked.fix ?? ""}`.trim());
            said("");
            for (const n of nodes) await host.send("set_values", { id: n.node.id, values: { [prop.name]: value } });
          },
          { marked: marks[prop.name] ?? null, overridden: nodes.length === 1 && Object.hasOwn(first.values ?? {}, prop.name), onReset: () => void host.send("set_values", { id: first.id, values: { [prop.name]: null } }) },
        ),
      );
      if (fields.length) host.pane.append(section("PROPERTIES", ...fields));
      if (nodes.length === 1) {
        const sendWire = async (port: string, wire: Record<string, unknown> | null): Promise<void> => {
          if (!host.state) return;
          try {
            host.take(await api<State>(`/streamlit/canvases/${host.state.canvas}/command`, "POST", { kind: "wire", id: first.id, port, wire, version: host.state.version, window: host.window }));
          } catch (e) {
            if (e instanceof ApiError && e.status === 409) await host.reload();
            throw new Error(String((e instanceof ApiError ? saidOf(e)?.error : null) ?? (e instanceof Error ? e.message : e)));
          }
        };
        host.pane.append(...wiringSections(first.id, first.wires, host.state.wiring, { ...host.context, page_names: host.pageNames() }, host.editable(), sendWire, (title, ...children) => section(title, ...children)));
      }
    }
    if (nodes.length === 1) host.pane.append(section("SIZE", sizeFields(first)), section("LAYOUT", showOn(first), hiddenInApp(first)));
  }

  /** Hidden in the app: a widget (or a container's widgets) runs and its Outs flow, but the played, launched or
   *  exported page gives it no space (a widget that only moves data; a titled box of them). */
  function hiddenInApp(node: Node): HTMLElement {
    const input = h("input", { type: "checkbox", class: "cvs-hidden", checked: Boolean(node.hidden), disabled: !host.editable(), "aria-label": "Hidden in the app" }) as HTMLInputElement;
    input.addEventListener("change", () => void host.send("hide", { id: node.id, hidden: input.checked }));
    return h("label", { class: "cvs-flag" }, input, h("span", {}, "Hidden in the app"));
  }

  /** Show on: both layouts, or one only (the owner: "Hiding a container or widget in one layout only"). */
  function showOn(node: Node): HTMLElement {
    const box = h("select", { class: "wg-input cvs-show", "aria-label": "Show on", disabled: !host.editable() });
    for (const [value, label] of [["both", "Phone and Desktop"], ["desktop", "Desktop only"], ["phone", "Phone only"]] as const) box.append(h("option", { value, selected: (node.show ?? "both") === value }, label));
    box.addEventListener("change", () => void host.send("show", { id: node.id, show: box.value }));
    return h("label", { class: "wg-field" }, h("span", { class: "wg-label" }, "Show on"), box);
  }

  return { drawProps };
}
