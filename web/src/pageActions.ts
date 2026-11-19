/**
 * pageActions.ts: buttons an extension that is on adds to a base page, as the backend declares them (the mode's
 * page_actions: {page, id, label, icon, title}). The page draws each one from that data and a click runs the
 * plug-in registered under its id with the page's own context; the page never names the extension. [SHARED]
 *
 * ROUTING: GET /app/mode (modes.ts) -> actionButtons(page, context)
 */
import { button } from "./dom";
import { activeMode } from "./modes";

export interface PageAction {
  page: string;
  id: string;
  label: string;
  icon?: string;
  title?: string;
}

type Run = (context: unknown) => void;
const plugins = new Map<string, Run>();

/** A plug-in's run, under the id its extension's PAGE_ACTIONS names. */
export function registerPageAction(id: string, run: Run): void {
  plugins.set(id, run);
}

/** Run a plug-in by its id with `context` (an extension's panel opening it right there); false: not here. */
export function openPlugin(id: string, context: unknown): boolean {
  const run = plugins.get(id);
  if (!run) return false;
  run(context);
  return true;
}

/** The buttons for `page`: each declared action whose plug-in is here. */
export function actionButtons(page: string, context: () => unknown): HTMLButtonElement[] {
  const declared = (activeMode().mode as { page_actions?: PageAction[] }).page_actions ?? [];
  return declared
    .filter((a) => a.page === page && plugins.has(a.id))
    .map((a) => button(a.label, () => plugins.get(a.id)?.(context()), { icon: a.icon || undefined, title: a.title || a.label }));
}
