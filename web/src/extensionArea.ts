/**
 * extensionArea.ts: a rail area an on extension names with a `panel` route (GET /app/areas: {area, name, icon,
 * panel}), drawn as a page of the rail's from that route's data (extensionPanel.ts). Generic: the page never
 * names an extension; its words, choices and buttons are all the backend's. [SHARED]
 *
 * ROUTING: GET /app/areas  ·  the area's panel route (GET, POST)
 */
import { api } from "./api";
import { openAreaPage, type PageElement } from "./areaPage";
import { extensionPanel } from "./extensionPanel";
import { dismissDialog, layerOpened, registerLayer, setOverTitle } from "./nav";

export interface PanelArea {
  area: string;
  name: string;
  icon: string;
  panel: string;
}

let found: Promise<PanelArea[]> | null = null;
// The address the page was opened at (nav may take an area it does not know yet out of it while it starts).
const ASKED = new URLSearchParams(location.search).get("open");

/** The areas with a page drawn from data, each registered as a layer (open=<area>) once. */
export function panelAreas(): Promise<PanelArea[]> {
  found ??= api<{ areas: (PanelArea & { panel?: string })[] }>("/app/areas").then(
    (got) => {
      const areas = got.areas.filter((a): a is PanelArea => Boolean(a.panel));
      for (const area of areas) register(area);
      return areas;
    },
    () => [],
  );
  return found;
}

function register(area: PanelArea): void {
  let shown: PageElement | null = null;
  const draw = (): void => {
    const { element, body, setHeading } = openAreaPage(area.area, area.name);
    shown = element;
    setOverTitle(area.name);
    setHeading(area.name);
    body.append(extensionPanel(area.panel));
  };
  registerLayer(area.area, {
    isOpen: () => Boolean(shown?.open),
    open: () => draw(),
    show: () => undefined,
    dismiss: () => {
      if (shown) dismissDialog(shown);
    },
  });
  // Its address (open=<area>) named before the area was known: opened now.
  if ((ASKED === area.area || new URLSearchParams(location.search).get("open") === area.area) && !shown) {
    layerOpened(area.area);
    draw();
  }
}
