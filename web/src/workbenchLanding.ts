/**
 * workbenchLanding.ts: the Workbench's page for a kind of document, where the rail's Notebooks, Scripts
 * and Apps land (the owner, 2026-11-16: "every time I click the rail it pops out a box from the icon to
 * create something get rid of that its duplicated behavior we should only create things from the panel";
 * "clicking the rail should land on a page not open a form"). [WIRE]
 *
 *   [ADDRESS] /workbench?kind=notebook&view=list: a reload, Back and Forward come back to it; a card's
 *             click is a move (pushed), so Back returns here from the document.
 *   [CARDS]   the page is its cards only. New and Open… are in the Workbench's top bar beside Save and
 *             Save as… (the owner, 2026-11-16: "new script and open should be in the bar above along with
 *             the save and save as"): workbenchPage.ts draws them for the kind on show.
 *   [TABLES]  Scripts and Notebooks first show each open table's transformations, read-only (the owner,
 *             2026-11-16: "The first thing I did was go to scripts thinking that is where I could see the
 *             transformations"): its name, its steps in plain words. A click opens its read-only cell.
 *   [DOCS]    that kind's documents: the open ones first (in front marked, unsaved marked), then the
 *             project's (with no project open: this computer's recent ones of that kind). A click brings
 *             an open one forward, or opens the file.
 *   [KINDS]   Notebooks in a project: under Data notebook (data.ipynb) and App notebooks (every other),
 *             after the Transformations (the owner, 2026-11-16: "data notebooks and app notebooks");
 *             a notebook outside the project under Notebooks. Each card's icon is its kind's.
 *
 * The groups and the empty state hide while the page shows; the rest of the Workbench (the top row,
 * the Data panel, kernels) stays as it was.
 */
import { api } from "./api";
import { h, icon } from "./dom";
import { emptyState } from "./emptyState";
import { type Kind, kindIcon, notebookRole, notebookWord } from "./kindColours";

export interface LandingDoc {
  title: string;
  path: string | null;
  dirty: boolean;
  front: boolean;
}

/** An open table's transformations, as its card shows them. */
export interface LandingTable {
  name: string;
  /** Each step in plain words ("Keep rows where amount is greater than 5"). */
  steps: string[];
  problem: string | null;
}

export interface LandingHost {
  /** That kind's documents open in this window, in their order. */
  openDocs: (kind: Kind) => LandingDoc[];
  /** A card's click: the open document brought forward, or the file opened. */
  choose: (kind: Kind, doc: LandingDoc) => void;
  /** The open tables' transformations (Scripts and Notebooks show them). */
  tables: () => Promise<LandingTable[]>;
  /** A table card's click: its transformations, read-only. */
  showTable: (name: string) => void;
  /** A new document of that kind (the top bar's New). */
  start: (kind: Kind) => void;
}

/** An empty kind's one sentence (emptyState.ts). */
const EMPTY_LINES: Record<Kind, string> = {
  notebook: "A notebook mixes Python, DuckDB SQL and notes in cells, run one at a time, beside your open tables.",
  script: "A script is plain Python run top to bottom, here or on a schedule, with your tables and connections.",
  app: "A Streamlit app is pages of blocks, each one a notebook cell, played live and exported to run anywhere.",
};

export const KIND_TITLES: Record<Kind, { title: string; one: string }> = {
  notebook: { title: "Notebooks", one: "notebook" },
  script: { title: "Scripts", one: "script" },
  app: { title: "Apps", one: "Streamlit app" },
};

/** The Notebooks page's groups: each notebook's role, its heading. */
const KINDS: ["data" | "app" | "", string][] = [
  ["data", "Data notebook"],
  ["app", "App notebooks"],
  ["", "Notebooks"],
];

const baseName = (path: string): string => path.split(/[\\/]/).pop() ?? path;
const folderOf = (path: string): string => path.slice(0, Math.max(0, path.length - baseName(path).length - 1));

/** SEAM (project-scope): the documents of a kind that are not open here. Today the Workbench's recent
 *  files of that kind; the open project's documents list replaces this one function. */
export async function projectDocuments(kind: Kind): Promise<string[]> {
  // The open project's documents of this kind (everything is the project's, 2026-11-16); with no project
  // open, this computer's recent ones, as the connections and blades fall back to this computer's.
  const listed = await api<{ project: unknown; documents: { path: string; full?: string; made?: boolean }[] }>(`/project/documents?kind=${kind}`);
  if (listed.project) return listed.documents.filter((d) => !d.made).map((d) => d.full ?? d.path);
  const home = await api<{ recent: { path: string; exists: boolean }[] }>("/workbench/home");
  return home.recent.filter((r) => r.exists && kindOfPath(r.path) === kind).map((r) => r.path);
}

