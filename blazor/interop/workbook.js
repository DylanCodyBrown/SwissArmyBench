// workbook.js: the Excel canvas's built sheet (Pages/Accounting, the classic excelPreview.ts drawSheet): each chart
// placed over its anchor cell once the table is laid out, and the sheet as tall and wide as its charts reach (they
// hang over the cells, as in Excel).
export function placeCharts(wrap) {
  const table = wrap?.querySelector("table.xc-grid");
  if (!table) {
    return;
  }
  wrap.style.minHeight = "";
  wrap.style.minWidth = "";
  for (const holder of wrap.querySelectorAll(".xc-chart-holder")) {
    const match = /^([A-Z]+)(\d+)$/.exec(holder.dataset.cell ?? "");
    const row = match ? Number(match[2]) : 1;
    const column = match ? [...match[1]].reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0) : 1;
    const rowEl = table.tBodies[0]?.rows[row - 1];
    const headCells = table.tHead?.rows[0]?.cells;
    const left = headCells?.[column]?.offsetLeft ?? 40;
    const top = rowEl?.offsetTop ?? (table.tHead?.offsetHeight ?? 22) + (row - 1) * 22;
    holder.style.left = `${left}px`;
    holder.style.top = `${top}px`;
    wrap.style.minHeight = `${Math.max(wrap.offsetHeight, top + holder.offsetHeight + 8)}px`;
    wrap.style.minWidth = `${Math.max(wrap.offsetWidth, left + holder.offsetWidth + 8)}px`;
  }
}

/** A pointer kept on the board while a block is dragged or sized. */
export function capture(element, pointerId) {
  try {
    element.setPointerCapture(pointerId);
  } catch {
    /* the pointer is gone already */
  }
}

/** The block with this id focused (after the arrow keys moved it and the board drew again). */
export function focusBlock(board, id) {
  board?.querySelector(`.xc-block[data-block="${id}"]`)?.focus();
}

/** Where a menu opens under its button: the button's left and bottom on the screen. */
export function below(element) {
  const r = element.getBoundingClientRect();
  return { x: r.left, y: r.bottom + 2 };
}

/** The browser's own Ctrl+S, Ctrl+Z and Ctrl+Y kept from the page while the canvas has the focus (outside a box):
 * the page's own Save, Undo and Redo hear them; a block's arrows and Space never scroll the board. */
export function guardKeys(element) {
  element.addEventListener("keydown", (e) => {
    if (e.target.closest?.("input, textarea, select")) {
      return;
    }
    if ((e.ctrlKey || e.metaKey) && !e.altKey && ["s", "z", "y"].includes(e.key.toLowerCase())) {
      e.preventDefault();
    }
    // A block's and its corner's keys move and size it: never the board's scroll.
    const own = e.target.classList?.contains("xc-block") || e.target.classList?.contains("xc-grip");
    if (own && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " ", "Backspace"].includes(e.key)) {
      e.preventDefault();
    }
  });
}
