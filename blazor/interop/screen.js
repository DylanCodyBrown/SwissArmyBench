// screen.js: what this window shows, read from the page for the agent's app_screen (the owner, 2026-11-27).
//
// Names only, never a value: titles, labels, numbers and states are read; never a cell's text, an output, a line of
// code or a field's value (the server's shape, domain/screen.py, has no place for one either). The read is a handful
// of selectors a few times a second, and it tells C# (Layout/ScreenReporter) only when what it read changed, so a
// page that is typed in pays nothing for it.

const LOOK_MS = 400;
const RESTS_MS = 120;
const MOST = 40;

const shown = (element) => element instanceof HTMLElement && (element.offsetParent !== null || getComputedStyle(element).position === "fixed");
const words = (text) => (text ?? "").replace(/\s+/g, " ").trim();
const all = (selector) => [...document.querySelectorAll(selector)].filter(shown).slice(0, MOST);
const labels = (selector, label) => [...new Set(all(selector).map(label).map(words).filter(Boolean))];

/** A dialog's title: its label, the element that labels it, else its heading. */
function title(dialog) {
  const by = dialog.getAttribute("aria-labelledby");
  return dialog.getAttribute("aria-label") ?? (by ? document.getElementById(by)?.textContent : null) ?? dialog.querySelector("h1, h2, h3")?.textContent ?? "";
}

/** The editors on screen (codeEditor.js lists them): the cursor of the one with the keys, else the one last in. */
function editors() {
  const seen = [...(window.sabScreenEditors ?? [])].filter((e) => shown(e.host)).map((e) => e.read());
  if (seen.length === 0) return {};
  const front = seen.find((e) => e.focused) ?? seen.filter((e) => e.at > 0).sort((a, b) => b.at - a.at)[0];
  const read = { problems: seen.reduce((sum, e) => sum + e.problems, 0) };
  if (front) {
    read.cursor = { line: front.line, column: front.column };
    if (front.from !== front.to) read.selection = { from_line: front.from, to_line: front.to };
  }
  return read;
}

/** A notebook's cells: how many, the one in focus, and each one on screen with its number, kind, name and state. */
function notebook() {
  const cells = [...document.querySelectorAll("section.wb-cell[data-number], section.wb-tcell[data-number]")].filter(shown);
  if (cells.length === 0) return null;
  const state = (cell) => {
    if (cell.classList.contains("running")) return "running";
    const run = words(cell.querySelector(".wb-cell-number")?.textContent).replace(/[[\]\s]/g, "");
    return run === "!" ? "failed" : run ? "ran" : cell.classList.contains("wb-tcell") ? "table" : "not run";
  };
  const visible = cells
    .filter((cell) => {
      const box = cell.getBoundingClientRect();
      return box.bottom > 0 && box.top < innerHeight;
    })
    .slice(0, MOST)
    .map((cell) => ({
      number: Number(cell.dataset.number),
      kind: [...cell.classList].find((c) => c.startsWith("kind-"))?.slice(5) ?? "",
      name: cell.querySelector(".wb-cell-name")?.value ?? "",
      state: state(cell),
    }));
  const read = { cells: cells.length, visible };
  const focused = cells.find((cell) => cell.classList.contains("selected"));
  if (focused) read.focused = Number(focused.dataset.number);
  return read;
}

/** The Settings page: its sections by their headings, and the one the focus is in (else the first on screen). */
function settings() {
  const sections = all(".settings-page fieldset").filter((box) => box.querySelector(":scope > legend"));
  if (sections.length === 0) return null;
  const name = (box) => words(box.querySelector(":scope > legend").textContent);
  const inView = (box) => {
    const at = box.getBoundingClientRect();
    return at.bottom > 0 && at.top < innerHeight;
  };
  const front = sections.find((box) => box.contains(document.activeElement)) ?? sections.find(inView);
  return { sections: sections.map(name), ...(front ? { section: name(front) } : {}) };
}

/** What the window shows that every page says the same way. */
export function read() {
  const page = location.pathname.replace(/^\/blazor\/?/, "");
  const state = {
    window: window.name,
    page,
    address: page + location.search,
    title: document.title,
    width: innerWidth,
    height: innerHeight,
    focused: document.hasFocus() && document.visibilityState === "visible",
    dialogs: labels("[role=dialog], [role=alertdialog]", title),
    menus: labels("[role=menu]", (menu) => menu.getAttribute("aria-label") ?? ""),
    panes: labels(".dock-pane[aria-label]", (pane) => pane.getAttribute("aria-label")),
    errors: labels(".error-note .error-note-what, .wb-err .wb-err-type", (note) => note.textContent),
    notices: labels(".toast", (toast) => toast.firstChild?.textContent ?? ""),
    ...editors(),
  };
  const cells = notebook();
  if (cells) state.notebook = cells;
  const boxes = settings();
  if (boxes) state.settings = boxes;
  for (const key of ["dialogs", "menus", "panes", "errors", "notices"]) if (state[key].length === 0) delete state[key];
  return state;
}

/** Watch the page: `listener.Seen(json)` when what `read` gives changed (a look every LOOK_MS, at once when the
 *  window takes or loses the focus, and once the hands rest after a click or a key). Returns what stops watching. */
export function watch(listener) {
  let last = "";
  const look = () => {
    let now;
    try {
      now = JSON.stringify(read());
    } catch {
      return; // a page half drawn: the next look reads it
    }
    if (now === last) return;
    last = now;
    listener.invokeMethodAsync("Seen", now).catch(() => {});
  };
  const timer = setInterval(look, LOOK_MS);
  const events = ["focus", "blur", "resize"];
  for (const name of events) window.addEventListener(name, look);
  document.addEventListener("visibilitychange", look);
  // A click or a key usually changes what shows (a dialog, the cursor's line): one look once the hands rest,
  // never one a keystroke (each key puts the look off again).
  let resting = 0;
  const soon = () => {
    clearTimeout(resting);
    resting = setTimeout(look, RESTS_MS);
  };
  const hands = ["pointerup", "keyup"];
  for (const name of hands) document.addEventListener(name, soon, { capture: true, passive: true });
  look();
  return {
    stop() {
      clearInterval(timer);
      clearTimeout(resting);
      for (const name of events) window.removeEventListener(name, look);
      for (const name of hands) document.removeEventListener(name, soon, { capture: true });
      document.removeEventListener("visibilitychange", look);
    },
  };
}