const kindOfPath = (path: string): Kind | null => (/\.stapp\.json$/i.test(path) ? "app" : /\.ipynb$/i.test(path) ? "notebook" : /\.py$/i.test(path) ? "script" : null);

export interface Landing {
  element: HTMLElement;
  /** The kind on show (null: none). */
  kind: () => Kind | null;
  show: (kind: Kind) => void;
  hide: () => void;
  /** Draw the page on show again (an icon or a table changed). */
  redraw: () => void;
}

export function mountLanding(host: LandingHost): Landing {
  const element = h("section", { class: "wb-landing", hidden: true, role: "region" });
  let shown: Kind | null = null;
  let serial = 0;

  const card = (k: Kind, doc: LandingDoc, open: boolean): HTMLElement =>
    h(
      "li",
      {},
      h(
        "button",
        {
          type: "button",
          class: `wb-landing-card km-${k}${doc.front ? " front" : ""}`,
          title: doc.path ?? doc.title,
          "data-path": doc.path ?? "",
          onclick: () => host.choose(k, doc),
        },
        h("span", { class: "wb-landing-icon", title: k === "notebook" ? notebookWord(doc.path) : "", "data-icon": kindIcon(k, doc.path) }, icon(kindIcon(k, doc.path))),
        h(
          "span",
          { class: "wb-landing-text" },
          h("strong", {}, doc.title, doc.dirty ? h("span", { class: "wb-landing-dirty", title: "Not saved", "aria-label": "Not saved" }, " ●") : null),
          h("span", { class: "wb-landing-where" }, doc.path ? folderOf(doc.path) : ""),
        ),
        open ? h("span", { class: "badge" }, "Open") : null,
      ),
    );

  const draw = async (k: Kind): Promise<void> => {
    const mine = ++serial;
    const words = KIND_TITLES[k];
    const opened = host.openDocs(k);
    const list = h("ul", { class: "wb-landing-cards", "aria-label": words.title }, ...opened.map((d) => card(k, d, true)));
    const all: [LandingDoc, boolean][] = opened.map((d) => [d, true]);
    const tablesHost = h("div", { class: "wb-landing-tables" });
    element.className = `wb-landing km-${k}`;
    element.setAttribute("aria-label", words.title);
    element.replaceChildren(
      h(
        "div",
        { class: "wb-landing-main" },
        h("h1", {}, h("span", { class: "wb-landing-title-icon", "aria-hidden": "true" }, icon(kindIcon(k))), words.title),
        tablesHost,
        list,
      ),
    );
    const [more, tables] = await Promise.all([projectDocuments(k).catch(() => [] as string[]), k === "app" ? Promise.resolve([]) : host.tables().catch(() => [] as LandingTable[])]);
    if (mine !== serial || shown !== k) return;
    // No Transformations cards (the owner, 2026-11-17: "notebooks also has data panel on the left and
    // transformations which is not needed"): a table's transformations live in data.ipynb and data.py.
    void tables;
    const openPaths = new Set(opened.map((d) => d.path).filter(Boolean));
    for (const path of more.filter((p) => !openPaths.has(p))) {
      const doc = { title: baseName(path), path, dirty: false, front: false };
      all.push([doc, false]);
      list.append(card(k, doc, false));
    }
    const kinds = k === "notebook" ? KINDS.map(([role, title]) => [role, title, all.filter(([d]) => notebookRole(d.path) === role)] as const) : [];
    if (kinds.some(([role, , docs]) => role && docs.length)) {
      // In a project: the data notebook, then the app notebooks (and any notebook from outside it).
      list.replaceWith(
        ...kinds.flatMap(([role, title, docs]) =>
          docs.length || role === "data"
            ? [
                h("h2", { class: "wb-landing-section", "data-role": role || "plain" }, title),
                docs.length
                  ? h("ul", { class: `wb-landing-cards wb-landing-${role || "plain"}`, "aria-label": title }, ...docs.map(([d, open]) => card(k, d, open)))
                  : h("p", { class: "empty-note" }, "No data notebook yet"),
              ]
            : [],
        ),
      );
      return;
    }
    if (tables.length) tablesHost.append(h("h2", { class: "wb-landing-section" }, `Your ${words.title.toLowerCase()}`));
    if (!list.childElementCount)
      list.replaceWith(
        emptyState({
          icon: kindIcon(k),
          line: EMPTY_LINES[k],
          action: { label: `New ${words.one}`, icon: "plus", run: () => host.start(k) },
          // The made-up tables, then a new document beside them (its Tables group lists them).
          sample: k !== "app",
          afterSample: () => host.start(k),
        }),
      );
  };

  return {
    element,
    kind: () => shown,
    show: (k) => {
      shown = k;
      element.hidden = false;
      void draw(k);
    },
    hide: () => {
      shown = null;
      serial++;
      element.hidden = true;
    },
    redraw: () => {
      if (shown) void draw(shown);
    },
  };
}
