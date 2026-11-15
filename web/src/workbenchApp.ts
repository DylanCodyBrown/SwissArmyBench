/**
 * workbenchApp.ts: App mode's panels for a Streamlit app's canvas (the Workbench's modes, 2026-11-15).
 * [WIRE]
 *
 *   [PROPERTIES]  the selected block: its name (the cell's own, renamed in its document), its size, its
 *                 source cell (in its document's kind colour; a click goes there), what it makes and
 *                 reads, the blocks it feeds, and its widget's value on the live page. With no block
 *                 selected: the page settings (title, icon, wide or centred, logo, theme colours),
 *                 written into the saved pages and the zip as st.set_page_config, st.logo and
 *                 .streamlit/config.toml
 *   [STATE]       what the live page's session holds (st.session_state: each widget's value by its key),
 *                 each key with its block; Reset state starts the page again with a fresh session
 *
 * ROUTING: PUT /streamlit/apps/{app}/settings, GET /streamlit/apps/{app}/session (routes_streamlit.py)
 */
import { button, clear, h, icon, toast } from "./dom";
import { kindIcon, kindOfPath } from "./kindColours";
import type { CanvasView } from "./workbenchCanvas";
import type { ModeFrame } from "./workbenchModes";
import { type AppSettings, type BlockState, type SessionRow, shownValue } from "./workbenchStreamlit";

export interface AppHost {
  /** Go to a block's cell (its document opened when it is not). */
  goToCell: (document: string, cell: number) => void;
  /** Name a cell of a document (its document opened when it is not). */
  renameCell: (document: string, cell: number, name: string) => Promise<void>;
  /** Choose a logo's file. */
  chooseLogo: () => Promise<string | null>;
}

const COLOURS: [keyof AppSettings["colours"], string][] = [
  ["primary", "Primary"],
  ["background", "Background"],
  ["secondary_background", "Panels"],
  ["text", "Text"],
];

const chip = (name: string): HTMLElement => h("span", { class: "app-chip mono" }, name);

/** A stepper: − value +. */
function stepper(label: string, shown: string, down: (() => void) | null, up: (() => void) | null): HTMLElement {
  const minus = button(`Less ${label.toLowerCase()}`, () => down?.(), { icon: "minus", iconOnly: true, class: "ghost" });
  const plus = button(`More ${label.toLowerCase()}`, () => up?.(), { icon: "plus", iconOnly: true, class: "ghost" });
  minus.disabled = !down;
  plus.disabled = !up;
  return h("div", { class: "app-row" }, h("span", { class: "app-label" }, label), h("span", { class: "app-stepper", role: "group", "aria-label": label }, minus, h("output", { class: "app-step-value" }, shown), plus));
}

const section = (title: string, ...children: (HTMLElement | null)[]): HTMLElement => h("section", { class: "app-section" }, h("h3", { class: "app-heading" }, title), ...children);

/** Properties: the selected block, else the page settings. `rows`: the live page's state, when known. */
export function drawProperties(body: HTMLElement, canvas: CanvasView, host: AppHost, rows: SessionRow[]): void {
  const block = canvas.selected();
  if (block) return drawBlock(body, canvas, host, block, rows);
  drawSettings(body, canvas, host);
}

function drawBlock(body: HTMLElement, canvas: CanvasView, host: AppHost, block: BlockState, rows: SessionRow[]): void {
  const name = h("input", { type: "text", class: "app-input", value: block.name ?? "", maxlength: 80, "aria-label": "Name", dataset: { field: "name" } }) as HTMLInputElement;
  name.addEventListener("change", () => {
    const typed = name.value.trim();
    if (typed === (block.name ?? "")) return;
    void host.renameCell(block.document, block.cell, typed).catch((e: Error) => toast(e.message, "error"));
  });
  name.addEventListener("keydown", (e) => {
    if (e.key === "Enter") name.blur();
    e.stopPropagation();
  });
  const kind = kindOfPath(block.document) ?? "notebook";
  const source = h(
    "button",
    { type: "button", class: `link app-source km-${kind}`, title: block.document, onclick: () => host.goToCell(block.document, block.cell) },
    icon(kindIcon(kind, block.document)),
    h("span", { class: "mono" }, block.where),
  );
  const feeds = canvas.feeds(block.id);
  const values = rows.filter((r) => r.block !== null && r.block === block.name);
  const w = block.w;
  const height = block.h;
  clear(
    body,
    section("Name", name),
    section(
      "Size",
      stepper("Width", `${w} of 12`, w > 2 ? () => void canvas.changeBlock(block.id, { w: w - 1 }) : null, block.column + w <= 12 ? () => void canvas.changeBlock(block.id, { w: w + 1 }) : null),
      stepper("Height", height === null ? "Fits" : `${height} ${height === 1 ? "row" : "rows"}`, height !== null ? () => void canvas.changeBlock(block.id, { h: height > 1 ? height - 1 : null }) : null, height === null || height < 30 ? () => void canvas.changeBlock(block.id, { h: height === null ? 2 : height + 1 }) : null),
    ),
    section(
      "Source cell",
      source,
      block.makes.length ? h("div", { class: "app-row" }, h("span", { class: "app-label" }, "Makes"), h("span", { class: "app-chips" }, ...block.makes.map(chip))) : null,
      block.reads.length || block.tables.length ? h("div", { class: "app-row" }, h("span", { class: "app-label" }, "Reads"), h("span", { class: "app-chips" }, ...[...block.tables, ...block.reads].map(chip))) : null,
    ),
    feeds.length
      ? section(
          "Feeds",
          h(
            "ul",
            { class: "app-feeds" },
            ...feeds.map((f) => h("li", {}, h("button", { type: "button", class: "link", onclick: () => canvas.select(f.id) }, icon("forward"), h("span", {}, f.name ?? f.where)))),
          ),
        )
      : null,
    values.length ? section("Widget value", ...values.map((r) => h("div", { class: "app-value" }, h("span", { class: "mono" }, r.key), h("span", { class: "mono" }, shownValue(r.value))))) : null,
  );
}

