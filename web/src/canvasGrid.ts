/**
 * canvasGrid.ts: the Canvas's placement maths (the owner, 2026-11-21: "should be able to turn on snap to",
 * "with a very fine precision", "finer than the precision I see in this mockup"). Pure: rectangles in pixels of
 * the page (the canvas file's own units), nothing here touches the page. [SHARED]
 *
 *   gridLines   the column lines of a box (each column's left and right edge), as domain/canvas_model.py lines
 *   snapRect    a rectangle being drawn, moved or sized, put on the step (1, 2, 4, 8 px, or the grid's cells),
 *               then onto another item's edge or centre when one is within `tolerance` (canvasSnap.ts's
 *               snaplines, with the guides to draw); snap off: whole pixels only
 *   nudgeBy     an arrow key's step: the snap step, ten of them with Shift, one pixel with Alt
 *   dotSpacing  the visible dots: the step, doubled until they are at least 12 screen pixels apart
 */
import { type Guide, guides, type Rect, snapped } from "./canvasSnap";

export type Step = 1 | 2 | 4 | 8 | "grid";

export interface Grid {
  columns: number;
  rowHeight: number;
  gap: number;
  /** The box's width the columns divide (the page's, or a container's). */
  width: number;
}

export function gridLines(width: number, columns: number, gap: number): number[] {
  const column = Math.max(1, (width - (columns - 1) * gap) / columns);
  const found: number[] = [];
  for (let i = 0; i < columns; i++) {
    const left = i * (column + gap);
    found.push(left, left + column);
  }
  return found;
}

const nearest = (value: number, lines: number[]): number => lines.reduce((best, line) => (Math.abs(line - value) < Math.abs(best - value) ? line : best), lines[0] ?? value);

function rowLines(grid: Grid, upTo: number): number[] {
  const found: number[] = [0];
  for (let y = 0; y <= upTo + grid.rowHeight * 2; y += grid.rowHeight + grid.gap) found.push(y, y + grid.rowHeight);
  return found;
}

export interface Snap {
  on: boolean;
  step: Step;
  grid: Grid;
  /** The other items beside it (its siblings), for the edges and centres. */
  others: Rect[];
  /** In page pixels: about 4 screen pixels at the zoom. */
  tolerance: number;
  /** Sizing keeps the left and top edge where they are. */
  sizing?: boolean;
}

/** The rectangle on the step and the guides to draw. */
export function snapRect(rect: Rect, snap: Snap): { rect: Rect; guides: Guide[] } {
  let { left, top, width, height } = rect;
  if (!snap.on) {
    return { rect: { ...rect, left: Math.round(left), top: Math.round(top), width: Math.max(1, Math.round(width)), height: Math.max(1, Math.round(height)) }, guides: [] };
  }
  if (snap.step === "grid") {
    const columns = gridLines(snap.grid.width, snap.grid.columns, snap.grid.gap);
    const rows = rowLines(snap.grid, top + height);
    if (snap.sizing) {
      width = nearest(left + width, columns) - left;
      height = nearest(top + height, rows) - top;
    } else {
      left = nearest(left, columns);
      top = nearest(top, rows);
    }
  } else {
    const step = snap.step;
    const on = (v: number): number => Math.round(v / step) * step;
    if (snap.sizing) {
      width = on(left + width) - left;
      height = on(top + height) - top;
    } else {
      left = on(left);
      top = on(top);
    }
  }
  let made: Rect = { ...rect, left: Math.round(left), top: Math.round(top), width: Math.max(1, Math.round(width)), height: Math.max(1, Math.round(height)) };
  // Another item's edge or centre within the tolerance wins over the step (moving only: a size keeps its corner).
  if (!snap.sizing && snap.others.length) {
    const near = snapped(made, snap.others, snap.tolerance);
    made = { ...made, left: Math.round(near.left), top: Math.round(near.top) };
  }
  return { rect: made, guides: guides(made, snap.others, 0.5) };
}

/** How far an arrow key moves the selection. */
export function nudgeBy(step: Step, keys: { shiftKey: boolean; altKey: boolean }, grid: Grid): number {
  if (keys.altKey) return 1;
  const one = step === "grid" ? Math.round(Math.max(1, (grid.width - (grid.columns - 1) * grid.gap) / grid.columns) + grid.gap) : step;
  return keys.shiftKey ? one * 10 : one;
}

/** The dots' spacing in page pixels: the step, doubled until they are 12 screen pixels apart at the zoom. */
export function dotSpacing(step: Step, zoom: number): number {
  let spacing = step === "grid" ? 8 : step;
  while (spacing * zoom < 12) spacing *= 2;
  return spacing;
}
