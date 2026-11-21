/**
 * Widget starter packs in the lists (the owner, 2026-11-21): a prebuilt widget that names a pack shows under
 * that pack's heading (the server sends them first, in the packs' order), the rest under their group; the open
 * project's own widgets (its widgets/ folder) under "This project" first, then the library's under "Library".
 * A pack's heading carries its description (a line under it, and its title).
 */
import { h } from "./dom";

export interface Packed {
  prebuilt: boolean;
  /** Where it lives: the project's widgets/, the library's, or prebuilt (the lists' order). */
  where?: "project" | "library" | "prebuilt";
  group: string;
  pack?: string;
  pack_description?: string;
}

/** The heading a widget is listed under. */
export const headingOf = (w: Packed): string => (w.prebuilt ? w.pack || w.group : w.where === "project" ? "This project" : "Library");

/** The heading's element: `cls` for its look; a pack's description as a line under it when `line`. */
export function headingElement(cls: string, w: Packed, line = true): HTMLElement {
  const text = headingOf(w);
  const description = w.prebuilt && w.pack ? w.pack_description || "" : "";
  const heading = h("div", { class: cls, title: description || undefined, "data-pack": w.prebuilt && w.pack ? w.pack : undefined }, text);
  if (!description || !line) return heading;
  return h("div", { class: "wg-pack" }, heading, h("div", { class: "wg-pack-desc" }, description));
}