function drawSettings(body: HTMLElement, canvas: CanvasView, host: AppHost): void {
  const settings = canvas.settings();
  const text = (field: "title" | "icon" | "logo", label: string, max: number, placeholder = ""): HTMLInputElement => {
    const input = h("input", { type: "text", class: "app-input", value: settings[field], maxlength: max, placeholder, "aria-label": label, dataset: { field } }) as HTMLInputElement;
    input.addEventListener("change", () => void canvas.setSettings({ [field]: input.value }));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") input.blur();
      e.stopPropagation();
    });
    return input;
  };
  const layout = (value: "wide" | "centered", label: string): HTMLButtonElement => button(label, () => void canvas.setSettings({ layout: value }), { pressed: settings.layout === value, class: `app-layout-${value}` });
  const colour = ([key, label]: (typeof COLOURS)[number]): HTMLElement => {
    const chosen = settings.colours[key];
    const input = h("input", { type: "color", value: chosen ?? "#ffffff", "aria-label": `${label} colour`, dataset: { colour: key } }) as HTMLInputElement;
    input.addEventListener("change", () => void canvas.setSettings({ colours: { [key]: input.value } }));
    return h(
      "div",
      { class: `app-row app-colour${chosen ? "" : " unset"}` },
      h("span", { class: "app-label" }, label),
      input,
      chosen ? button(`${label}: the theme's own`, () => void canvas.setSettings({ colours: { [key]: null } }), { icon: "close", iconOnly: true, class: "ghost" }) : null,
    );
  };
  const logo = text("logo", "Logo", 500, "logo.png");
  clear(
    body,
    section("Title", text("title", "Title", 120)),
    section("Icon", text("icon", "Icon", 8)),
    section("Layout", h("div", { class: "cv-mode app-layout", role: "group", "aria-label": "Layout" }, layout("wide", "Wide"), layout("centered", "Centred"))),
    section(
      "Logo",
      h(
        "div",
        { class: "app-row" },
        logo,
        button("Browse…", () => void host.chooseLogo().then((path) => (path ? canvas.setSettings({ logo: path }) : false)), { class: "ghost" }),
      ),
    ),
    section("Theme colours", ...COLOURS.map(colour)),
  );
}

/** The State panel: each key the live page's session holds, its value, its block. */
export function drawState(body: HTMLElement, rows: SessionRow[], live: boolean): void {
  if (!live) return void clear(body, h("p", { class: "hint app-empty" }, "Play shows the page's state"));
  if (!rows.length) return void clear(body, h("p", { class: "hint app-empty" }, "Nothing held yet"));
  clear(
    body,
    h(
      "table",
      { class: "app-state" },
      h("thead", {}, h("tr", {}, h("th", {}, "Key"), h("th", {}, "Value"), h("th", {}, "Block"))),
      h("tbody", {}, ...rows.map((r) => h("tr", { dataset: { key: r.key } }, h("td", { class: "mono" }, r.key), h("td", { class: "mono" }, shownValue(r.value)), h("td", {}, r.block ?? "")))),
    ),
  );
}

/** App mode's two panels on a canvas document, and the state they share (the live page's). */
export function appPanels(frame: ModeFrame, canvas: () => CanvasView, host: AppHost): { refresh: () => void; rows: () => SessionRow[]; resetState: () => void } {
  let rows: SessionRow[] = [];
  let timer: number | null = null;
  const live = (): boolean => canvas().mode() === "live";
  const fetchRows = async (): Promise<void> => {
    if (!live()) {
      rows = [];
      return;
    }
    try {
      rows = await canvas().session();
    } catch {
      /* the app went away: the next draw says so */
    }
  };
  const draw = (): void => {
    frame.redraw("properties");
    frame.redraw("state");
  };
  const poll = (): void => {
    if (timer !== null) window.clearTimeout(timer);
    timer = null;
    if (!frame.isOpen("state") && !frame.isOpen("properties")) return;
    if (!live()) return;
    timer = window.setTimeout(() => void fetchRows().then(() => {
      draw();
      poll();
    }), 1500);
  };
  const resetState = (): void => {
    canvas().resetState();
    rows = [];
    draw();
  };
  frame.add({ id: "properties", title: "Properties", icon: "properties", where: "side", panel: "workbench.properties", draw: (body) => drawProperties(body, canvas(), host, rows) });
  frame.add({
    id: "state",
    title: "State",
    icon: "sliders",
    where: "bottom",
    panel: "workbench.state",
    draw: (body) => {
      drawState(body, rows, live());
      poll();
    },
    tools: () => [button("Reset state", () => resetState(), { icon: "reset", class: "ghost app-reset" })],
  });
  return {
    refresh: () => {
      void fetchRows().then(draw);
    },
    rows: () => rows,
    resetState,
  };
}
