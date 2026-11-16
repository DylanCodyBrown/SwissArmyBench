/**
 * workbenchLanding.ts: the Workbench's page for a kind of document, where the rail's Notebooks, Scripts
 * and Apps land (the owner, 2026-11-16: "every time I click the rail it pops out a box from the icon to
 * create something get rid of that its duplicated behavior we should only create things from the panel";
 * "clicking the rail should land on a page not open a form"). [WIRE]
 *
 *   [ADDRESS] /workbench?kind=notebook&view=list: a reload, Back and Forward come back to it; a card's
 *             click is a move (pushed), so Back returns here from the document.
 *   [PANEL]   the page's own panel: New (a notebook, a script, a Streamlit app) and Open….
 *   [CARDS]   that kind's documents: the open ones first (in front marked, unsaved marked), then the
 *             project's (today: the recent files of that kind, behind `projectDocuments`, the seam the
 *             project-scoped list replaces). A click brings an open one forward, or opens the file.
 *
 * The groups and the empty state hide while the page shows; the rest of the Workbench (the top row,
 * the Data panel, kernels) stays as it was.
 */
import { api } from "./api";
import { button, h, icon } from "./dom";
import { type Kind, kindIcon } from "./kindColours";

export interface LandingDoc {
  title: string;
  path: string | null;
  dirty: boolean;
  front: boolean;
}

export interface LandingHost {
  /** That kind's documents open in this window, in their order. */
  openDocs: (kind: Kind) => LandingDoc[];
  /** A card's click: the open document brought forward, or the file opened. */
  choose: (kind: Kind, doc: LandingDoc) => void;
  /** New: that kind's start (a group's "+" makes the same). */
  start: (kind: Kind) => (() => void) | null;
  openFile: () => void;
}

const WORDS: Record<Kind, { title: string; one: string }> = {
  notebook: { title: "Notebooks", one: "notebook" },
  script: { title: "Scripts", one: "script" },
  app: { title: "Apps", one: "Streamlit app" },
};

const baseName = (path: string): string => path.split(/[\\/]/).pop() ?? path;
const folderOf = (path: string): string => path.slice(0, Math.max(0, path.length - baseName(path).length - 1));

/** SEAM (project-scope): the documents of a kind that are not open here. Today the Workbench's recent
 *  files of that kind; the open project's documents list replaces this one function. */
export async function projectDocuments(kind: Kind): Promise<string[]> {
  // The open project's documents of this kind (everything is the project's, 2026-11-16).
  const listed = await api<{ project: unknown; documents: { path: string; made?: boolean }[] }>(`/project/documents?kind=${kind}`);
  return listed.documents.filter((d) => !d.made).map((d) => d.path);
}

export interface Landing {
  element: HTMLElement;
  /** The kind on show (null: none). */
  kind: () => Kind | null;
  show: (kind: Kind) => void;
  hide: () => void;
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
        h("span", { class: "wb-landing-icon", "aria-hidden": "true" }, icon(kindIcon(k, doc.path))),
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
    const words = WORDS[k];
    const opened = host.openDocs(k);
    const list = h("ul", { class: "wb-landing-cards", "aria-label": words.title }, ...opened.map((d) => card(k, d, true)));
    const start = host.start(k);
    element.className = `wb-landing km-${k}`;
    element.setAttribute("aria-label", words.title);
    element.replaceChildren(
      h(
        "aside",
        { class: "wb-landing-panel", "aria-label": `${words.title} panel` },
        h("h1", {}, h("span", { class: "wb-landing-title-icon", "aria-hidden": "true" }, icon(kindIcon(k))), words.title),
        start ? button(`New ${words.one}`, start, { icon: "plus", class: "primary" }) : null,
        button("Open…", host.openFile, { icon: "folder" }),
      ),
      h("div", { class: "wb-landing-main" }, list),
    );
    let more: string[] = [];
    try {
      more = await projectDocuments(k);
    } catch {
      /* the server will say so on the next action */
    }
    if (mine !== serial || shown !== k) return;
    const openPaths = new Set(opened.map((d) => d.path).filter(Boolean));
    for (const path of more.filter((p) => !openPaths.has(p))) list.append(card(k, { title: baseName(path), path, dirty: false, front: false }, false));
    if (!list.childElementCount) list.replaceWith(h("p", { class: "empty-note" }, `No ${words.title.toLowerCase()} yet`));
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
  };
}
