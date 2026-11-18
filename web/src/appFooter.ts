/**
 * appFooter.ts: the one footer every page and window of the app wears (the owner, 2026-11-17: "same footer on the
 * erd page should be the same across the entire app"). [SHARED]
 *
 * The same frame, order and look everywhere: the version on the left, then the page's own items (a grid's rows and
 * selection on the home page; the kernel, environment, cursor, Problems and the panes' switches in the Workbench;
 * nothing on the Blades page), then on the right an extension's marks (areaMarks.ts: the open project out of sync),
 * the update notice, the zoom, Beta, Launch Claude and the credit.
 * A page passes only its own items; everything else is drawn here, so no page can drift from the others.
 */
import { areaMarks } from "./areaMarks";
import { betaMark } from "./betaNotes";
import { launchButton } from "./claudeLaunch";
import { h } from "./dom";
import { updateMark, versionMark } from "./updates";
import { zoomControl } from "./zoom";

/** Fill `host` with the app's footer: its common parts around the page's own `items` (and `end`, on the right,
 *  before the common right side: what belongs to the page but reads as a status, a meter or "live"). */
export function mountAppFooter(host: HTMLElement, items: Node[] = [], end: Node[] = []): void {
  host.classList.add("statusbar", "app-footer");
  host.replaceChildren(
    versionMark(),
    ...items,
    h("span", { class: "grow" }),
    ...end,
    areaMarks(),
    updateMark(),
    zoomControl(),
    betaMark(),
    launchButton(),
    h("span", { class: "credit" }, "Created by Dylan Brown"),
  );
}
