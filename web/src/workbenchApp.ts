/**
 * workbenchApp.ts: App mode's panels for a Streamlit app's canvas (the Workbench's modes, 2026-11-15).
 * [WIRE]
 *
 *   [PROPERTIES]  the selected block: its name (the cell's own, renamed in its document), its size, its
 *                 source cell (in its document's kind colour; a click goes there), what it makes and
 *                 reads, the blocks it feeds, and its widget's value on the live page; its controller
 *                 (domain/controllers.py: its role, what it makes with types and defaults, what is
 *                 wrong with its contract) and Lineage… (the overlay, back to the data). With no block
 *                 selected: the page settings (title, icon, wide or centred, logo, theme colours),
 *                 written into the saved pages and the zip as st.set_page_config, st.logo and
 *                 .streamlit/config.toml
 *   [STATE]       what the live page's session holds (st.session_state: each widget's value by its key),
 *                 each key with its block; Reset state starts the page again with a fresh session
 *
 * ROUTING: PUT /streamlit/apps/{app}/settings, GET /streamlit/apps/{app}/session (routes_streamlit.py)
 */
import { button, clear, h, icon } from "./dom";
import { kindIcon, kindOfPath } from "./kindColours";
import { canvasPane, type CodePlan, type Inspected } from "./canvasPane";
import type { CanvasView } from "./workbenchCanvas";
import type { ModeFrame } from "./workbenchModes";
import { type AppSettings, type SessionRow, shownValue } from "./workbenchStreamlit";

export interface AppHost {
  /** Go to a block's cell (its document opened when it is not), at a line of it. */
  goToCell: (document: string, cell: number, line?: number | null) => void;
  /** A change to a cell's code made in its open document, like typing (the pane's plan). */
  applyCode: (plan: CodePlan) => Promise<boolean>;
  openVariable: (name: string) => void;
  openConnection: (name: string) => void;
  openGrid: (grid: string) => void;
  /** Name a cell of a document (its document opened when it is not). */
  renameCell: (document: string, cell: number, name: string) => Promise<void>;
  /** Choose a logo's file. */
  chooseLogo: () => Promise<string | null>;
  /** The lineage overlay for a block of the page in front. */
  lineage?: (block: string) => void;
  /** A SQL cell's connections, a DAX cell's datasets; a query cell put on another (the property pane). */
  sources?: (kind: "sql" | "dax") => string[];
  setConnection?: (document: string, cell: number, connection: string) => Promise<void>;
}

const COLOURS: [keyof AppSettings["colours"], string][] = [
  ["primary", "Primary"],
  ["background", "Background"],
  ["secondary_background", "Panels"],
  ["text", "Text"],
];

const section = (title: string, ...children: (HTMLElement | null)[]): HTMLElement => h("section", { class: "app-section" }, h("h3", { class: "app-heading" }, title), ...children);

export function drawSettings(body: HTMLElement, canvas: CanvasView, host: AppHost): void {
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
      { class: `pp-row app-colour${chosen ? "" : " unset"}` },
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
        { class: "pp-row" },
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
export function appPanels(frame: ModeFrame, canvas: () => CanvasView, host: AppHost): { refresh: () => void; rows: () => SessionRow[]; resetState: () => void; inspected: () => Inspected | null } {
  let rows: SessionRow[] = [];
  const pane = canvasPane(canvas, { ...host, drawSettings: (body) => drawSettings(body, canvas(), host) });
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
    pane.setRows(rows);
    frame.redraw("state");
  };
  // What was last drawn: a poll that reads the same draws nothing.
  const drawn = (): string => JSON.stringify([live(), rows]);
  let waitingToShow = false;
  const poll = (): void => {
    if (timer !== null) window.clearTimeout(timer);
    timer = null;
    if (!frame.isOpen("state") && !frame.isOpen("properties")) return;
    if (!live()) return;
    // Nothing is asked while the window is hidden; it goes on when the window shows again.
    if (document.hidden) {
      if (!waitingToShow) {
        waitingToShow = true;
        document.addEventListener("visibilitychange", function shown() {
          if (document.hidden) return;
          document.removeEventListener("visibilitychange", shown);
          waitingToShow = false;
          if (timer === null) poll();
        });
      }
      return;
    }
    timer = window.setTimeout(() => {
      const before = drawn();
      void fetchRows().then(() => {
        timer = null;
        if (drawn() !== before) draw();
        poll();
      });
    }, 1500);
  };
  const resetState = (): void => {
    canvas().resetState();
    rows = [];
    draw();
  };
  frame.add({ id: "properties", title: "Properties", icon: "properties", where: "side", panel: "workbench.properties", draw: (body) => pane.draw(body) });
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
      if (frame.isOpen("properties")) pane.refresh();
      void fetchRows().then(() => {
        draw();
        if (timer === null) poll(); // the live values are followed while either panel shows
      });
    },
    inspected: () => pane.shown(),
    rows: () => rows,
    resetState,
  };
}
