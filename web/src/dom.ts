/**
 * dom.ts: tiny helpers for building the page without a framework. [SHARED]
 *
 * h("button", { class: "btn", onclick: fn }, "Run") is the whole idiom: like building a WPF
 * visual tree in code. Text is always set as text (never innerHTML), because cell values are
 * untrusted (plan section 6, rule 8); the only innerHTML is the fixed icon markup below and the
 * escaped markdown renderer.
 */

type Child = Node | string | number | null | undefined | false;
type Attrs = Record<string, unknown>;

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Attrs = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on") && typeof value === "function") {
      element.addEventListener(key.slice(2), value as EventListener);
    } else if (key === "class") {
      element.className = String(value);
    } else if (key === "dataset" && typeof value === "object") {
      Object.assign(element.dataset, value);
    } else if (key === "style" && typeof value === "object") {
      // setProperty for custom properties (--share): Object.assign drops them silently.
      for (const [name, css] of Object.entries(value as Record<string, string>)) {
        if (name.startsWith("--")) element.style.setProperty(name, css);
        else Object.assign(element.style, { [name]: css });
      }
    } else if (value === true) {
      element.setAttribute(key, "");
    } else {
      element.setAttribute(key, String(value));
    }
  }
  append(element, ...children);
  return element;
}

export function append(parent: Node, ...children: Child[]): void {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    parent.appendChild(typeof child === "object" ? child : document.createTextNode(String(child)));
  }
}

export function clear(element: Element, ...children: Child[]): void {
  element.replaceChildren();
  append(element, ...children);
}

export function $(selector: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(selector);
  if (!found) throw new Error(`Missing element ${selector}`);
  return found;
}

// The parts some icons share: a database's cylinder (its own mark goes beside it, lower right), a
// file's sheet, a lock.
const CYL = '<ellipse cx="8.5" cy="5.5" rx="5.5" ry="2.2"/><path d="M3 5.5v12.5c0 1.2 2.5 2.2 5.5 2.2M14 5.5V10M3 12c0 1.2 2.5 2.2 5.5 2.2"/>';
const SHEET = '<path d="M6 3h8l4 4v14H6zM14 3v4h4"/>';
const LOCK = '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7.5a4 4 0 018 0V11"/>';
const CLOUD = '<path d="M7 19h10a4 4 0 00.6-8 5.6 5.6 0 00-10.8 1.4A3.4 3.4 0 007 19z"/>';

