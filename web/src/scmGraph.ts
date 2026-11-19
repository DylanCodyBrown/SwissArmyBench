/*---------------------------------------------------------------------------------------------
 *  Ported from Code - OSS (github.com/microsoft/vscode), src/vs/workbench/contrib/scm/browser/scmHistory.ts.
 *  Copyright (c) Microsoft Corporation. All rights reserved.
 *  Licensed under the MIT License (THIRD_PARTY_NOTICES.md has its text).
 *--------------------------------------------------------------------------------------------*/
/**
 * scmGraph.ts: the Source Control page's graph (the owner, 2026-11-18: "literally clone to exactly no
 * deviation"): VS Code's swimlanes, as its scmHistory.ts draws them (the same sizes, curves, circles and the
 * five lane colours, each a --vscode-* theme colour the page sets), over GitHub's history. [SHARED]
 *
 *   viewModels(rows, refs)  each commit's input and output swimlanes, the colour of a lane named by a ref
 *   graph(model)            one row's SVG: | / \ - lines, the commit's circle (HEAD: a ring; a merge: two)
 */

export const SWIMLANE_HEIGHT = 22;
export const SWIMLANE_WIDTH = 11;
const SWIMLANE_CURVE_RADIUS = 5;
const CIRCLE_RADIUS = 4;
const CIRCLE_STROKE_WIDTH = 2;

/** Colours, as VS Code's colour ids (scmGraph.historyItemRefColor and the rest). */
export const REF_COLOR = "scmGraph-historyItemRefColor";
export const REMOTE_REF_COLOR = "scmGraph-historyItemRemoteRefColor";
const COLORS = ["scmGraph-foreground1", "scmGraph-foreground2", "scmGraph-foreground3", "scmGraph-foreground4", "scmGraph-foreground5"];
export const INCOMING_ID = "scm-graph-incoming-changes";

export interface HistoryItem {
  id: string;
  parentIds: string[];
  subject: string;
  author: string;
  date: string;
  message: string;
  references?: Ref[];
}
export interface Ref {
  id: string;
  name: string;
  kind: "local" | "remote" | "base";
  color?: string;
}
interface Node {
  id: string;
  color: string;
}
export interface ViewModel {
  item: HistoryItem;
  kind: "HEAD" | "node" | "incoming-changes";
  input: Node[];
  output: Node[];
}

const css = (color: string): string => `var(--vscode-${color})`;

function labelColor(item: HistoryItem, colors: Map<string, string | undefined>): string | undefined {
  if (item.id === INCOMING_ID) return REMOTE_REF_COLOR;
  for (const ref of item.references ?? []) {
    const found = colors.get(ref.id);
    if (found !== undefined) return found;
  }
  return undefined;
}

const clone = (nodes: Node[]): Node[] => nodes.map((n) => ({ ...n }));

/** toISCMHistoryItemViewModelArray: each item's swimlanes, in order. */
export function viewModels(items: HistoryItem[], colors: Map<string, string | undefined>, head?: string): ViewModel[] {
  let colorIndex = -1;
  const out: ViewModel[] = [];
  for (const item of items) {
    const kind = item.id === INCOMING_ID ? "incoming-changes" : item.id === head ? "HEAD" : "node";
    const input = clone(out.at(-1)?.output ?? []);
    const output: Node[] = [];
    let firstParentAdded = false;
    if (item.parentIds.length > 0) {
      for (const node of input) {
        if (node.id === item.id) {
          if (!firstParentAdded) {
            output.push({ id: item.parentIds[0]!, color: labelColor(item, colors) ?? node.color });
            firstParentAdded = true;
          }
          continue;
        }
        output.push({ ...node });
      }
    }
    for (let i = firstParentAdded ? 1 : 0; i < item.parentIds.length; i++) {
      let color: string | undefined;
      if (i === 0) color = labelColor(item, colors);
      else {
        const parent = items.find((h) => h.id === item.parentIds[i]);
        color = parent ? labelColor(parent, colors) : undefined;
      }
      if (!color) {
        colorIndex = (colorIndex + 1) % COLORS.length;
        color = COLORS[colorIndex]!;
      }
      output.push({ id: item.parentIds[i]!, color });
    }
    const references = (item.references ?? []).map((ref) => {
      let color = colors.get(ref.id);
      if (colors.has(ref.id) && color === undefined) {
        const at = input.findIndex((n) => n.id === item.id);
        const circle = at !== -1 ? at : input.length;
        color = circle < output.length ? output[circle]!.color : circle < input.length ? input[circle]!.color : REF_COLOR;
      }
      return { ...ref, color };
    });
    out.push({ item: { ...item, references }, kind, input, output });
  }
  return out;
}

function path(color: string, width = 1): SVGPathElement {
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("fill", "none");
  p.setAttribute("stroke-width", `${width}px`);
  p.setAttribute("stroke-linecap", "round");
  p.style.stroke = css(color);
  return p;
}

function circle(index: number, radius: number, width: number, color?: string): SVGCircleElement {
  const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  c.setAttribute("cx", `${SWIMLANE_WIDTH * (index + 1)}`);
  c.setAttribute("cy", `${SWIMLANE_WIDTH}`);
  c.setAttribute("r", `${radius}`);
  c.style.strokeWidth = `${width}px`;
  if (color) c.style.fill = css(color);
  return c;
}

function dashed(index: number, width: number, color: string): SVGCircleElement {
  const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  c.setAttribute("cx", `${SWIMLANE_WIDTH * (index + 1)}`);
  c.setAttribute("cy", `${SWIMLANE_WIDTH}`);
  c.setAttribute("r", `${CIRCLE_RADIUS + 1}`);
  c.style.stroke = css(color);
  c.style.strokeWidth = `${width}px`;
  c.style.strokeDasharray = "4,2";
  return c;
}

