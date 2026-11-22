/**
 * The one action picker for any API (Plans/api-adapter.plan.md): a widget's endpoint property, an In's source
 * and an Event's call all list the same actions the same way, grouped by their API. An action is named
 * "GET /orders" (the project's local sandbox API's endpoint) or "[Orders] GET /orders" (the library's API
 * called Orders); the server gives the list (GET /streamlit/widgets/context `endpoints`) and every call of one
 * goes through api_adapter.
 */
import { h } from "./dom";

export const LOCAL_API = "Local sandbox API";

/** An action's API and its own words: "[Orders] GET /orders" is Orders and "GET /orders". */
export function actionParts(ref: string): { api: string; words: string } {
  const found = /^\[([^[\]]+)\] (.*)$/.exec(ref);
  return found ? { api: found[1]!, words: found[2]! } : { api: LOCAL_API, words: ref };
}

/**
 * The actions as a select's groups, one per API (the local sandbox API first): each option's value is
 * `valueOf(ref)`, its label the action's own words, the one equal to `current` selected.
 */
export function actionGroups(refs: string[], current: string, valueOf: (ref: string) => string = (ref) => ref): HTMLElement[] {
  const groups = new Map<string, string[]>();
  for (const ref of refs) {
    const { api } = actionParts(ref);
    groups.set(api, [...(groups.get(api) ?? []), ref]);
  }
  const names = [...groups.keys()].sort((a, b) => Number(b === LOCAL_API) - Number(a === LOCAL_API) || a.localeCompare(b));
  return names.map((api) =>
    h("optgroup", { label: api }, ...groups.get(api)!.map((ref) => h("option", { value: valueOf(ref), selected: valueOf(ref) === current }, actionParts(ref).words))),
  );
}

/** Whether an action only reads (a GET): an In's source takes these. */
export function readsOnly(ref: string): boolean {
  return actionParts(ref).words.startsWith("GET ");
}