// Line icons (24x24, stroke). Fixed markup, so innerHTML is safe here.
const ICONS: Record<string, string> = {
  // The Settings button: a cog (a toothed wheel around a hub).
  cog: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z"/>',
  // A known relationship (from the model), and a primary-key column.
  crown: '<path d="M3 8l4 4 5-7 5 7 4-4-2 11H5z"/><path d="M5 19h14"/>',
  key: '<circle cx="8" cy="14" r="4"/><path d="M11 11l9-9M16 6l3 3M14 8l2 2"/>',
  link: '<path d="M10 14a4 4 0 005.66 0l3-3a4 4 0 00-5.66-5.66l-1 1"/><path d="M14 10a4 4 0 00-5.66 0l-3 3a4 4 0 005.66 5.66l1-1"/>',
  steps: '<path d="M4 6h16M4 12h10M4 18h6"/>',
  case: '<path d="M3 18l4-12 4 12M4.5 14h5M14 13.5a3 3 0 1 0 6 0v4.5M20 13.5a3 3 0 0 0-6 0"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1"/>',
  // A Dataverse environment: a table of rows inside a hexagon (our own drawing).
  dataverse: '<path d="M12 2.5l8.2 4.75v9.5L12 21.5l-8.2-4.75v-9.5z"/><path d="M7.5 9.5h9M7.5 13h9M7.5 16.5h9M12 9.5v7"/>',
  // The lake and SharePoint kinds (our own drawings): a lake's waves, a Delta's triangle, a list, a page.
  onelake: '<path d="M3 15c2 0 2 1.5 4.5 1.5S10 15 12 15s2 1.5 4.5 1.5S19 15 21 15M3 19c2 0 2 1.5 4.5 1.5S10 19 12 19s2 1.5 4.5 1.5S19 19 21 19"/><path d="M12 3l5 8H7z"/>',
  datalake: '<path d="M3 15c2 0 2 1.5 4.5 1.5S10 15 12 15s2 1.5 4.5 1.5S19 15 21 15M3 19c2 0 2 1.5 4.5 1.5S10 19 12 19s2 1.5 4.5 1.5S19 19 21 19"/><ellipse cx="12" cy="6" rx="6" ry="2.5"/><path d="M6 6v4c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V6"/>',
  delta: '<path d="M12 3.5L21 19H3z"/><path d="M12 9.5L16.5 17h-9z"/>',
  sharepoint: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 12.5h8M8 16h5"/>',
  sharepoint_docs: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 15.5h6"/>',
  sql: '<ellipse cx="12" cy="5.5" rx="7" ry="2.5"/><path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/>',
  profile: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  code: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 3h6v3H9zM10 11l-2 2 2 2M14 11l2 2-2 2"/>',
  export: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
  // The Workbench's tabs and Data panel (the redesign of 2026-11-15): a notebook, an app page, a file,
  // a blade's value, and splitting a group right or down.
  notebook: '<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M9 3v18M12.5 7.5h3M12.5 11h3"/>',
  page: '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 9h18M10 9v11"/>',
  file: '<path d="M6 3h8l4 4v14H6zM14 3v4h4"/>',
  bolt: '<path d="M13 3L5 13.5h6L10 21l8-10.5h-6z"/>',
  splitRight: '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M12 4v16"/>',
  splitDown: '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 12h18"/>',
  panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  bottom: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 14h18"/>',
  right: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M14 4v16"/>',
  max: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  restore: '<path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/>',
  collapse: '<path d="M15 6l-6 6 6 6"/>',
  up: '<path d="M6 15l6-6 6 6"/>',
  down: '<path d="M6 9l6 6 6-6"/>',
  branch: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/><path d="M6 7v10M18 9c0 5-12 3-12 8"/>',
  more: '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>',
  expand: '<path d="M9 6l6 6-6 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  edit: '<path d="M4 20h4L20 8l-4-4L4 16v4z"/>',
  pin: '<path d="M9 4h6l-1 6 4 4H6l4-4-1-6zM12 14v6"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 012-2h8"/>',
  zoom: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5M11 8v6M8 11h6"/>',
  popout: '<path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/>',
  play: '<path d="M7 5l12 7-12 7V5z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1"/>',
  // The debugger's (workbenchDebug.ts): a bug, step over, into, out.
  bug: '<path d="M9 7a3 3 0 016 0M8 9h8v6a4 4 0 01-8 0V9zM12 9v10M4 12h4M16 12h4M5 7l3 2M19 7l-3 2M5 18l3-2M19 18l-3-2"/>',
  "step-over": '<path d="M4 13a8 8 0 0115-3M19 4v6h-6"/><circle cx="12" cy="19" r="1.5"/>',
  "step-into": '<path d="M12 3v11M7 10l5 5 5-5"/><circle cx="12" cy="20" r="1.5"/>',
  "step-out": '<path d="M12 15V4M7 8l5-5 5 5"/><circle cx="12" cy="20" r="1.5"/>',
  agent: '<rect x="5" y="8" width="14" height="11" rx="3"/><path d="M12 4v4M9 13h.01M15 13h.01"/>',
  bucket: '<path d="M3 7h5v13H3zM10 4h5v16h-5zM17 10h4v10h-4zM3 20h18"/>',
  tag: '<path d="M3 12V4h8l10 10-8 8L3 12z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
  image: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/>',
  forward: '<path d="M14 6l6 6-6 6M20 12H4"/>',
  back: '<path d="M10 6l-6 6 6 6M4 12h16"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  "eye-off": '<path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0122 12s-1.2 2.1-3.4 4M6.6 6.6C3.8 8.5 2 12 2 12s4 7 10 7c1.9 0 3.5-.6 4.9-1.4"/><path d="M9.9 9.9a3 3 0 004.2 4.2"/>',
  claude: '<path d="M12 3v6M12 15v6M3 12h6M15 12h6M5.6 5.6l4.2 4.2M14.2 14.2l4.2 4.2M18.4 5.6l-4.2 4.2M9.8 14.2l-4.2 4.2"/>',
  star: '<path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z"/>',
  import: '<path d="M12 15V3M7 8l5-5 5 5M5 21h14"/>',
  folder: '<path d="M3 6a1 1 0 011-1h5l2 2h9a1 1 0 011 1v10a1 1 0 01-1 1H4a1 1 0 01-1-1z"/>',
  save: '<path d="M5 3h11l3 3v15H5zM8 3v5h8M8 21v-7h8v7"/>',
  check: '<path d="M4 12l5 5L20 6"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4 2v-8z"/>',
  sortup: '<path d="M7 20V4M3 8l4-4 4 4M14 6h7M14 12h5M14 18h3"/>',
  sortdown: '<path d="M7 4v16M3 16l4 4 4-4M14 6h3M14 12h5M14 18h7"/>',
  columns: '<path d="M4 4h16v16H4zM9.5 4v16M14.5 4v16"/>',
  group: '<path d="M4 5h6v6H4zM14 5h6v6h-6zM4 15h16v4H4z"/>',
  rename: '<path d="M4 20h4l10-10-4-4L4 16zM13 7l4 4"/>',
  clean: '<path d="M4 20l7-7M14 4l6 6-7 7-6-6zM4 20h6"/>',
  exclude: '<circle cx="12" cy="12" r="8"/><path d="M6.5 6.5l11 11"/>',
  keep: '<path d="M4 7h16M7 12h10M10 17h4"/>',
  rows: '<path d="M4 5h16M4 10h16M4 15h16M4 20h16"/>',
  // A lineage: a source flowing down through two steps.
  lineage: '<rect x="8" y="2.5" width="8" height="5" rx="1"/><rect x="3" y="16.5" width="8" height="5" rx="1"/><rect x="13" y="16.5" width="8" height="5" rx="1"/><path d="M12 7.5V12M7 16.5V12h10v4.5"/>',
  // The fit test: a bell curve on a baseline. Outliers: a cluster of points and one far away.
  fit: '<path d="M3 20h18M4 19c3 0 4.5-13 8-13s5 13 8 13"/>',
  outliers: '<circle cx="6" cy="16" r="1.4"/><circle cx="10" cy="13.5" r="1.4"/><circle cx="9" cy="18" r="1.4"/><circle cx="13" cy="16.5" r="1.4"/><circle cx="19" cy="5" r="2"/><path d="M3 21h18"/>',
  // The tour: a question mark in a circle.
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 114 2c-.9.6-1.5 1.1-1.5 2.2M12 17h.01"/>',
  warning: '<path d="M12 3.5L21.5 20h-19z"/><path d="M12 10v4.5M12 17.5h.01"/>',
  problem: '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  // The Workbench's modes (2026-11-15): history, schedule, outline, properties, state, devices, light
  // and dark, undo and redo, align, duplicate, dictionary, run up to here (lineage's own is above).
  history: '<path d="M3 12a9 9 0 103-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  outline: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
  properties: '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M9 4v16"/>',
  sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
  desktop: '<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4"/>',
  tablet: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M11 18h2"/>',
  phone: '<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18.5h2"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/>',
  undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 010 11H11"/>',
  redo: '<path d="M15 14l5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 000 11H13"/>',
  align: '<path d="M4 3v18M8 7h12v4H8zM8 14h7v4H8z"/>',
  duplicate: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 00-2-2H5a2 2 0 00-2 2v9a2 2 0 002 2h3"/>',
  book: '<path d="M2 5h7a3 3 0 013 3v13a2 2 0 00-2-2H2zM22 5h-7a3 3 0 00-3 3v13a2 2 0 012-2h8z"/>',
  runTo: '<path d="M5 4v16M9 5l10 7-10 7z"/>',
  reset: '<path d="M3 12a9 9 0 109-9 9.7 9.7 0 00-6.7 2.7L3 8"/><path d="M3 3v5h5"/>',
  wiring: '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 6c7 0 3 12 10 12"/><path d="M14 15l3 3-3 3"/>',
  // ----- projects (projectFile.ts, projectImport.ts) -----
  // A project: a page with its corner folded, the app's cross on it.
  project: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M12 10v6M9 13h6"/>',
  // The rail's Home (the owner, 2026-11-21: "a + is confusing just make this a normal icon"): a house.
  home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
  // The rail's areas (rail.ts, 2026-11-16; Settings is the cog, Notebooks, Scripts and Apps their documents'
  // icons): the Analyze board's cards, the ERD's two tables and their join, a blade, a plug; Grids: a grid's tabs.
  sandbox: '<rect x="3" y="3" width="8" height="10" rx="1.5"/><rect x="13" y="3" width="8" height="6" rx="1.5"/><rect x="13" y="11" width="8" height="10" rx="1.5"/><rect x="3" y="15" width="8" height="6" rx="1.5"/>',
  diagram: '<rect x="2.5" y="3" width="9" height="7.5" rx="1.5"/><rect x="12.5" y="13.5" width="9" height="7.5" rx="1.5"/><path d="M2.5 6.2h9M12.5 16.7h9M11.5 8.3h2.5a2 2 0 012 2v3.2"/>',
  blade: '<path d="M2.5 14.5h12a3 3 0 010 6h-12a3 3 0 010-6z"/><path d="M11 14.5L20.5 4c1.2 4.2-.6 8.3-4.4 10.5"/><circle cx="5.5" cy="17.5" r=".6"/>',
  // The APIs page's (rail.ts): a request and its answer, two arrows between two ends.
  apis: '<path d="M4 8h12l-3-3M20 16H8l3 3"/><circle cx="19" cy="8" r="1.5"/><circle cx="5" cy="16" r="1.5"/>',
  // The Data page's (the rail, 2026-11-17): stacked disks, a cylinder in three bands; our own, no brand's.
  data: '<ellipse cx="12" cy="5" rx="7" ry="2.5"/><path d="M5 5v14c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V5M5 9.7c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5M5 14.3c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/>',
  // The Structures page's: a small branching tree, a root and three leaves.
  structures: '<circle cx="6" cy="5" r="2"/><path d="M6 7v12M6 12h5M6 19h5"/><rect x="12" y="9.5" width="8" height="5" rx="1.2"/><rect x="12" y="16.5" width="8" height="5" rx="1.2"/><path d="M8 5h4"/><rect x="12" y="2.5" width="8" height="5" rx="1.2"/>',
  plug: '<path d="M9 3v4.5M15 3v4.5M6 7.5h12v3.5a6 6 0 01-12 0zM12 17v4"/>',
  // The Code App page's (the Power Apps extension's): a window with code's angle brackets in it.
  codeapp: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 8h18M9.5 11.5 7 14l2.5 2.5M14.5 11.5 17 14l-2.5 2.5"/>',
  // Source Control (as VS Code's activity bar draws it: a line of commits and a branch joining it).
  "source-control": '<circle cx="7" cy="5" r="2.2"/><circle cx="7" cy="19" r="2.2"/><circle cx="17" cy="7" r="2.2"/><path d="M7 7.2v9.6M17 9.2c0 4-4 4.3-8.6 7.6"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
  // The Session page (2026-11-16): a log, a dot for each thing made.
  // The Variables page's (rail.ts): braces round an x.
  // The Environment: layers (everything the project holds, one on another).
  environment: '<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 12l9 5 9-5M3 16l9 5 9-5"/>',
  variables: '<path d="M8 4c-2 0-3 1-3 3v2c0 1.5-1 3-2 3 1 0 2 1.5 2 3v2c0 2 1 3 3 3"/><path d="M16 4c2 0 3 1 3 3v2c0 1.5 1 3 2 3-1 0-2 1.5-2 3v2c0 2-1 3-3 3"/><path d="M9.5 9.5l5 5M14.5 9.5l-5 5"/>',
  // The Extensions page's: a puzzle piece (what plugs into the base).
  extensions: '<path d="M4 8h4a2 2 0 114 0h4v4a2 2 0 110 4v4h-4a2 2 0 10-4 0H4v-4a2 2 0 100-4z"/>',
  session: '<path d="M5 3.5v17"/><circle cx="5" cy="6.5" r="1.7"/><circle cx="5" cy="12" r="1.7"/><circle cx="5" cy="17.5" r="1.7"/><path d="M10 6.5h11M10 12h8M10 17.5h10"/>',
  grids: '<path d="M3 8V5.5A1.5 1.5 0 014.5 4H10l1.5 4"/><rect x="3" y="8" width="18" height="12" rx="1.5"/><path d="M3 12h18M3 16h18M9 12v8M15 12v8"/>',
  // ----- connection types (2026-11-16, the owner: "our connection panel has no icons on the connection
  // types"), each by its type's id (connectionsWindow.ts): our own line icons, never a brand's logo. A
  // database is the cylinder with a mark of its own beside it; a file its sheet, grid, columns or braces;
  // a vault its lock, shield or cloud. Every database's is different (tests/test_icons.py).
  sqlserver: CYL + '<rect x="13" y="12" width="9" height="4" rx="1"/><rect x="13" y="17.5" width="9" height="4" rx="1"/><path d="M15.5 14h.01M15.5 19.5h.01"/>',
  azuresql: CYL + '<path d="M14.5 21.5h6a2.6 2.6 0 00.4-5.2 3.6 3.6 0 00-7 .9 2.2 2.2 0 00.6 4.3z"/>',
  postgres: CYL + '<path d="M13 13h5.5a3.5 3.5 0 013.5 3.5V19a2.5 2.5 0 01-2.5 2.5M17 13v6.5a2 2 0 01-2 2"/>',
  mysql: CYL + '<path d="M13 20.5c2-3.5 4.8-5.3 9-6-1.6 1.7-2 3.8-1.4 6.5M16.5 20l2.2-1.2"/>',
  mariadb: CYL + '<path d="M13 21.5c1-4.2 3.6-6.8 8.5-8-1 3-.8 5.6 1 8"/><path d="M18.6 16.4h.01"/>',
  oracle: CYL + '<ellipse cx="17.5" cy="17" rx="4.5" ry="3"/>',
  sqlite: CYL + '<path d="M14 22l7.5-9.5M21.5 12.5c-4.2 0-6.8 2.6-6.8 6.8 3.2 0 5.8-2.6 6.8-6.8zM16.5 17.6h2.3"/>',
  duckdb: CYL + '<circle cx="17" cy="15.3" r="2.4"/><path d="M19.4 15.3H22l-1.5 1.4M13.5 22c0-2.2 1.6-3.6 3.6-3.6h2c1.6 0 2.9 1.2 2.9 2.8V22z"/>',
  snowflake: CYL + '<path d="M17.5 12v10M13.2 14.5l8.6 5M13.2 19.5l8.6-5"/>',
  bigquery: CYL + '<circle cx="17" cy="16.5" r="3.6"/><path d="M19.6 19.1L22.5 22M15.6 17.6v-1.1M17.2 17.6v-2.6"/>',
  redshift: CYL + '<path d="M13.5 21.5l8-8M16 13.5h5.5V19"/>',
  databricks: CYL + '<path d="M17.5 12.5l4.5 2.5-4.5 2.5-4.5-2.5zM13 18.2l4.5 2.5 4.5-2.5"/>',
  db2: CYL + '<path d="M13 13.5h9M13 17h9M13 20.5h9"/>',
  teradata: CYL + '<path d="M13 13h9M17.5 13v9"/>',
  trino: CYL + '<path d="M17.5 12.5l4.5 9h-9z"/>',
  clickhouse: CYL + '<path d="M14 13v9M16.5 13v9M19 13v9M21.5 16v3"/>',
  saphana: CYL + '<path d="M17.5 12l4.5 5-4.5 5-4.5-5z"/>',
  vertica: CYL + '<path d="M13 13l4.5 9 4.5-9"/>',
  sybase: CYL + '<rect x="13.5" y="13" width="8" height="8" rx="1.5"/><path d="M17.5 17h.01"/>',
  access: CYL + '<path d="M18 13h4v9h-4M13 17.5h6M16.5 15l2.5 2.5-2.5 2.5"/>',
  odbc: CYL + '<path d="M15.5 12v2.5M19.5 12v2.5M13.5 14.5h8v2a4 4 0 01-8 0zM17.5 20.5v2"/>',
  // A Power BI workspace: its bars (datasets, not a cylinder).
  powerbi: '<rect x="4" y="12" width="4" height="9" rx="1"/><rect x="10" y="7" width="4" height="14" rx="1"/><rect x="16" y="3" width="4" height="18" rx="1"/>',
  csv: SHEET + '<path d="M9 12h1.5M12.5 12H15M9 15.5h1.5M12.5 15.5H15M9 19h1.5M12.5 19H15"/>',
  excel: '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 9h18M3 14.5h18M9 4v16M15 4v16"/>',
  parquet: '<rect x="4" y="4" width="4" height="16" rx="1"/><rect x="10" y="4" width="4" height="16" rx="1"/><rect x="16" y="4" width="4" height="16" rx="1"/><path d="M4 9h4M10 13h4M16 8h4"/>',
  json: '<path d="M9 4C7 4 6 5 6 7v2.5C6 11 5 12 3.5 12 5 12 6 13 6 14.5V17c0 2 1 3 3 3M15 4c2 0 3 1 3 3v2.5c0 1.5 1 2.5 2.5 2.5-1.5 0-2.5 1-2.5 2.5V17c0 2-1 3-3 3"/>',
  // Your own Python: a prompt and its code.
  python: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M12 15h5"/>',
  azure_key_vault: CLOUD + '<path d="M12 13v3.5"/>',
  aws_secrets_manager: LOCK + '<path d="M12 13.5v5M9.8 14.8l4.4 2.4M14.2 14.8l-4.4 2.4"/>',
  aws_parameter_store: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 8v8M12 8v8M16 8v8M6.5 11h3M10.5 14h3M14.5 10h3"/>',
  google_secret_manager: '<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><circle cx="12" cy="11" r="1.6"/><path d="M12 12.6V16"/>',
  hashicorp_vault: '<path d="M3 4h18l-9 17z"/><path d="M10 8h.01M14 8h.01M12 11h.01M10 11h.01M14 11h.01"/>',
  onepassword: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v9"/>',
  dotenv: SHEET + '<path d="M9 13.5h6M9 16.5h6"/>',
  os_vault: LOCK + '<circle cx="12" cy="15.5" r="1.3"/><path d="M12 16.8v1.7"/>',
  // Add API's presets (a function host's bolt in its own frame) and its two ways in.
  "api-azure": CLOUD + '<path d="M12.5 11.5L10.5 15h3l-2 3"/>',
  "api-aws": '<path d="M5 20L11 4h3M9.5 8.5L15 20h4"/>',
  "api-google": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M13 8l-3 4.5h4L11 17"/>',
  "api-openapi": SHEET + '<path d="M10 11l-1.5 2 1.5 2M14 11l1.5 2-1.5 2"/>',
  "api-form": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h3M7 13h3M7 17h3M12 9h5M12 13h5M12 17h5"/>',
  // The catalog's tree: a schema, a table, a view; a column by its kind of value.
  schema: '<path d="M12 3l9 4.5-9 4.5-9-4.5z"/><path d="M3 12l9 4.5 9-4.5M3 16.5L12 21l9-4.5"/>',
  table: '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 9h18M3 14.5h18M9 9v11"/>',
  // A chart block (the Excel canvas): three columns on a baseline.
  chart: '<path d="M4 20h16"/><rect x="6" y="11" width="3" height="9"/><rect x="11" y="6" width="3" height="14"/><rect x="16" y="14" width="3" height="6"/>',
  view: '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 9h18"/><path d="M7 14.5s2-2.5 5-2.5 5 2.5 5 2.5-2 2.5-5 2.5-5-2.5-5-2.5z"/>',
  number: '<path d="M10 4L8 20M16 4l-2 16M4.5 9h15M4 15h15"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  toggle: '<rect x="2.5" y="7" width="19" height="10" rx="5"/><circle cx="16.5" cy="12" r="3"/>',
  // The starter pack's families and a snippet's languages: DAX's sum, HTML's brackets, Markdown's M.
  formula: '<path d="M18 4H6l6.5 8L6 20h12"/>',
  html: '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M13.5 5l-3 14"/>',
  markdown: '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 15V9l2.5 3L11 9v6M16.5 9v6M14.5 13l2 2 2-2"/>',
  // A Analyze note card (a chart is profile's bars, a table and a diagram their own, above).
  note: '<path d="M5 3h10l4 4v14H5z"/><path d="M8.5 10h7M8.5 13.5h7M8.5 17h4"/>',
};

