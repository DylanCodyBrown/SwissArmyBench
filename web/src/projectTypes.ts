/**
 * projectTypes.ts: the project types explained for beginners (the owner, 2026-11-17: "explanations of project
 * types for beginners"), shared by the Project Explorer's strip and New project's chooser. [VIEW]
 *
 * The words are the backend's (each mode's title, for whom, what you get, an example: an extension brings
 * its own); the small pictures of each deliverable are drawn here, our own, no brand's logo. A type this
 * page has no picture for gets a plain one.
 *
 * ROUTING: GET /projects/types
 */
import { api } from "./api";
import { button, h } from "./dom";

export interface ProjectType {
  type: string;
  name: string;
  title: string;
  for_whom: string;
  explain: string;
  example: string;
  deliverable: string;
  make: Record<string, unknown>;
}

let cached: Promise<ProjectType[]> | null = null;

export function projectTypes(fresh = false): Promise<ProjectType[]> {
  if (fresh || !cached) cached = api<{ types: ProjectType[] }>("/projects/types").then((r) => r.types).catch(() => []);
  return cached;
}

const SVG = "http://www.w3.org/2000/svg";

function svg(tag: string, attrs: Record<string, string | number>, ...children: SVGElement[]): SVGElement {
  const element = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, String(value));
  element.append(...children);
  return element;
}

const line = (x1: number, y1: number, x2: number, y2: number, cls = "pt-ink"): SVGElement => svg("line", { x1, y1, x2, y2, class: cls });
const rect = (x: number, y: number, w: number, hh: number, cls = "pt-ink", rx = 2): SVGElement => svg("rect", { x, y, width: w, height: hh, rx, class: cls });

/** A small drawing of what a type makes: a notebook and a chart, an app's page, a workbook, a phone app. */
export function typePicture(kind: string): SVGElement {
  const parts: SVGElement[] = [];
  if (kind === "bi") {
    // A notebook page with cells, and a bar chart beside it.
    parts.push(rect(6, 8, 40, 48, "pt-paper"), line(12, 18, 40, 18), line(12, 24, 34, 24), rect(12, 30, 28, 10, "pt-soft"), line(12, 46, 38, 46));
    parts.push(rect(52, 16, 42, 40, "pt-paper"), rect(58, 40, 6, 10, "pt-accent", 1), rect(68, 32, 6, 18, "pt-accent", 1), rect(78, 24, 6, 26, "pt-accent", 1), line(56, 50, 90, 50));
  } else if (kind === "streamlit") {
    // A browser window with a side bar of filters and a chart.
    parts.push(rect(6, 8, 88, 48, "pt-paper"), line(6, 16, 94, 16), svg("circle", { cx: 11, cy: 12, r: 1.5, class: "pt-accent-fill" }));
    parts.push(rect(10, 20, 20, 32, "pt-soft"), line(13, 26, 27, 26), line(13, 32, 27, 32), line(13, 38, 24, 38));
    parts.push(svg("polyline", { points: "36,46 46,36 56,40 66,28 76,32 88,22", class: "pt-accent-line" }), line(36, 50, 90, 50));
  } else if (kind === "accounting") {
    // A workbook: a grid of cells, a header row, a sheet tab.
    parts.push(rect(8, 8, 84, 44, "pt-paper"), rect(8, 8, 84, 8, "pt-soft", 2));
    for (let x = 28; x < 92; x += 20) parts.push(line(x, 8, x, 52));
    for (let y = 24; y < 52; y += 8) parts.push(line(8, y, 92, y));
    parts.push(rect(10, 52, 18, 6, "pt-accent", 1), rect(30, 52, 18, 6, "pt-soft", 1));
  } else if (kind === "codeapp") {
    // A phone with an app's list and a button.
    parts.push(rect(34, 4, 32, 56, "pt-paper", 5), line(44, 9, 56, 9), rect(38, 14, 24, 6, "pt-soft", 1), rect(38, 23, 24, 6, "pt-soft", 1), rect(38, 32, 24, 6, "pt-soft", 1), rect(42, 46, 16, 7, "pt-accent", 3));
  } else {
    parts.push(rect(20, 8, 60, 48, "pt-paper"), line(28, 20, 72, 20), line(28, 28, 64, 28), line(28, 36, 68, 36));
  }
  return svg("svg", { viewBox: "0 0 100 64", class: "pt-picture", role: "img", "aria-hidden": "true" }, ...parts);
}

/** A type's card: its picture, its words, and Create. */
export function typeCard(t: ProjectType, create: (t: ProjectType) => void, large = false): HTMLElement {
  return h(
    "article",
    { class: `pt-card${large ? " large" : ""}`, "data-type": t.type },
    h("div", { class: "pt-figure" }, typePicture(t.type)),
    h("h3", {}, t.title || t.name),
    t.for_whom ? h("p", { class: "pt-for" }, t.for_whom) : null,
    t.explain ? h("p", { class: "pt-explain" }, t.explain) : null,
    t.example ? h("p", { class: "pt-example" }, t.example) : null,
    button(`Create ${t.title || t.name}`, () => create(t), { icon: "plus", class: "primary pt-create" }),
  );
}
