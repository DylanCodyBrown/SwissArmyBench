/**
 * workbenchDocPanels.ts: the Workbench's modes (2026-11-15): each document's own panels sit beside it in its
 * group (workbenchModes.ts), so they follow the group; the status bar's toggles are the focused document's.
 * Moved out of workbenchPage.ts along its own heading (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [NOTEBOOK]  the run order (edited, out of date), the Outline, Present
 *   [SCRIPT]    Run settings (its arguments for Run file); API.py: its Endpoints
 *   [DATA]      data.ipynb: Cells | Lineage | Dictionary (its descriptions kept in the notebook)
 *   [TOGGLES]   the status bar's mode toggles, and a group's view switch
 */
import { button, clear, h } from "./dom";
import { errorNote } from "./errorNote";
import { type Descriptions, type DictionaryTable, described, drawDictionary, drawOutline, drawRunSettings, type FlowState, type OutlineItem, readDictionary, readFlow, runSettings } from "./workbenchDocModes";
import { closePlacedLineage } from "./workbenchLineage";
import { modeFrame } from "./workbenchModes";
import type { Doc } from "./workbenchPage";
import type { TableInfo } from "./workbenchTables";

/** What the panels ask of the page: its documents and the one in front, its redraws, which document is the
 *  project's data.ipynb or API.py, a document marked changed, the Lineage view drawn, the Data Explorer's
 *  pane (closed while a notebook is presented), the open tables and the key vaults' names. */
export interface PanelsHost {
  docs: Doc[];
  readonly current: Doc | null;
  drawStatus: () => void;
  drawControls: () => void;
  isData: (doc: Doc) => boolean;
  isApiFile: (doc: Doc | null) => boolean;
  markChanged: (doc: Doc) => () => void;
  dataLineage: (doc: Doc, into: HTMLElement) => Promise<unknown>;
  explorer: { isOpen: () => boolean; toggle: (on: boolean) => void };
  readonly tables: TableInfo[];
  readonly vaultNames: string[];
}

