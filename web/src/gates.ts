/**
 * gates.ts: the features a project type keeps closed to stay simple (the owner, 2026-11-19), drawn from what the
 * backend says (GET /app/gates: the mode's `areas`). Generic: no project type is named here. [SHARED]
 *
 *   [RAIL]    a closed area's rail item hidden (rail.ts asks isClosed)
 *   [LINE]    every other way in (an address, a link, a menu, the palette) shows one line: "This <type> project
 *             keeps <feature> closed." with Open every feature
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

/** The one line a closed feature's way in shows, with Open every feature (the page keeps its place). */
export function showGateLine(area: string): void {
  const gate = current?.closed.find((c) => c.area === area);
  if (!current || !gate) return;
  document.querySelector(".gate-line")?.remove();
  const line = h(
    "div",
    { class: "gate-line", role: "status", "data-area": area },
    icon("info"),
    h("span", {}, current.line.replace("{feature}", gate.name)),
    button("Open every feature", () => void openEvery(true).then(() => line.remove()), { class: "primary" }),
    button("", () => line.remove(), { icon: "close", class: "ghost", title: "Close" }),
  );
  document.body.append(line);
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
