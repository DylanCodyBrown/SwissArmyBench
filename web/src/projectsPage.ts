/**
 * projectsPage.ts: the Projects page, the rail's mark (the owner, 2026-11-18: "Move this to the rail ... and
 * give this button its own page for projects dont share the grid as the home page"). [PAGE]
 *
 *   [PAGE]    a page of the rail's over the home page (areaPage.ts), in the address as open=projects: the
 *             Project Explorer (projectExplorer.ts: New project, Open project…, the cards, the types strip)
 *             and the tour (tour.ts: its button and the "New here?" bubble, only here). The grids stay as they
 *             were under it; the grid page is only the grids.
 *   [HOME]    the mark and Alt+Home land here (nav.ts goHome); another window's mark brings the home window
 *             forward showing it. The app opens here when it starts with no table and no project (main.ts),
 *             and the old /workspace?view=start lands here (replaced).
 *   [OPEN]    a project opened or made here: the page makes way for its grids (pushed: Back comes back).
 *
 * Only the home page has this page (main.ts imports it): the rail elsewhere brings the home window forward.
 */
import { openAreaPage, type PageElement } from "./areaPage";
import { dismissDialog, registerLayer, setOverTitle, visit, withParams } from "./nav";
import { explorerInto, mountExplorer } from "./projectExplorer";
import type { ProjectState } from "./projectFile";
import { tourButton } from "./tour";

/** The page's name, in one place: the rail, the title. */
export const PROJECTS = "Projects";

let shown: PageElement | null = null;

/** A project opened here: its grids (the landing when it has no table yet), Projects put away. */
function toGrids(state: ProjectState | null): void {
  if (!state?.project) return;
  if (new URLSearchParams(location.search).get("open") !== "projects") return;
  visit(withParams({ open: null, at: null, type: null, name: null, view: null }));
}

function draw(): void {
  const { element, body, actions } = openAreaPage("projects", PROJECTS);
  shown = element;
  body.classList.add("projects-page");
  actions.append(tourButton());
  setOverTitle(PROJECTS);
  explorerInto(body);
}

/** The home page's Projects page (main.ts, once). */
export function mountProjectsPage(): void {
  mountExplorer(toGrids);
  registerLayer("projects", {
    isOpen: () => Boolean(shown?.open),
    open: () => draw(),
    show: () => undefined,
    dismiss: () => {
      if (shown) dismissDialog(shown);
    },
  });
}