/** Whether the set has `name` (an icon picked by a type's id falls back to its group's). */
export const hasIcon = (name: string): boolean => Object.prototype.hasOwnProperty.call(ICONS, name);

export function icon(name: string): SVGSVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("icon-svg");
  svg.setAttribute("data-icon", name); // which icon it is (the tests read it)
  svg.innerHTML = ICONS[name] ?? "";
  return svg;
}

/** A button with an icon, visible text (or a label for icon-only buttons) and a tooltip. */
export function button(
  label: string,
  onclick: (event: MouseEvent) => void,
  options: { icon?: string; iconOnly?: boolean; class?: string; title?: string; pressed?: boolean } = {},
): HTMLButtonElement {
  const btn = h(
    "button",
    {
      type: "button",
      class: `btn ${options.iconOnly ? "icon" : ""} ${options.class ?? ""}`.trim(),
      title: options.title ?? label,
      // Always named, so a label hidden at narrow widths still reads to screen readers.
      "aria-label": label,
      "aria-pressed": options.pressed === undefined ? undefined : String(options.pressed),
      onclick,
    },
    options.icon ? icon(options.icon) : null,
    options.iconOnly ? null : h("span", { class: "btn-label" }, label),
  );
  return btn;
}

// ===== toasts =====

/** The toasts' place: in the newest open modal dialog while one is open (the rest of the page is inert), else
 *  the page; when that dialog closes its toasts go back to the page (or the dialog under it), still showing. */
