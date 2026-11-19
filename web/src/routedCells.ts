/**
 * routedCells.ts: a cell run by another kernel than the notebook's Python one, where the open project's mode
 * says so (modes.ts cellRoute: an extension's TypeScript and SQL cells, its TSX cells drawn). [WIRE + FUNCTION]
 *
 *   [RUN]     the route streams one output record a line, as a kernel's run does (workbenchKernel.ts),
 *             then {done}; an error comes with its panel's detail
 *   [DRAW]    a TSX cell: the route answers one page, shown in the HTML cells' design frame
 *   [GRID]    a table result opened as a grid by its id
 *   [TYPES]   the route's declarations for the editor's TypeScript service, asked once
 *   [MISSING] a tool the route needs and this computer lacks: the one missing-package prompt; its Install
 *             is the route's own install
 *
 * Nothing here names a mode or an extension: the routes are data the backend declared.
 */
import { api, ApiError, saidOf, token } from "./api";
import { toast } from "./dom";
import type { CellRoute } from "./modes";
import { type Missing, promptForError } from "./missingPackages";
import type { Done } from "./workbenchKernel";
import type { Output } from "./workbenchOutputs";
import { errorHere } from "./errorNote";

export interface RoutedRun {
  path: string | null;
  kind: string;
  code: string;
  cell: number | null;
}

/** A missing tool's answer (422 with {missing}) put in the user's face, Install going to the route's own. */
function prompted(route: CellRoute, error: unknown, again?: () => void): boolean {
  const said: unknown = saidOf(error) ?? error;
  const install = async (missing: Missing): Promise<void> => {
    if (route.install) await api(route.install, "POST", { tool: (missing as Missing & { tool?: string }).tool });
  };
  return promptForError(said, { install, then: again });
}

/** Run a cell on its route: each output as it comes, then how the run ended. A missing tool: the prompt. */
export async function runRouted(route: CellRoute, body: RoutedRun, onOutput: (o: Output) => void, again?: () => void): Promise<Done> {
  const response = await fetch(route.run, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, stream: true }),
  });
  if (!response.ok || !response.body) {
    const error = new ApiError(response.status, await response.text());
    if (prompted(route, error, again)) return { ok: false, execution_count: null, error: "" };
    throw error;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let done: Done = { ok: false, execution_count: null };
  for (;;) {
    const { value, done: finished } = await reader.read();
    if (value) pending += decoder.decode(value, { stream: true });
    let at: number;
    while ((at = pending.indexOf("\n")) >= 0) {
      const line = pending.slice(0, at).trim();
      pending = pending.slice(at + 1);
      if (!line) continue;
      const item = JSON.parse(line) as Output & { done?: Done };
      if (item.done) done = item.done;
      else onOutput(item);
    }
    if (finished) break;
  }
  return done;
}

/** A TSX cell drawn: the page for the design frame (its policy is the HTML cells'). Null: the prompt took it. */
export async function previewRouted(route: CellRoute, body: { path: string | null; source: string; cell: number | null }, again?: () => void): Promise<string | null> {
  if (!route.preview) throw new Error("This cell kind is not drawn here.");
  try {
    return (await api<{ html: string }>(route.preview, "POST", body)).html;
  } catch (e) {
    if (prompted(route, e, again)) return null;
    throw e;
  }
}

/** A table result opened as a grid, by its id; the grid comes to the front in the grid page. */
export async function openRoutedTable(route: CellRoute, path: string | null, id: string, name?: string): Promise<void> {
  if (!route.grid) return;
  try {
    const opened = await api<{ dataset?: string }>(route.grid, "POST", { path, id, name });
    toast(`${opened.dataset ?? "The result"} is open as a grid.`);
  } catch (e) {
    errorHere(e);
  }
}

const declarations = new Map<string, Promise<string>>();

/** The route's declarations for the editor (asked once per route; empty when it has none). */
export function routedTypes(route: CellRoute): Promise<string> {
  const url = route.types;
  if (!url) return Promise.resolve("");
  let found = declarations.get(url);
  if (!found) {
    found = fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.text() : ""))
      .catch(() => "");
    declarations.set(url, found);
  }
  return found;
}