function vertical(x: number, y1: number, y2: number, color: string, width = 1): SVGPathElement {
  const p = path(color, width);
  p.setAttribute("d", `M ${x} ${y1} V ${y2}`);
  return p;
}

/** renderSCMHistoryItemGraph: one row's lanes and circle. */
export function graph(model: ViewModel): SVGSVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("graph");
  const { item, input, output } = model;
  const inputIndex = input.findIndex((n) => n.id === item.id);
  const circleIndex = inputIndex !== -1 ? inputIndex : input.length;
  const circleColor = circleIndex < output.length ? output[circleIndex]!.color : circleIndex < input.length ? input[circleIndex]!.color : REF_COLOR;
  let outputIndex = 0;
  for (let index = 0; index < input.length; index++) {
    const color = input[index]!.color;
    if (input[index]!.id === item.id) {
      if (index !== circleIndex) {
        const p = path(color);
        p.setAttribute("d", [`M ${SWIMLANE_WIDTH * (index + 1)} 0`, `A ${SWIMLANE_WIDTH} ${SWIMLANE_WIDTH} 0 0 1 ${SWIMLANE_WIDTH * index} ${SWIMLANE_WIDTH}`, `H ${SWIMLANE_WIDTH * (circleIndex + 1)}`].join(" "));
        svg.append(p);
      } else {
        outputIndex++;
      }
    } else if (outputIndex < output.length && input[index]!.id === output[outputIndex]!.id) {
      if (index === outputIndex) {
        svg.append(vertical(SWIMLANE_WIDTH * (index + 1), 0, SWIMLANE_HEIGHT, color));
      } else {
        const p = path(color);
        p.setAttribute(
          "d",
          [
            `M ${SWIMLANE_WIDTH * (index + 1)} 0`,
            "V 6",
            `A ${SWIMLANE_CURVE_RADIUS} ${SWIMLANE_CURVE_RADIUS} 0 0 1 ${SWIMLANE_WIDTH * (index + 1) - SWIMLANE_CURVE_RADIUS} ${SWIMLANE_HEIGHT / 2}`,
            `H ${SWIMLANE_WIDTH * (outputIndex + 1) + SWIMLANE_CURVE_RADIUS}`,
            `A ${SWIMLANE_CURVE_RADIUS} ${SWIMLANE_CURVE_RADIUS} 0 0 0 ${SWIMLANE_WIDTH * (outputIndex + 1)} ${SWIMLANE_HEIGHT / 2 + SWIMLANE_CURVE_RADIUS}`,
            `V ${SWIMLANE_HEIGHT}`,
          ].join(" "),
        );
        svg.append(p);
      }
      outputIndex++;
    }
  }
  for (let i = 1; i < item.parentIds.length; i++) {
    const at = output.map((n) => n.id).lastIndexOf(item.parentIds[i]!);
    if (at === -1) continue;
    const p = path(output[at]!.color);
    p.setAttribute(
      "d",
      [
        `M ${SWIMLANE_WIDTH * at} ${SWIMLANE_HEIGHT / 2}`,
        `A ${SWIMLANE_WIDTH} ${SWIMLANE_WIDTH} 0 0 1 ${SWIMLANE_WIDTH * (at + 1)} ${SWIMLANE_HEIGHT}`,
        `M ${SWIMLANE_WIDTH * at} ${SWIMLANE_HEIGHT / 2}`,
        `H ${SWIMLANE_WIDTH * (circleIndex + 1)} `,
      ].join(" "),
    );
    svg.append(p);
  }
  if (inputIndex !== -1) svg.append(vertical(SWIMLANE_WIDTH * (circleIndex + 1), 0, SWIMLANE_HEIGHT / 2, input[inputIndex]!.color));
  if (item.parentIds.length > 0) svg.append(vertical(SWIMLANE_WIDTH * (circleIndex + 1), SWIMLANE_HEIGHT / 2, SWIMLANE_HEIGHT, circleColor));
  if (model.kind === "HEAD") {
    svg.append(circle(circleIndex, CIRCLE_RADIUS + 3, CIRCLE_STROKE_WIDTH, circleColor), circle(circleIndex, CIRCLE_STROKE_WIDTH, CIRCLE_RADIUS));
  } else if (model.kind === "incoming-changes") {
    svg.append(
      circle(circleIndex, CIRCLE_RADIUS + 3, CIRCLE_STROKE_WIDTH, circleColor),
      circle(circleIndex, CIRCLE_RADIUS + 1, CIRCLE_STROKE_WIDTH + 1),
      dashed(circleIndex, CIRCLE_STROKE_WIDTH - 1, circleColor),
    );
  } else if (item.parentIds.length > 1) {
    svg.append(circle(circleIndex, CIRCLE_RADIUS + 2, CIRCLE_STROKE_WIDTH, circleColor), circle(circleIndex, CIRCLE_RADIUS - 1, CIRCLE_STROKE_WIDTH, circleColor));
  } else {
    svg.append(circle(circleIndex, CIRCLE_RADIUS + 1, CIRCLE_STROKE_WIDTH, circleColor));
  }
  svg.style.height = `${SWIMLANE_HEIGHT}px`;
  svg.style.width = `${SWIMLANE_WIDTH * (Math.max(input.length, output.length, 1) + 1)}px`;
  svg.dataset.lanes = String(Math.max(input.length, output.length, 1));
  return svg;
}
