/**
 * gates.ts: the features a project type keeps closed to stay simple (the owner, 2026-11-19), drawn from what the
 * backend says (GET /app/gates: the mode's `areas`). Generic: no project type is named here. [SHARED]
 *
 *   [RAIL]    a closed area's rail item hidden (rail.ts asks isClosed)
 *   [LINE]    every other way in (an address, a link, a menu, the palette, the Workbench's New entries) shows
 *             one line: "This <type> project keeps <feature> closed." with Open every feature; an address that
 *             lands on a closed area covers its page with that line (the page is not seen behind it)
 *   [ASK]     gatedRun: a command or a New entry of a closed area shows the line instead of running (the
 *             agent's tools stay open: its commands are never gated)
 *   [TOUR]    the mode's own tour cards, for a gated project type
 *   [SETTING] Settings' Open every feature in this project (off by default), kept in .sab/project.json
 *   [FIRST]   the first-open pop-up, once per project: its words from the mode; Got it / Open Settings
 *
 * ROUTING: GET/POST /app/gates  ·  notices project_changed, projects_changed
 */
import { api, onNotice } from "./api";
import { button, h, icon } from "./dom";

export interface Gates {
  open: string[] | null;
  closed: { area: string; name: string }[];
  gated: boolean;
  every: boolean;
  first_open: string | null;
  line: string;
  tour: { area: string; words: string }[];
}

let current: Gates | null = null;
const listeners = new Set<(g: Gates) => void>();

/** The gates now (asked once, again after a project changes). */
export async function loadGates(): Promise<Gates> {
  try {
    current = await api<Gates>("/app/gates");
  } catch {
    current = { open: null, closed: [], gated: false, every: false, first_open: null, line: "", tour: [] };
  }
  for (const told of listeners) told(current);
  return current;
}

export function onGates(told: (g: Gates) => void): void {
  listeners.add(told);
  if (current) told(current);
}

onNotice((n) => {
  if (n.type === "project_changed" || n.type === "projects_changed") void loadGates();
});

export function isClosed(area: string): boolean {
  return Boolean(current?.closed.some((c) => c.area === area));
}

async function openEvery(on: boolean): Promise<void> {
  current = await api<Gates>("/app/gates", "POST", { every: on });
  for (const told of listeners) told(current);
}

/** The one line a closed feature's way in shows, with Open every feature (the page keeps its place). With
 *  `cover` (an address that landed on the closed area), the line stands over that page so it is not seen. */
export function showGateLine(area: string, cover = false): void {
  const gate = current?.closed.find((c) => c.area === area);
  if (!current || !gate) return;
  document.querySelector(".gate-line")?.remove();
  if (!cover) removeGateCover();
  const gone = (): void => {
    line.remove();
    removeGateCover();
  };
  const line = h(
    "div",
    { class: "gate-line", role: "status", "data-area": area },
    icon("info"),
    h("span", {}, current.line.replace("{feature}", gate.name)),
    button("Open every feature", () => void openEvery(true).then(gone), { class: "primary" }),
    cover ? null : button("", gone, { icon: "close", class: "ghost", title: "Close" }),
  );
  if (!cover) {
    document.body.append(line);
    return;
  }
  // Over the page (and any page layer shown before it: a popover is in the top layer), beside the rail.
  let shade = document.querySelector<HTMLElement>(".gate-cover");
  if (!shade) {
    shade = h("div", { class: "gate-cover", popover: "manual", "data-area": area });
    document.body.append(shade);
  }
  shade.dataset.area = area;
  shade.replaceChildren(line);
  if (!shade.matches(":popover-open")) shade.showPopover();
}

/** The cover a closed area's address put over its page, taken away (the address moved to an open one). */
export function removeGateCover(): void {
  const shade = document.querySelector<HTMLElement>(".gate-cover");
  if (!shade) return;
  if (shade.matches(":popover-open")) shade.hidePopover();
  shade.remove();
}

/** Whether a way into `area` is closed: if so, its one line is shown and the caller does not go on. */
export function gated(area: string | null | undefined): boolean {
  if (!area || !isClosed(area)) return false;
  showGateLine(area);
  return true;
}

// The palette's commands and the Workbench's New entries by the area they belong to (their ids as
// workbenchPage.ts names them; an extension's own commands name theirs with Command.area).
const COMMAND_AREAS: [RegExp, string][] = [
  [/^(file\.newScript|file\.exportScript|script(\.|$)|runSettings|runHistory)/, "scripts"],
  [/^(file\.newApp|canvas\.|streamlit\.|data\.streamlitCells|appNotebook|toolbox|page$)/, "apps"],
  [/^(data\.blades|data\.starters|data\.starterList|blade$|starters$|snippet\.)/, "blades"],
  [/^data\.addApi/, "apis"],
  [/^(analyze|visualizations)/, "analyze"],
  [/^structures?/, "structures"],
];
const KIND_AREAS: Record<string, string> = { script: "scripts", page: "apps", notebook: "notebooks" };

/** The area a command belongs to (null: none of the gated ones). */
export function areaOfCommand(id: string): string | null {
  return COMMAND_AREAS.find(([pattern]) => pattern.test(id))?.[1] ?? null;
}

/** The area a Workbench tab kind's New makes a document of. */
export function areaOfKind(kind: string): string | null {
  return KIND_AREAS[kind] ?? null;
}

/** `run`, unless `area` is closed: then its line instead. */
export function gatedRun(area: string | null, run: () => void): () => void {
  return () => {
    if (!gated(area)) run();
  };
}

/** The tour's cards for a gated project type (the mode's own list), or null: the usual tour. */
export function tourCards(): { area: string; words: string }[] | null {
  return current?.gated && current.tour.length ? current.tour : null;
}

/** Settings' switch: Open every feature in this project (shown only in a project whose type keeps some closed). */
export function gatesSetting(): HTMLElement {
  const host = h("fieldset", { class: "fieldset gates-fieldset", hidden: true }, h("legend", {}, icon("project"), "This project"));
  const input = h("input", { type: "checkbox", role: "switch", class: "switch-input", id: "open-every-feature" });
  input.addEventListener("change", () => void openEvery(input.checked));
  host.append(h("label", { class: "autosave-switch" }, input, h("span", {}, "Open every feature in this project")));
  onGates((g) => {
    host.hidden = !g.gated;
    input.checked = g.every;
  });
  if (!current) void loadGates();
  return host;
}

/** The first-open pop-up, once per project (remembered there): Got it, or Open Settings on the switch. */
export function firstOpen(openSettings: () => void): void {
  onGates((g) => {
    if (!g.first_open || document.querySelector(".gates-first")) return;
    const dialog = h("dialog", { class: "dialog gates-first", "aria-label": "Features" }) as HTMLDialogElement;
    const done = (then?: () => void): void => {
      dialog.close();
      dialog.remove();
      void api<Gates>("/app/gates", "POST", { seen: true }).then((got) => (current = got), () => undefined);
      then?.();
    };
    dialog.append(
      h("p", {}, g.first_open),
      h(
        "div",
        { class: "dialog-buttons" },
        button("Open Settings", () => done(openSettings)),
        button("Got it", () => done(), { class: "primary" }),
      ),
    );
    document.body.append(dialog);
    dialog.showModal();
  });
}
