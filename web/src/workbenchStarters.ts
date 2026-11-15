/**
 * workbenchStarters.ts: App mode's starter gallery (the Workbench's modes, 2026-11-15), in the Data
 * panel's Starters: the real Streamlit starters of the starter pack, in their own families (Filters,
 * Displays, Layout, Interaction, Feedback), each a card with a small sketch of what it draws. [WIRE]
 *
 * Drag one onto a canvas (or click it: the end of the page in front): it is filled (its form asks for
 * the table and the column), written as a real named cell of the project's mockups notebook, and that
 * cell is placed as a block. Never called "pieces" on screen: they are cells once dropped.
 *
 * ROUTING: GET /blades/starters (starters.ts)
 */
import { clear, h, icon } from "./dom";
import { starters, type StarterSummary } from "./starters";
import { STARTER_DRAG } from "./workbenchCanvas";

/** The families, by a starter's second tag, in the gallery's order. */
const FAMILIES: [string, string][] = [
  ["filter", "Filters"],
  ["display", "Displays"],
  ["layout", "Layout"],
  ["interaction", "Interaction"],
  ["feedback", "Feedback"],
];

/** A starter's short name on its card: "Streamlit selectbox filter" -> "Selectbox filter". */
export const cardName = (name: string): string => {
  const bare = name.replace(/^Streamlit\s+/i, "");
  return bare.charAt(0).toUpperCase() + bare.slice(1);
};

/** A small sketch of what a starter draws (by its name's words). Fixed markup. */
function sketch(name: string): SVGSVGElement {
  const n = name.toLowerCase();
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 96 48");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("wb-starter-sketch");
  const shapes: Record<string, string> = {
    bar: '<rect x="18" y="26" width="10" height="14"/><rect x="32" y="16" width="10" height="24"/><rect x="46" y="20" width="10" height="20"/><rect x="60" y="10" width="10" height="30"/><path d="M12 41h72" class="line"/>',
    line: '<path d="M12 36l16-10 14 6 18-16 22 8" class="line" fill="none"/><path d="M12 41h72" class="line"/>',
    area: '<path d="M12 40V30l16-10 14 6 18-14 22 8v20z"/>',
    table: '<rect x="12" y="8" width="72" height="32" rx="2" class="frame"/><path d="M12 16h72M12 24h72M12 32h72M36 8v32M60 8v32" class="line"/>',
    metric: '<rect x="14" y="10" width="30" height="5" rx="2"/><rect x="14" y="20" width="52" height="14" rx="2"/>',
    map: '<rect x="12" y="8" width="72" height="32" rx="2" class="frame"/><circle cx="34" cy="22" r="3"/><circle cx="58" cy="28" r="3"/><circle cx="66" cy="16" r="3"/>',
    progress: '<rect x="12" y="20" width="72" height="8" rx="4" class="frame"/><rect x="12" y="20" width="44" height="8" rx="4"/>',
    select: '<rect x="12" y="8" width="26" height="4" rx="2"/><rect x="12" y="16" width="72" height="16" rx="3" class="frame"/><path d="M72 22l4 4 4-4" class="line" fill="none"/>',
    date: '<rect x="12" y="8" width="26" height="4" rx="2"/><rect x="12" y="16" width="32" height="16" rx="3" class="frame"/><rect x="52" y="16" width="32" height="16" rx="3" class="frame"/>',
    slider: '<rect x="12" y="8" width="26" height="4" rx="2"/><path d="M12 28h72" class="line"/><circle cx="54" cy="28" r="5"/>',
    multi: '<rect x="12" y="8" width="26" height="4" rx="2"/><rect x="12" y="16" width="72" height="16" rx="3" class="frame"/><rect x="16" y="20" width="18" height="8" rx="3"/><rect x="38" y="20" width="18" height="8" rx="3"/>',
    toggle: '<rect x="12" y="18" width="24" height="12" rx="6"/><circle cx="30" cy="24" r="4" class="knob"/><rect x="42" y="21" width="30" height="5" rx="2"/>',
    search: '<rect x="12" y="16" width="72" height="16" rx="3" class="frame"/><circle cx="22" cy="24" r="4" class="line" fill="none"/>',
    tabs: '<rect x="12" y="10" width="20" height="8" rx="2"/><rect x="34" y="10" width="20" height="8" rx="2" class="frame"/><rect x="12" y="18" width="72" height="22" rx="2" class="frame"/>',
    columns: '<rect x="12" y="10" width="22" height="28" rx="2" class="frame"/><rect x="37" y="10" width="22" height="28" rx="2" class="frame"/><rect x="62" y="10" width="22" height="28" rx="2" class="frame"/>',
    box: '<rect x="12" y="8" width="72" height="32" rx="4" class="frame"/><rect x="20" y="16" width="40" height="5" rx="2"/>',
    download: '<path d="M48 10v18M40 22l8 8 8-8" class="line" fill="none"/><path d="M28 38h40" class="line"/>',
    form: '<rect x="12" y="8" width="72" height="9" rx="2" class="frame"/><rect x="12" y="20" width="72" height="9" rx="2" class="frame"/><rect x="58" y="32" width="26" height="9" rx="2"/>',
    message: '<rect x="12" y="14" width="72" height="20" rx="3" class="frame"/><circle cx="22" cy="24" r="4"/><rect x="30" y="22" width="40" height="4" rx="2"/>',
  };
  const key =
    /bar chart/.test(n) ? "bar" : /line chart/.test(n) ? "line" : /area/.test(n) ? "area" : /table/.test(n) ? "table" : /metric/.test(n) ? "metric" : /map/.test(n) ? "map" : /progress/.test(n) ? "progress"
    : /date/.test(n) ? "date" : /number range|slider/.test(n) ? "slider" : /multiselect/.test(n) ? "multi" : /toggle/.test(n) ? "toggle" : /search/.test(n) ? "search" : /select|sidebar/.test(n) ? "select"
    : /tabs/.test(n) ? "tabs" : /columns/.test(n) ? "columns" : /download/.test(n) ? "download" : /form/.test(n) ? "form" : /upload|cached|session|counter/.test(n) ? "box"
    : /toast|message|status/.test(n) ? "message" : "box";
  svg.innerHTML = shapes[key] ?? shapes.box!;
  return svg;
}

