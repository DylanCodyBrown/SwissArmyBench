/**
 * areaPage.ts: a page of the rail's own over any page and window (the owner, 2026-11-16: "clicking the
 * rail should land on a page not open a form"). [SHARED]
 *
 *   [PAGE]    Settings and Connections are pages, not dialogs: the whole width right of the rail, the
 *             page under them kept as it was (its grids, its kernels). Their address is the layer's
 *             (open=settings, open=connections: nav.ts), so Back, Forward, a reload and every old address
 *             work as they did; leaving is a rail click or Back (no Close).
 *   [PARTS]   a heading row (the title, then the page's own actions on the right), the body, and a foot
 *             for a form's buttons (empty: hidden).
 *
 * The page is a <section>, not a <dialog>: nothing is modal, and the rail stays usable beside it.
 */
import { h } from "./dom";

/** A page's element: closed by its own close() (a "close" event, as a dialog's), removed with it. */
export type PageElement = HTMLElement & { close(): void; open: boolean };

export interface AreaPage {
  element: PageElement;
  /** The heading row's right side: the page's own actions (Add connection, ...). */
  actions: HTMLElement;
  body: HTMLElement;
  foot: HTMLElement;
  close: () => void;
  /** The heading's words (a connection's detail names it). */
  setHeading: (title: string, ...more: (Node | string | null)[]) => void;
}

/** Open the page `key` titled `title`, over the page under it (one of each key at a time). */
export function openAreaPage(key: string, title: string): AreaPage {
  document.querySelector<PageElement>(`.area-page[data-page="${key}"]`)?.close();
  const heading = h("h1", { class: "area-page-title" }, title);
  const actions = h("div", { class: "area-page-actions" });
  const body = h("div", { class: "area-page-body" });
  const foot = h("div", { class: "area-page-foot" });
  const section = h(
    "section",
    { class: "area-page", "data-page": key, role: "region", "aria-label": title, tabindex: -1 },
    h("header", { class: "area-page-head" }, heading, actions),
    body,
    foot,
  );
  const element = Object.assign(section, {
    open: true,
    close: (): void => {
      if (!element.open) return;
      element.open = false;
      element.remove();
      document.body.classList.toggle("area-page-shown", !!document.querySelector(".area-page"));
      element.dispatchEvent(new Event("close"));
    },
  }) as PageElement;
  document.body.append(element);
  document.body.classList.add("area-page-shown");
  return {
    element,
    actions,
    body,
    foot,
    close: () => element.close(),
    setHeading: (words, ...more) => heading.replaceChildren(words, ...more.filter((m): m is Node | string => m !== null)),
  };
}