function toastHost(): HTMLElement {
  let host = document.querySelector<HTMLElement>(".toasts");
  if (!host) host = h("div", { class: "toasts", role: "status", "aria-live": "polite" });
  // A modal dialog makes the rest of the page inert and draws over it: while one is open the
  // toasts live inside the newest, so they are seen and their button (Undo, Show) can be pressed.
  const home = [...document.querySelectorAll<HTMLDialogElement>("dialog[open]")].pop() ?? document.body;
  if (host.parentElement !== home) {
    home.append(host);
    // When that dialog closes its toasts go back to the page (or the dialog under it), still showing.
    const back = host;
    if (home instanceof HTMLDialogElement) {
      home.addEventListener("close", () => {
        if (!home.contains(back)) return;
        ([...document.querySelectorAll<HTMLDialogElement>("dialog[open]")].filter((d) => d !== home).pop() ?? document.body).append(back);
      }, { once: true });
    }
  }
  return host;
}

/** A toast that holds `content` (errorNote.ts's errorToast: the error note itself), shown for `ms`, longer while
 *  the pointer or focus is in it. The same `key` already showing is kept up instead of stacked again. */
export function toastNode(content: HTMLElement, key: string, ms = 12000): HTMLElement {
  const host = toastHost();
  const shown = [...host.children].find((t) => (t as HTMLElement).dataset.message === key) as HTMLElement | undefined;
  const item = shown ?? h("div", { class: "toast toast-note", "data-message": key }, content);
  if (!shown) host.append(item);
  const later = (): void => {
    window.clearTimeout(Number(item.dataset.timer));
    item.dataset.timer = String(window.setTimeout(() => item.remove(), ms));
  };
  if (!shown) {
    const hold = (): void => window.clearTimeout(Number(item.dataset.timer));
    item.addEventListener("mouseenter", hold);
    item.addEventListener("focusin", hold);
    item.addEventListener("mouseleave", later);
  }
  later();
  return item;
}

