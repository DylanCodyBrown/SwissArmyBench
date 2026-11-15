/**
 * panels.ts: the panels Settings can turn off (the owner, 2026-11-15). [FUNCTION + WIRE]
 *
 * Each panel has a switch on the server (domain/panels.py), on unless the user turns it off: shared by
 * every window, kept through a reload, every one on again when SwissArmyGrid starts. A panel turned off
 * is gone, not folded: the page puts `panel-off-<id>` on <body> and grid.css takes the panel away; the
 * pages' own code asks `panelOn` where a panel would open by itself (a run opening the console).
 *
 * ROUTING: GET /panels, PUT /panels (routes_panels.py); the `panels_changed` notice
 */
import { api, onNotice } from "./api";

export interface PanelSwitch {
  id: string;
  page: "Workbench" | "Grid page";
  name: string;
  on: boolean;
}

let panels: PanelSwitch[] = [];
const listeners: (() => void)[] = [];

const cssName = (id: string): string => `panel-off-${id.replace(/\./g, "-")}`;

function take(list: PanelSwitch[]): void {
  panels = list;
  for (const p of panels) document.body.classList.toggle(cssName(p.id), !p.on);
  for (const listener of listeners) listener();
}

/** Whether a panel is on (true until the server says otherwise). */
export const panelOn = (id: string): boolean => panels.find((p) => p.id === id)?.on ?? true;

export const panelList = (): PanelSwitch[] => panels;

/** What a command says when its panel is off. */
export const turnedOff = (name: string): string => `${name} is turned off in Settings (Panels).`;

/** Called whenever the switches change (here or in another window). */
export function onPanels(listener: () => void): void {
  listeners.push(listener);
}

export async function loadPanels(): Promise<void> {
  try {
    take((await api<{ panels: PanelSwitch[] }>("/panels")).panels);
  } catch {
    /* an older server: every panel stays on */
  }
}

export async function setPanel(id: string, on: boolean): Promise<void> {
  take((await api<{ panels: PanelSwitch[] }>("/panels", "PUT", { [id]: on })).panels);
}

onNotice((notice) => {
  if (notice.type === "panels_changed") take((notice as unknown as { panels: PanelSwitch[] }).panels);
});