export interface Gallery {
  element: HTMLElement;
  /** The starters, by family (for the agent). */
  list: () => { family: string; starters: string[] }[];
}

/** The gallery: a search, then each family folding open (the first two open). `add`: a click puts the
 *  starter at the end of the page in front. */
export function starterGallery(add: (name: string) => void): Gallery {
  const search = h("input", { type: "search", class: "app-input wb-starters-search", placeholder: "Search", "aria-label": "Search the starters" }) as HTMLInputElement;
  const families = h("div", { class: "wb-starters" });
  const element = h("div", { class: "wb-starters-panel" }, h("div", { class: "wb-starters-searchbox" }, icon("zoom"), search), families);
  let found: StarterSummary[] = [];
  const open = new Set<string>(["filter", "display"]);
  const familyOf = (s: StarterSummary): string => s.tags.find((t) => FAMILIES.some(([key]) => key === t)) ?? "display";

  const draw = (): void => {
    const words = search.value.trim().toLowerCase();
    const shown = found.filter((s) => !words || `${s.name} ${s.description}`.toLowerCase().includes(words));
    clear(
      families,
      ...FAMILIES.map(([key, label]) => {
        const mine = shown.filter((s) => familyOf(s) === key);
        if (!mine.length) return null;
        const unfolded = open.has(key) || !!words;
        const head = h(
          "button",
          { type: "button", class: "wb-data-fold-head", "aria-expanded": String(unfolded), onclick: () => (open.has(key) ? open.delete(key) : open.add(key), draw()) },
          icon(unfolded ? "down" : "expand"),
          h("span", {}, label),
          h("span", { class: "wb-data-count" }, String(mine.length)),
        );
        return h(
          "section",
          { class: "wb-starter-family", dataset: { family: key } },
          h("h3", {}, head),
          unfolded
            ? h(
                "div",
                { class: "wb-starter-cards" },
                ...mine.map((s) =>
                  h(
                    "button",
                    {
                      type: "button",
                      class: "wb-starter-card",
                      draggable: "true",
                      title: s.description,
                      dataset: { starter: s.name },
                      onclick: () => add(s.name),
                      ondragstart: (e: DragEvent) => {
                        e.dataTransfer?.setData(STARTER_DRAG, s.name);
                        e.dataTransfer?.setData("text/plain", cardName(s.name));
                        if (e.dataTransfer) e.dataTransfer.effectAllowed = "copy";
                      },
                    },
                    h("span", { class: "wb-starter-sketch-box" }, sketch(s.name)),
                    h("span", { class: "wb-starter-name" }, cardName(s.name)),
                  ),
                ),
              )
            : null,
        );
      }),
    );
    if (!families.childElementCount) families.append(h("p", { class: "wb-data-empty" }, found.length ? "No matches" : "No starters"));
  };
  search.addEventListener("input", draw);
  search.addEventListener("keydown", (e) => e.stopPropagation());
  void starters().then(
    (all) => {
      found = all.flatMap((f) => f.blades).filter((s) => s.family === "Streamlit" && s.language === "streamlit" && FAMILIES.some(([key]) => s.tags.includes(key)));
      draw();
    },
    () => draw(),
  );
  draw();
  return {
    element,
    list: () => FAMILIES.map(([key, label]) => ({ family: label, starters: found.filter((s) => familyOf(s) === key).map((s) => s.name) })),
  };
}
