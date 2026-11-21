/**
 * zoom.ts: the app's one zoom, on every page and window. [SHARED]
 *
 *   [CONTROL]  - 100% + in the status bar beside Beta (the owner, 2026-11-17: "move the zoom to the bottom
 *              beside the word beta so its available the entire time in the app"), on the grid page,
 *              the Workbench and the blades page
 *   [INPUT]    Ctrl + mouse wheel, Ctrl+= / Ctrl++ / Ctrl+- and Ctrl+0 anywhere on the page (the browser's
 *              own page zoom is taken over: the app scales its text, icons and the grid's rows instead)
 *   [FOLLOW]   every window follows a zoom made in another (the zoom is remembered: theme.ts)
 */
import { button, h } from "./dom";
import { gridZoom, onThemeChange, setGridZoom, stepZoom } from "./theme";

const percent = (): string => `${Math.round(gridZoom() * 100)}%`;

/** The status bar's zoom: - 100% +. Its percentage follows every zoom step. */
export function zoomControl(): HTMLElement {
  const out = h("output", { "aria-live": "polite", title: "Zoom (Ctrl + mouse wheel, Ctrl+= and Ctrl+-; Ctrl+0 resets)" }, percent());
  onThemeChange(() => {
    out.textContent = percent();
  });
  return h(
    "span",
    { class: "zoom-control status-zoom", role: "group", "aria-label": "Zoom" },
    button("Zoom out", () => stepZoom(-1), { icon: "minus", iconOnly: true, title: "Zoom out (Ctrl+-, or Ctrl + wheel down)" }),
    out,
    button("Zoom in", () => stepZoom(1), { icon: "plus", iconOnly: true, title: "Zoom in (Ctrl+=, or Ctrl + wheel up)" }),
  );
}

let installed = false;
/** Inside an element marked data-own-zoom (an IDE's code: codeIde.ts), the element zooms itself. */
const ownZoom = (target: EventTarget | null): boolean => target instanceof Element && !!target.closest("[data-own-zoom]");
/** Ctrl + wheel and the Ctrl keys zoom the app, not the browser. Once per page. */
export function installZoomInput(): void {
  if (installed) return;
  installed = true;
  document.addEventListener(
    "keydown",
    (e) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey || ownZoom(e.target)) return;
      if (e.key === "=" || e.key === "+") stepZoom(1);
      else if (e.key === "-" || e.key === "_") stepZoom(-1);
      else if (e.key === "0") setGridZoom(1);
      else return;
      e.preventDefault();
      e.stopPropagation(); // the editor's own Ctrl+= (Monaco's font zoom) does not double it
    },
    { capture: true },
  );
  // A trackpad's pinch arrives as Ctrl + wheel too; small deltas add up to one step.
  let pending = 0;
  document.addEventListener(
    "wheel",
    (e) => {
      if (!(e.ctrlKey || e.metaKey) || ownZoom(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      pending += e.deltaY;
      if (Math.abs(pending) < 40) return;
      stepZoom(pending < 0 ? 1 : -1);
      pending = 0;
    },
    { capture: true, passive: false },
  );
}