export function documentPanels(host: PanelsHost) {
  const { docs, drawStatus, drawControls, isData, isApiFile, markChanged, dataLineage } = host;

  interface Flow {
    cells: FlowState[];
    outline: OutlineItem[];
  }
  const flows = new Map<Doc, Flow>();
  const flowTimers = new Map<Doc, number>();

  function flowSoon(doc: Doc): void {
    if (!doc.notebook) return;
    const was = flowTimers.get(doc);
    if (was !== undefined) window.clearTimeout(was);
    flowTimers.set(doc, window.setTimeout(() => {
      flowTimers.delete(doc);
      void refreshFlow(doc);
    }, 300));
  }

  async function refreshFlow(doc: Doc): Promise<Flow | null> {
    if (!doc.notebook || !docs.includes(doc)) return null;
    try {
      const read = await readFlow(doc.notebook.flowCells());
      flows.set(doc, read);
      doc.notebook.markFlow(read.cells);
      doc.modes?.redraw("outline");
      return read;
    } catch {
      return null;
    }
  }

  function notebookModes(doc: Doc): void {
    doc.modes = modeFrame(doc.element, () => doc === host.current && drawStatus());
    doc.modes.add({
      id: "outline",
      title: "Outline",
      icon: "outline",
      where: "side",
      draw: (body) => {
        const flow = flows.get(doc);
        const view = doc.notebook!;
        const at = view.selected();
        const selectedNumber = at >= 0 ? (view.cells()[at]?.number ?? null) : null;
        drawOutline(body, flow?.outline ?? [], flow?.cells ?? [], selectedNumber, view.tables().length > 0, (n) => void view.goTo(n), () => {
          view.foldTables(false);
          const first = view.cells().find((c) => c.role === "host.tables");
          if (first?.number) view.goTo(first.number);
        });
      },
    });
    void refreshFlow(doc);
  }

  /** Present: the notebook as a document, the Data Explorer closed while it shows. */
  let openBeforePresent: boolean | null = null;
  function present(doc: Doc, on?: boolean): boolean {
    const now = doc.notebook!.present(on);
    doc.element.classList.toggle("presenting", now);
    if (now && openBeforePresent === null) {
      openBeforePresent = host.explorer.isOpen();
      if (openBeforePresent) host.explorer.toggle(false);
    } else if (!now && openBeforePresent !== null) {
      if (openBeforePresent) host.explorer.toggle(true);
      openBeforePresent = null;
    }
    drawControls();
    return now;
  }

  // ----- Script mode: run settings

  function scriptModes(doc: Doc): void {
    doc.modes = modeFrame(doc.element, () => doc === host.current && drawStatus());
    if (isApiFile(doc)) {
      // API.py: its endpoints beside the code, Try it there (closed until asked for: design principle 8.14). Its
      // Run is Run API, so it has no run settings or history of a script's.
      doc.modes.add({ id: "endpoints", title: "Endpoints", icon: "play", where: "side", draw: (body) => void import("./localApis").then((m) => m.endpointsPane(body)) });
      return;
    }
    doc.modes.add({ id: "runSettings", title: "Run settings", icon: "sliders", where: "side", draw: (body) => drawRunSettings(body, doc.path, host.vaultNames, () => void readArguments(doc)) });
  }

  const scriptArguments = new Map<Doc, string>();

  /** The run settings' arguments, for Run file (read when the script opens and when its settings change). */
  async function readArguments(doc: Doc): Promise<void> {
    if (!doc.path) return;
    try {
      scriptArguments.set(doc, (await runSettings(doc.path)).arguments);
    } catch {
      /* a script that cannot be read: no arguments */
    }
  }

  // ----- Data mode (data.ipynb): Cells | Lineage | Dictionary

  type DataView = "cells" | "lineage" | "dictionary";
  const dataViews = new Map<Doc, { view: DataView; host: HTMLElement; chosen: { table: string | null }; dictionary: Descriptions }>();

  /** What data.ipynb saves beside its cells: its data dictionary's descriptions. */
  function dataBody(doc: Doc): { dictionary?: Descriptions } {
    const held = dataViews.get(doc);
    return held && isData(doc) ? { dictionary: held.dictionary } : {};
  }

  function dataMode(doc: Doc, dictionary: Descriptions): void {
    const host = h("div", { class: "wb-data-view", hidden: true });
    doc.element.append(host);
    dataViews.set(doc, { view: "cells", host, chosen: { table: null }, dictionary });
  }

  function setDataView(doc: Doc, view: DataView): DataView {
    const held = dataViews.get(doc);
    if (!held || !doc.notebook) throw new Error("The document in front is not a project's data.ipynb.");
    held.view = view;
    doc.notebook.element.hidden = view !== "cells";
    held.host.hidden = view === "cells";
    doc.element.classList.toggle("data-view", view !== "cells");
    if (view !== "lineage") closePlacedLineage();
    if (view === "dictionary") void drawDictionaryView(doc);
    else if (view === "lineage") void dataLineage(doc, held.host).catch(() => undefined);
    drawControls();
    return view;
  }

  async function dictionaryTables(doc: Doc): Promise<DictionaryTable[]> {
    const held = dataViews.get(doc)!;
    const named = doc.notebook!.tables().map((t) => ({ name: t.name, source: host.tables.find((i) => i.name === t.name)?.source ?? "" }));
    return readDictionary(named, held.dictionary);
  }

  async function drawDictionaryView(doc: Doc): Promise<void> {
    const held = dataViews.get(doc);
    if (!held || held.view !== "dictionary") return;
    try {
      const found = await dictionaryTables(doc);
      drawDictionary(held.host, found, held.chosen, (table, column, text) => describe(doc, table, column, text));
    } catch (e) {
      clear(held.host, errorNote(e, { dismiss: false }));
    }
  }

  /** A description typed in the Dictionary (or sent by the agent): kept in data.ipynb (unsaved until
   *  Save), and data.py's next export carries it. */
  function describe(doc: Doc, table: string, column: string | null, text: string): Descriptions {
    const held = dataViews.get(doc);
    if (!held) throw new Error("The document in front is not a project's data.ipynb.");
    held.dictionary = described(held.dictionary, table, column, text);
    markChanged(doc)();
    return held.dictionary;
  }

  // ----- the status bar's mode toggles, and a group's mode switches

  const modeToggles = h("span", { class: "wb-mode-toggles" });

  function drawModeToggles(doc: Doc | null): void {
    const panels = doc?.modes?.panels() ?? [];
    clear(
      modeToggles,
      ...panels.map((p) =>
        button(p.label ?? p.title, () => {
          doc!.modes!.toggle(p.id);
          drawStatus();
        }, { class: `ghost wb-toggle wb-mode-toggle-${p.id}`, pressed: doc!.modes!.isOpen(p.id) }),
      ),
    );
  }

  /** A notebook's Cells | Present switch; data.ipynb's Cells | Lineage | Dictionary. */
  function modeSwitch(doc: Doc): HTMLElement | null {
    if (!doc.notebook) return null;
    const pick = (label: string, ic: string, on: boolean, run: () => void): HTMLButtonElement => button(label, run, { icon: ic, pressed: on, class: `wb-view-${label.toLowerCase()}` });
    const held = dataViews.get(doc);
    if (held && isData(doc)) {
      return h(
        "span",
        { class: "cv-mode wb-view-switch", role: "group", "aria-label": "View" },
        pick("Cells", "notebook", held.view === "cells", () => void setDataView(doc, "cells")),
        pick("Lineage", "lineage", held.view === "lineage", () => void setDataView(doc, "lineage")),
        pick("Dictionary", "book", held.view === "dictionary", () => void setDataView(doc, "dictionary")),
      );
    }
    const presenting = doc.element.classList.contains("presenting");
    return h(
      "span",
      { class: "cv-mode wb-view-switch", role: "group", "aria-label": "View" },
      pick("Cells", "notebook", !presenting, () => void present(doc, false)),
      pick("Present", "eye", presenting, () => void present(doc, true)),
    );
  }

  return { flows, flowSoon, refreshFlow, notebookModes, present, scriptModes, scriptArguments, readArguments, dataViews, dataBody, dataMode, setDataView, dictionaryTables, drawDictionaryView, describe, modeToggles, drawModeToggles, modeSwitch };
}