/** A short message that goes by itself (Saved, Copied, an Undo). Never an error: an error is errorNote.ts's note,
 *  in place, or errorToast for work with no place on screen (design principles 9.5). */
export function toast(message: string, kind: "info" = "info", action?: { label: string; run: () => void }): void {
  const host = toastHost();
  // The same message already showing (a stopped server fails every action alike): keep that
  // one up for longer rather than stack copies up the screen.
  const shown = [...host.children].find((t) => (t as HTMLElement).dataset.message === message && !t.classList.contains("toast-note"));
  const item = (shown as HTMLElement | undefined) ?? h("div", { class: `toast ${kind}`, "data-message": message }, message);
  if (!shown) host.append(item);
  if (action && !shown) {
    // One button (Undo): it acts and the message goes.
    item.append(" ", h("button", { type: "button", class: "link toast-action", onclick: () => { item.remove(); action.run(); } }, action.label));
  }
  window.clearTimeout(Number(item.dataset.timer));
  item.dataset.timer = String(window.setTimeout(() => item.remove(), 5000));
}

// ===== dialogs =====

export interface DialogParts {
  dialog: HTMLDialogElement;
  body: HTMLElement;
  foot: HTMLElement;
  close: () => void;
}

/** What nav.ts does with each new dialog: an entry of its own, so the browser's Back closes it. */
let dialogHook: ((dialog: HTMLDialogElement) => void) | null = null;

