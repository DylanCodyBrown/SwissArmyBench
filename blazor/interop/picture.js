// picture.js: a picture of this window for a beta note (the classic betaNotes.ts picture), drawn by html-to-image
// (the classic page's own package at the same version). The note's dialog is left out of it.
import { toPng } from "html-to-image";

export async function picture(skipSelector) {
  const skip = [...document.querySelectorAll(skipSelector)];
  return toPng(document.body, {
    width: window.innerWidth,
    height: window.innerHeight,
    pixelRatio: 1,
    cacheBust: false,
    backgroundColor: getComputedStyle(document.body).backgroundColor,
    filter: (node) => !(node instanceof Element) || !skip.some((s) => s === node),
  });
}

// The element a note is about (the classic betaNotes.ts describe): what was right-clicked last, described without
// its data (no cell's or editor's text, ever), kept for a minute so the menu's Leave a note… can name it.
const DATA_PLACES = ".ag-cell, .wb-output, .monaco-editor, pre, td, textarea, input, select, [contenteditable], .value-viewer, .sab-card-body, .wb-err";
const WORDY = "button, [role=button], [role=tab], [role=menuitem], [role=columnheader], .ag-header-cell, label, legend, summary, h1, h2, h3, h4, th";
const IMPLICIT = { BUTTON: "button", A: "link", INPUT: "textbox", TEXTAREA: "textbox", SELECT: "combobox", SUMMARY: "button", H1: "heading", H2: "heading", H3: "heading", H4: "heading", TABLE: "table", DIALOG: "dialog" };
const KEPT_MS = 60000;
let last = null;

function step(el) {
  let part = el.tagName.toLowerCase();
  if (el.id && /^[A-Za-z][\w-]{0,40}$/.test(el.id) && !/\d{3,}/.test(el.id)) part += `#${el.id}`;
  const classes = [...el.classList].filter((c) => /^[A-Za-z][\w-]{0,40}$/.test(c) && !/\d{3,}/.test(c)).slice(0, 3);
  if (classes.length) part += `.${classes.join(".")}`;
  const column = el.getAttribute("col-id");
  if (column) part += `[col-id="${column.slice(0, 60)}"]`;
  return part;
}

function cssPath(el) {
  const parts = [];
  for (let at = el; at && at !== document.body && parts.length < 6; at = at.parentElement) parts.unshift(step(at));
  return parts.join(" > ");
}

export function describe(el) {
  const target = el.closest(`${WORDY}, [role=gridcell], .ag-cell, [aria-label], [title], [role]`) ?? el;
  const data = target.closest(DATA_PLACES) !== null;
  const wordy = target.matches(WORDY);
  const name = data ? "" : target.getAttribute("aria-label") || target.getAttribute("title") || "";
  const text = data || !wordy ? "" : (target.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 80);
  const box = target.getBoundingClientRect();
  return {
    tag: target.tagName.toLowerCase(),
    role: target.getAttribute("role") ?? IMPLICIT[target.tagName] ?? (target.classList.contains("ag-cell") ? "gridcell" : ""),
    name: name.slice(0, 80),
    text,
    path: cssPath(target),
    box: { x: Math.round(box.left), y: Math.round(box.top), w: Math.round(box.width), h: Math.round(box.height) },
  };
}

const noticed = (event) => {
  if (event.target instanceof Element) last = { at: performance.now(), info: describe(event.target) };
};

/** Start keeping what is right-clicked (once a page). */
export function watch() {
  window.removeEventListener("contextmenu", noticed, true);
  window.addEventListener("contextmenu", noticed, true);
}

/** What was right-clicked within the last minute, or null. */
export function lastClicked() {
  return last && performance.now() - last.at < KEPT_MS ? last.info : null;
}
