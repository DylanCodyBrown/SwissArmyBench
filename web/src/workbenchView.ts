/**
 * workbenchView.ts: how a Workbench page shows its code, apart from what the code is: the code's own zoom
 * and full screen. Moved out of workbenchPage.ts along its own headings (the craft review of 2026-11-22),
 * unchanged; neither knows a document. [WIRE]
 *
 *   [ZOOM]  codeZoom: Ctrl + wheel and Ctrl+= / Ctrl+- / Ctrl+0 over the documents size the code alone (8 to
 *           40 px), per page, remembered in this browser; the page's own zoom (zoom.ts) leaves [data-own-zoom]
 *           alone (the owner, 2026-11-21: "Can the blade ide be zoomable"; the same on this page)
 *   [FULL]  fullScreen: the tabs and the editor fill the window (the rail, the explorer, the panels gone),
 *           remembered for the session, per page; Escape leaves it when nothing else took the key; the
 *           desktop app's F11 asks the page first (the owner, 2026-11-21: "the ide pane should be
 *           fullscreenable")
 */
import { windowFullScreen } from "./desktopApp";

export const BASE_FONT = 13;
const MIN_FONT = 8;
const MAX_FONT = 40;

/** A code size kept inside what the editors take (8 to 40 px, whole). */
export const clampFont = (px: number): number => Math.min(MAX_FONT, Math.max(MIN_FONT, Math.round(px)));

/** The size one step up or down from `now` (by: 1 or -1): a step is 1 px, 2 px from 20 px on. */
export const steppedFont = (now: number, by: number): number => clampFont(now + by * (now >= 20 ? 2 : 1));

/** The code's own zoom over `source`. `apply`: the editors take the size. The answer sets a size and gives
 *  the one in use. */
export function codeZoom(page: string, source: HTMLElement, apply: (px: number) => void): (px: number) => number {
  const key = `wb-font:${page}`;
  let codeFont = (() => {
    try {
      return Math.min(MAX_FONT, Math.max(MIN_FONT, Number(localStorage.getItem(key)) || BASE_FONT));
    } catch {
      return BASE_FONT;
    }
  })();
  function setCodeFont(px: number): number {
    codeFont = clampFont(px);
    try {
      localStorage.setItem(key, String(codeFont));
    } catch {
      /* storage blocked */
    }
    apply(codeFont);
    return codeFont;
  }
  if (codeFont !== BASE_FONT) setCodeFont(codeFont);
  source.dataset.ownZoom = "";
  const stepCode = (by: number): void => void setCodeFont(steppedFont(codeFont, by));
  source.addEventListener(
    "wheel",
    (e) => {
      if (!(e.ctrlKey || e.metaKey) || (e.target as Element | null)?.closest?.(".code-ide")) return; // a blade's own zoom
      e.preventDefault();
      e.stopPropagation();
      stepCode(e.deltaY < 0 ? 1 : -1);
    },
    { capture: true, passive: false },
  );
  source.addEventListener(
    "keydown",
    (e) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey || (e.target as Element | null)?.closest?.(".code-ide")) return;
      const by = zoomKey(e.key);
      if (by === null) return;
      e.preventDefault();
      e.stopPropagation();
      if (by === 0) setCodeFont(BASE_FONT);
      else stepCode(by);
    },
    true,
  );
  return setCodeFont;
}

/** What a zoom key asks for with Ctrl held: 1 bigger, -1 smaller, 0 back to the base size; null: not one. */
export function zoomKey(key: string): 1 | -1 | 0 | null {
  return key === "=" || key === "+" ? 1 : key === "-" ? -1 : key === "0" ? 0 : null;
}

export interface FullScreen {
  /** Full screen on, off, or the other way (no argument); what it is now. */
  toggle: (on?: boolean) => boolean;
  on: () => boolean;
}

/** Full screen for a Workbench page. `changed`: the page draws its controls again. */
export function fullScreen(page: string, changed: () => void): FullScreen {
  const key = `wb-fullscreen:${page}`;
  let full = false;
  function toggle(on?: boolean): boolean {
    full = on ?? !full;
    document.body.classList.toggle("wb-full", full);
    windowFullScreen(full); // in the desktop app, the window too (PySide6's showFullScreen / back)
    try {
      sessionStorage.setItem(key, full ? "1" : "0");
    } catch {
      /* storage refused: it lasts until a reload */
    }
    changed();
    window.requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
    return full;
  }
  try {
    if (sessionStorage.getItem(key) === "1") toggle(true);
  } catch {
    /* nothing kept */
  }
  // The desktop app's F11 (its own key, server/desktop_shell.py) asks the page first: the IDE alone, and the window.
  Object.defineProperty(window, "sabFullScreen", { value: () => toggle(), configurable: true });
  document.addEventListener("keydown", (e) => {
    // Escape leaves full screen when nothing else took it (a member list, a dialog, a menu).
    if (e.key !== "Escape" || !full || e.defaultPrevented || document.querySelector("dialog[open], .wb-menu, .suggest-widget.visible")) return;
    toggle(false);
  });
  return { toggle, on: () => full };
}