export function setDialogHook(hook: (dialog: HTMLDialogElement) => void): void {
  dialogHook = hook;
}

/** A modal dialog with a title, a body and a footer. Escape and the close button close it, and so does
 *  the browser's Back (nav.ts), unless `history` is false: a dialog whose views are in the address
 *  (Connections, Settings), or one that waits for an answer (the agent's approval). */
export function openDialog(title: string, wide = false, options: { history?: boolean } = {}): DialogParts {
  const body = h("div", { class: "dialog-body" });
  const foot = h("div", { class: "dialog-foot" });
  const dialog = h("dialog", { class: wide ? "wide" : "", "aria-label": title });
  const close = (): void => {
    dialog.close();
    dialog.remove();
  };
  dialog.append(
    h("div", { class: "dialog-head" }, h("h2", {}, title), button("Close", close, { icon: "close", iconOnly: true, class: "ghost" })),
    body,
    foot,
  );
  dialog.addEventListener("close", () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
  if (options.history !== false) dialogHook?.(dialog);
  return { dialog, body, foot, close };
}

/** Close every open dialog (the newest first), as their own Close buttons do. */
export function closeDialogs(): void {
  for (const dialog of [...document.querySelectorAll<HTMLDialogElement>("dialog[open]")].reverse()) dialog.close();
}

// ===== analysis forms: results that no longer match the choices =====

// ===== safe storage (per-viewer conveniences only; may be unavailable) =====

export function remember(key: string, value: string): void {
  try {
    localStorage.setItem(`swissarmybench.${key}`, value);
  } catch {
    // Private windows and blocked storage: the setting just isn't remembered.
  }
}

export function recall(key: string): string | null {
  try {
    return localStorage.getItem(`swissarmybench.${key}`);
  } catch {
    return null;
  }
}

/** Forget a remembered setting. */
export function forget(key: string): void {
  try {
    localStorage.removeItem(`swissarmybench.${key}`);
  } catch {
    // Blocked storage: nothing was remembered.
  }
}

// ===== formatting =====

const NUMERIC = /^(U?TINYINT|U?SMALLINT|U?INTEGER|U?BIGINT|U?HUGEINT|FLOAT|DOUBLE|REAL|DECIMAL)/;
export const isNumericType = (type: string): boolean => NUMERIC.test(type.toUpperCase());
export const isTextType = (type: string): boolean => type.toUpperCase() === "VARCHAR";
export const isDateType = (type: string): boolean => /^(DATE|TIMESTAMP)/.test(type.toUpperCase());
export const isBoolType = (type: string): boolean => type.toUpperCase() === "BOOLEAN";

const grouping = new Intl.NumberFormat(undefined, { maximumFractionDigits: 6 });
export const formatCount = (n: number): string => grouping.format(n);

/** A column whose numbers are labels, not amounts: a year or an identifier, written without separators
 *  ("2018", never "2,018"). By its name's words (fiscal_year, CustomerKey, order_id), or whole numbers
 *  from `low` to `high` that all read as years (1800 to 2200). The server's twin: analysis_cards.is_label_column. */
const LABEL_WORDS = new Set(["year", "yr", "fy", "id", "key", "code", "zip", "postcode", "sku"]);
export function isLabelColumn(column: string, low?: unknown, high?: unknown): boolean {
  const words = column.replace(/([a-z0-9])([A-Z])/g, "$1 $2").toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  if (words.some((w) => LABEL_WORDS.has(w) || w.endsWith("year"))) return true;
  const yearish = (v: unknown): boolean => typeof v === "number" && Number.isInteger(v) && v >= 1800 && v <= 2200;
  return yearish(low) && yearish(high);
}
/** A label's number as its digits (anything else as given, for the caller's own formatting). */
export const plainNumber = (v: unknown): string => (typeof v === "number" ? (Number.isInteger(v) ? String(v) : String(Number(v.toFixed(2)))) : String(v ?? ""));

/** A count with its word, the one way every page says it: "1 row", "1,204 rows" (`many` for a word whose
 *  plural is not its word and an s). */
export const plural = (n: number, word: string, many = `${word}s`): string => `${formatCount(n)} ${n === 1 ? word : many}`;

/** A moment as every page shows it: "21 Nov 2026, 14:02" in the system's own words. An ISO text, epoch
 *  milliseconds or a Date; text that is not a date is shown as it is, and nothing as "". */
export function dateTime(at: string | number | Date | null | undefined): string {
  if (at === null || at === undefined || at === "") return "";
  const date = at instanceof Date ? at : new Date(at);
  return Number.isNaN(date.getTime()) ? String(at) : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

// ===== context menus (right-click) =====

/** A menu entry: [icon, words, action], or "-" for a rule. A fourth part says why the entry cannot
 * be used now: it shows disabled, with that reason as its tooltip. */
export type MenuItem = [string, string, () => void, string?] | "-";

/** What every right-click menu adds at its end while beta mode is on ("Leave a note…": betaNotes.ts),
 * read as the menu is drawn; null when beta mode is off. */
export interface MenuExtra {
  icon: string;
  label: string;
  run: () => void;
}
let menuExtras: (() => MenuExtra[]) | null = null;

export function setMenuExtras(extras: (() => MenuExtra[]) | null): void {
  menuExtras = extras;
}

export const extraMenuItems = (): MenuExtra[] => menuExtras?.() ?? [];

/** One drag of a handle (a splitter, a grip): what every drag-to-resize shares. */
export interface DragOptions {
  /** As the pointer goes down: measure here. Answering false: no drag (the handle is off). */
  start?: (down: PointerEvent) => void | false;
  /** The pointer's distance from where it went down, with the event itself. */
  move: (dx: number, dy: number, event: PointerEvent) => void;
  /** Once it lets go, or the drag is cancelled. */
  end?: () => void;
  /** A class worn while it drags, by `on` (default: the handle). */
  dragging?: string;
  on?: HTMLElement;
  /** Keep the pointer's press from handlers further out (a grip inside something that itself drags). */
  stop?: boolean;
}

/** Drag-to-resize, once (the craft review of 2026-11-22: nine hand-written copies): the handle captures the
 *  pointer, so the drag follows it over frames and out of the window; `move` hears the distance from where
 *  it went down; letting go or a cancelled pointer ends it, always, and the listeners go with it. The keys
 *  stay each handle's own (they differ: a width, a fraction, a grid's cells). */
export function dragResize(handle: HTMLElement, options: DragOptions): void {
  handle.addEventListener("pointerdown", (down) => {
    if (down.button !== 0 && down.pointerType === "mouse") return;
    if (options.start?.(down) === false) return;
    down.preventDefault();
    if (options.stop) down.stopPropagation();
    try {
      handle.setPointerCapture(down.pointerId);
    } catch {
      // a pointer that is already gone: the drag ends on the next event
    }
    const worn = options.on ?? handle;
    if (options.dragging) worn.classList.add(options.dragging);
    const moved = (event: PointerEvent): void => options.move(event.clientX - down.clientX, event.clientY - down.clientY, event);
    const up = (): void => {
      if (options.dragging) worn.classList.remove(options.dragging);
      handle.removeEventListener("pointermove", moved);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
      options.end?.();
    };
    handle.addEventListener("pointermove", moved);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  });
}

/** A menu at the pointer, kept inside the window; arrow keys move, Escape closes. */
export function showMenu(x: number, y: number, label: string, items: MenuItem[]): void {
  document.querySelector(".menu")?.remove();
  const extra = extraMenuItems().map((e): MenuItem => [e.icon, e.label, e.run]);
  if (extra.length) items = items.length ? [...items, "-", ...extra] : extra;
  const menu = h(
    "div",
    { class: "menu context-menu", role: "menu", "aria-label": label },
    h("div", { class: "menu-label" }, label),
    ...items.map((item) =>
      item === "-"
        ? h("div", { class: "menu-rule", role: "separator" })
        : h("button", { type: "button", role: "menuitem", disabled: Boolean(item[3]), title: item[3], onclick: () => { menu.remove(); item[2](); } }, icon(item[0]), item[1]),
    ),
  );
  // A modal dialog makes the rest of the page inert: a menu opened from one lives inside it (as toasts do).
  ([...document.querySelectorAll<HTMLDialogElement>("dialog[open]")].pop() ?? document.body).append(menu);
  menu.style.left = `${Math.max(8, Math.min(x, window.innerWidth - menu.offsetWidth - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(y, window.innerHeight - menu.offsetHeight - 8))}px`;
  (menu.querySelector("button:not(:disabled)") as HTMLButtonElement | null)?.focus();
  setTimeout(() => {
    const away = (event: Event): void => {
      if (!menu.contains(event.target as Node)) {
        menu.remove();
        document.removeEventListener("mousedown", away);
        document.removeEventListener("contextmenu", away);
      }
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("contextmenu", away);
  });
  menu.addEventListener("keydown", (event) => {
    const buttons = [...menu.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "Escape") menu.remove();
    else if (event.key === "ArrowDown") buttons[(at + 1) % buttons.length]?.focus();
    else if (event.key === "ArrowUp") buttons[(at - 1 + buttons.length) % buttons.length]?.focus();
    else return;
    event.preventDefault();
  });
}
