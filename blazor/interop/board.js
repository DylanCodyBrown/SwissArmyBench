// board.js: the Analyze board's moves (the classic aiPanel.ts and sandboxPages.ts): a card's corner grip dragged to
// its size on the twelve-column board, a card dragged by its head to another place, its drawings as pictures (the
// markdown export), a file saved, and the page printed.

const COLUMNS = 12;

/** The corner grip: dragged, the card's width in columns and height in rows go to C# when it ends (Resized). */
export function grip(element, dotnet, rowHeight, gap) {
  element.addEventListener("pointerdown", (down) => {
    const card = element.closest(".board-card");
    const board = card?.parentElement;
    if (!card || !board) return;
    down.preventDefault();
    element.setPointerCapture(down.pointerId);
    const box = card.getBoundingClientRect();
    const column = (board.clientWidth - gap * (COLUMNS - 1)) / COLUMNS;
    let w = 0;
    let h = 0;
    const move = (event) => {
      w = Math.max(2, Math.min(COLUMNS, Math.round((event.clientX - box.left + gap) / (column + gap))));
      h = Math.max(3, Math.min(30, Math.round((event.clientY - box.top + gap) / (rowHeight + gap))));
      card.style.gridColumn = `span ${w}`;
      card.style.height = `${h * rowHeight + (h - 1) * gap}px`;
    };
    const up = () => {
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", up);
      if (w && h) dotnet.invokeMethodAsync("Resized", w, h).catch(() => {});
    };
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", up);
  });
}

/** A card dragged by its head: dropped on another card, it goes before it (or after it, past its middle). */
export function movable(head, dotnet) {
  head.addEventListener("pointerdown", (down) => {
    if (down.button !== 0 || down.target.closest("button, a, select, input")) return;
    const card = head.closest(".board-card");
    if (!card) return;
    let moved = false;
    const move = (event) => {
      if (!moved && Math.hypot(event.clientX - down.clientX, event.clientY - down.clientY) < 6) return;
      moved = true;
      card.classList.add("moving");
    };
    const up = (event) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      card.classList.remove("moving");
      if (!moved) return;
      const target = document.elementsFromPoint(event.clientX, event.clientY).map((e) => e.closest?.(".board-card[data-card]")).find((e) => e && e !== card);
      if (!target) return;
      const box = target.getBoundingClientRect();
      const after = event.clientX > box.left + box.width / 2;
      const next = after ? target.nextElementSibling?.closest?.(".board-card[data-card]") ?? null : target;
      const before = next === card ? null : next?.dataset.card ?? null;
      dotnet.invokeMethodAsync("Moved", before ?? "").catch(() => {});
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
}

/** Each drawn card's picture by its id: a Plotly figure's PNG, a diagram's SVG (as the classic markdown keeps it). */
export async function pictures(board) {
  const out = {};
  for (const card of board.querySelectorAll(".board-card[data-card]")) {
    const id = card.dataset.card;
    const plot = card.querySelector(".js-plotly-plot");
    const image = card.querySelector("img.card-image");
    const svg = card.querySelector(".mermaid-host svg, svg.mermaid, .vega-host svg");
    if (plot && window.Plotly?.toImage) out[id] = await window.Plotly.toImage(plot, { format: "png", scale: 2 }).catch(() => null);
    else if (image) out[id] = image.src;
    else if (svg) out[id] = `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(new XMLSerializer().serializeToString(svg))))}`;
  }
  return out;
}

/** Text saved as a file by the browser's own download. */
export function save(text, name, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** The page printed (the board in Page view; the browser's dialog saves it as a PDF). */
export function print(paperCss) {
  const style = document.createElement("style");
  style.textContent = `@page { size: ${paperCss}; margin: 0.5in; }`;
  document.head.append(style);
  document.body.classList.add("printing-board");
  const done = () => {
    style.remove();
    document.body.classList.remove("printing-board");
    window.removeEventListener("afterprint", done);
  };
  window.addEventListener("afterprint", done);
  window.print();
}

/** Show: a card brought into view (the board's own scroll) and marked as it lands. */
export function reveal(board, id) {
  const card = board?.querySelector(`.board-card[data-card="${CSS.escape(id)}"]`);
  card?.scrollIntoView({ block: "start", behavior: "auto" });
  return Boolean(card);
}
