/**
 * modes.ts: the open project's mode (Plans/editions.plan.md, "Project modes"), as the backend declares it:
 * GET /app/mode. Shared code reads the mode's fields, never which type it is. [SHARED]
 *
 *   [MODE]      the canvases offered (New, the canvas area), the blade and function families shown first
 *               (the Blades page, Insert a snippet…; "Show all" still there), the languages, cell kinds,
 *               the export. No project open: the base's mode
 *   [TYPES]     every project type this app can make (GET /app/modes): New project offers each one
 *   [FOLLOW]    asked again when a project opens, closes or is made (refresh), and its listeners told
 *
 * ROUTING: GET /app/mode, GET /app/modes (routes_modes.py)
 */
import { api } from "./api";

/** Where a cell kind runs in this mode when not in the Python kernel (an extension's kernel): its words, its
 *  editor's language, the route a run is posted to (a stream of output records, as a kernel's), the route that
 *  draws it (a page for the HTML cells' frame), the route that opens a table result as a grid, the editor's
 *  declarations, the install of a tool it lacks. */
export interface CellRoute {
  name: string;
  language: string;
  run: string;
  preview?: string;
  grid?: string;
  types?: string;
  install?: string;
}

export interface Mode {
  type: string;
  name: string;
  deliverable: string;
  canvases: string[];
  families: string[];
  languages: string[];
  cell_kinds: string[];
  tools: string[];
  export: string[];
  cell_routes?: Record<string, CellRoute>;
}

export interface ActiveMode {
  project: string | null;
  project_type: string;
  mode: Mode;
  needs?: string;
}

const BASE: Mode = { type: "bi", name: "BI", deliverable: "a notebook", canvases: ["streamlit"], families: [], languages: ["python"], cell_kinds: [], tools: [], export: ["notebook"] };
let active: ActiveMode = { project: null, project_type: "bi", mode: BASE };
let every: Mode[] = [BASE];
let asked: Promise<ActiveMode> | null = null;
const listeners: ((mode: ActiveMode) => void)[] = [];

export const activeMode = (): ActiveMode => active;
export const modes = (): Mode[] => every;

/** The mode asked again (a project opened, closed or made); its listeners hear it when it changed. */
export function refreshMode(): Promise<ActiveMode> {
  asked = Promise.all([api<ActiveMode>("/app/mode"), api<{ modes: Mode[] }>("/app/modes")])
    .then(([found, listed]) => {
      const changed = JSON.stringify(found) !== JSON.stringify(active) || listed.modes.length !== every.length;
      active = found;
      every = listed.modes;
      if (changed) for (const listener of listeners) listener(found);
      return found;
    })
    .catch(() => active);
  return asked;
}

/** The mode once it is known (asked the first time). */
export const whenMode = (): Promise<ActiveMode> => asked ?? refreshMode();

export function onMode(listener: (mode: ActiveMode) => void): void {
  listeners.push(listener);
}

/** Does the open project's mode offer this canvas kind ("excel", "streamlit")? */
export const offersCanvas = (kind: string): boolean => active.mode.canvases.includes(kind);

/** Where a cell of this kind runs in the open project's mode (null: the Python kernel, as always). */
export const cellRoute = (kind: string): CellRoute | null => active.mode.cell_routes?.[kind] ?? null;

/** Is a blade family one the mode shows first? (A mode with no families shows every one.) */
export const familyShown = (family: string | null | undefined): boolean => !active.mode.families.length || active.mode.families.includes(family ?? "");

/** The mode's families, said for a "Show all" switch ("Excel, Write, Files"); empty when it shows all. */
export const familyWords = (): string => active.mode.families.join(", ");
