/**
 * canvasSnap.ts: the designer's snaplines (the owner, 2026-11-19: "Snaplines and alignment like WinForms"):
 * while a block is dragged or sized, a guide wherever one of its edges or its centre lines up with another
 * block's, and a marker where the gaps between the blocks of a row are equal. Pure maths over rectangles
 * (pixels of the board): nothing here touches the page. [SHARED]
 *
 *   guides       the lines to draw for a moving rectangle against the others: vertical where a left edge, a
 *                right edge or a centre matches (within `tolerance`), horizontal where a top, a bottom or a
 *                middle does; each line spans the rectangles it joins
 *   snapped      the moving rectangle nudged onto the nearest guide (at most `tolerance` away), per axis
 *   equalGaps    the gaps of a row that are equal to another (the row sorted by its left edges), as the
 *                spans to mark
 *   sameSize     the others as wide, or as tall, as the moving one (a sizing drag says so)
 *   inBand       the rectangles a rubber band touches
 */

export interface Rect {
  id: string;
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface Guide {
  /** "v": a vertical line at x = at; "h": a horizontal line at y = at. */
  axis: "v" | "h";
  at: number;
  /** Where the line starts and ends along the other axis: over the moving block and what it matches. */
  from: number;
  to: number;
  /** Which of the moving block's lines it is. */
  edge: "left" | "right" | "centre" | "top" | "bottom" | "middle";
  /** The blocks it lines up with. */
  with: string[];
}

const right = (r: Rect): number => r.left + r.width;
const bottom = (r: Rect): number => r.top + r.height;

function lines(r: Rect, axis: "v" | "h"): [Guide["edge"], number][] {
  return axis === "v"
    ? [["left", r.left], ["centre", r.left + r.width / 2], ["right", right(r)]]
    : [["top", r.top], ["middle", r.top + r.height / 2], ["bottom", bottom(r)]];
}

/** The guides of `moving` against `others` (itself left out): one line for each of its lines that matches. */
export function guides(moving: Rect, others: Rect[], tolerance = 1): Guide[] {
  const found: Guide[] = [];
  for (const axis of ["v", "h"] as const) {
    for (const [edge, at] of lines(moving, axis)) {
      const matched = others.filter((o) => o.id !== moving.id && lines(o, axis).some(([kind, value]) => Math.abs(value - at) <= tolerance && (kind === "centre" || kind === "middle") === (edge === "centre" || edge === "middle")));
      if (!matched.length) continue;
      const all = [moving, ...matched];
      const from = Math.min(...all.map((r) => (axis === "v" ? r.top : r.left)));
      const to = Math.max(...all.map((r) => (axis === "v" ? bottom(r) : right(r))));
      found.push({ axis, at, from, to, edge, with: matched.map((m) => m.id) });
    }
  }
  return found;
}

/** `moving` moved onto the nearest line of another block, per axis, when one is within `tolerance`. */
export function snapped(moving: Rect, others: Rect[], tolerance = 6): Rect {
  const shift = (axis: "v" | "h"): number => {
    let best = 0;
    let far = tolerance + 1;
    for (const [edge, at] of lines(moving, axis)) {
      for (const other of others) {
        if (other.id === moving.id) continue;
        for (const [kind, value] of lines(other, axis)) {
          if ((kind === "centre" || kind === "middle") !== (edge === "centre" || edge === "middle")) continue;
          const gap = Math.abs(value - at);
          if (gap < far) {
            far = gap;
            best = value - at;
          }
        }
      }
    }
    return far <= tolerance ? best : 0;
  };
  return { ...moving, left: moving.left + shift("v"), top: moving.top + shift("h") };
}

export interface Gap {
  from: number;
  to: number;
  /** The row's vertical middle, where the marker is drawn. */
  y: number;
}

/** The equal gaps of a row: every gap between neighbours that at least one other gap matches (the
 *  rectangles sorted by their left edges; overlapping ones have no gap). */
export function equalGaps(row: Rect[], tolerance = 1): Gap[] {
  const sorted = [...row].sort((a, b) => a.left - b.left);
  const gaps: Gap[] = [];
  for (let i = 1; i < sorted.length; i++) {
    const before = sorted[i - 1]!;
    const after = sorted[i]!;
    if (after.left - right(before) <= tolerance) continue;
    gaps.push({ from: right(before), to: after.left, y: (Math.max(before.top, after.top) + Math.min(bottom(before), bottom(after))) / 2 });
  }
  return gaps.filter((g, i) => gaps.some((o, j) => j !== i && Math.abs(o.to - o.from - (g.to - g.from)) <= tolerance));
}

/** The others as wide (or as tall) as `moving`: a sizing drag marks them. */
export function sameSize(moving: Rect, others: Rect[], tolerance = 1): { width: string[]; height: string[] } {
  const rest = others.filter((o) => o.id !== moving.id);
  return {
    width: rest.filter((o) => Math.abs(o.width - moving.width) <= tolerance).map((o) => o.id),
    height: rest.filter((o) => Math.abs(o.height - moving.height) <= tolerance).map((o) => o.id),
  };
}

/** The rectangles a rubber band (dragged from one corner to another) touches. */
export function inBand(band: { x1: number; y1: number; x2: number; y2: number }, rects: Rect[]): string[] {
  const left = Math.min(band.x1, band.x2);
  const top = Math.min(band.y1, band.y2);
  const r = Math.max(band.x1, band.x2);
  const b = Math.max(band.y1, band.y2);
  return rects.filter((o) => o.left < r && right(o) > left && o.top < b && bottom(o) > top).map((o) => o.id);
}
