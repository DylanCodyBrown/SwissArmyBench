/**
 * workbenchCellsPane.ts: App mode's Streamlit cells panel (the canvas's own panel since the Data panel
 * became the Data Explorer, 2026-11-17). [WIRE]
 *
 * Every Python cell that calls Streamlit (the owner, 2026-11-15), from the open notebooks and scripts and
 * the project's files, grouped by document, each by its name (else its first comment line), its @cell and
 * what it makes and reads; then, under Text, the Markdown and HTML cells, which go on a page too. A drag
 * places its link on a canvas (as dragging the cell itself does); a click goes to the cell. A cell already
 * on the canvas page in front has a mark. One element, shown in the App panel of the canvas in front.
 */
import { type Kind, kindIcon, kindOfPath } from "./kindColours";
import { h, icon } from "./dom";
import { CELL_DRAG, type PaneCell, type PaneDocument, partsOf } from "./workbenchStreamlit";

export interface CellsPane {
  element: HTMLElement;
  /** Its documents and cells, and the links on the canvas page in front ("path#cell"), which get a mark. */
  set: (documents: PaneDocument[], placed: Set<string>) => void;
  /** How many cells it lists. */
  count: () => number;
}

/** A pane document's kind (its file's, else a notebook: an unsaved script says so by its title). */
const sourceKind = (d: PaneDocument): Kind => kindOfPath(d.document ?? d.title) ?? "notebook";

export function cellsPane(goToCell: (document: string | null, title: string, cell: number) => void): CellsPane {
  let docs: PaneDocument[] = [];
  let placed = new Set<string>();
  const list = h("div", { class: "wb-st-list" });
  const element = h("section", { class: "wb-data-section wb-st", "data-panel": "streamlit", "aria-label": "Streamlit cells" }, list);

  const item = (d: PaneDocument, c: PaneCell): HTMLElement => {
    const on = d.document !== null && placed.has(`${d.document}#${c.cell}`);
    const parts = partsOf(c);
    const text = c.kind === "markdown" || c.kind === "html";
    const kind = c.kind === "markdown" ? "A Markdown cell" : "An HTML cell";
    return h(
      "li",
      { class: "wb-data-item" },
      h(
        "button",
        {
          type: "button",
          class: `wb-data-card wb-st-cell${on ? " placed" : ""}${c.named ? " named" : ""}${text ? ` text kind-${c.kind}` : ""}`,
          title: `Go to ${c.where}${text ? ` (${kind.toLowerCase()})` : ""}`,
          draggable: "true",
          dataset: { document: d.document ?? "", cell: String(c.cell) },
          onclick: () => goToCell(d.document, d.title, c.cell),
          ondragstart: (event: DragEvent) => {
            // The same link a cell's own drag carries: a canvas places it.
            event.dataTransfer?.setData(CELL_DRAG, JSON.stringify({ document: d.document, cell: c.cell, title: d.title }));
            event.dataTransfer?.setData("text/plain", `@cell${c.cell}`);
            if (event.dataTransfer) event.dataTransfer.effectAllowed = "copyLink";
          },
        },
        h(
          "span",
          { class: "wb-data-name" },
          text ? h("span", { class: "wb-st-t", title: kind, "aria-label": kind }, "T") : null,
          h("span", { class: "wb-data-label" }, c.name),
          on ? h("span", { class: "wb-st-placed", title: "On the canvas page in front", "aria-label": "On the canvas page in front" }, icon("check")) : null,
        ),
        // Its source document's kind colour and icon beside the @cell (notebook blue, script green).
        h("span", { class: "wb-data-meta" }, h("span", { class: "wb-st-where" }, icon(kindIcon(sourceKind(d), d.document)), `@cell${c.cell}`), parts ? h("span", {}, parts) : null),
      ),
    );
  };

  function draw(): void {
    list.replaceChildren(
      ...docs.map((d) => {
        const live = d.cells.filter((c) => c.kind !== "markdown" && c.kind !== "html");
        const texts = d.cells.filter((c) => c.kind === "markdown" || c.kind === "html");
        return h(
          "div",
          { class: `wb-st-doc km-${sourceKind(d)}` },
          h("div", { class: "wb-st-doc-name", title: d.document ?? d.title }, icon(kindIcon(sourceKind(d), d.document)), h("span", {}, d.title)),
          live.length ? h("ul", { class: "wb-data-list", "aria-label": d.title }, ...live.map((c) => item(d, c))) : null,
          texts.length ? h("div", { class: "wb-st-text-head" }, "Text") : null,
          texts.length ? h("ul", { class: "wb-data-list wb-st-texts", "aria-label": `${d.title}: text` }, ...texts.map((c) => item(d, c))) : null,
        );
      }),
    );
    if (!docs.length) list.append(h("p", { class: "wb-data-empty" }, "No cells call Streamlit"));
  }
  draw();

  return {
    element,
    set: (documents, onPage) => {
      docs = documents;
      placed = onPage;
      draw();
    },
    count: () => docs.reduce((n, d) => n + d.cells.length, 0),
  };
}
