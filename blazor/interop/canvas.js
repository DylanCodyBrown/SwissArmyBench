// canvas.js: the Canvas's few browser parts the C# side cannot reach (the classic canvasPage.ts's own listeners):
// the pointer captured while a block is dragged (its moves reach the board even outside it), the board's place on
// the screen, the page's keys (F5 never reloads the canvas; the run group's keys anywhere), Ctrl+wheel zoom, and a
// window opened at once on the user's click (a window opened after a wait is blocked).

/** The pointer captured by an element: its moves and its release come to it until it lets go. */
export function capture(element, pointerId) {
  try {
    element.setPointerCapture(pointerId);
  } catch {
    /* the pointer is gone already */
  }
}

/** An element's box on the screen (the board's: a pointer's place in the page's pixels). */
export function rect(element) {
  const r = element.getBoundingClientRect();
  return { left: r.left, top: r.top, width: r.width, height: r.height };
}

/** The viewport's width (Fit). */
export function width(element) {
  return element.clientWidth;
}

const typing = (target) => !!target?.closest?.("input, textarea, select, [contenteditable], .monaco-editor");

/** The page's keys, told to C# by name: F5, Ctrl+F5, Ctrl+Shift+F5, Ctrl+Shift+E anywhere; the others when no box
 *  has the typing focus (Ctrl+Z, Ctrl+Y, Ctrl+= and -, Ctrl+0, Delete, Backspace, Escape, Insert, the arrows). */
export function keys(dotnet) {
  const listener = (e) => {
    const ctrl = e.ctrlKey || e.metaKey;
    const key = e.key;
    if (key === "F11" && !ctrl && !e.altKey) {
      e.preventDefault();
      dotnet.invokeMethodAsync("FullScreen", null).catch(() => {});
      return;
    }
    // Escape always leaves full screen, from a box too.
    if (key === "Escape" && document.body.classList.contains("cvs-full")) {
      dotnet.invokeMethodAsync("FullScreen", false).catch(() => {});
      return;
    }
    const always = key === "F5" || (ctrl && e.shiftKey && key.toLowerCase() === "e");
    if (!always && (typing(e.target) || e.defaultPrevented)) {
      if (key === "Escape") dotnet.invokeMethodAsync("Key", key, ctrl, e.shiftKey, e.altKey, true).catch(() => {});
      return;
    }
    const handled = always
      || (ctrl && !e.altKey && ["z", "y", "=", "+", "-", "0"].includes(key.toLowerCase()))
      || ["Delete", "Backspace", "Escape", "Insert", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(key);
    if (!handled) return;
    if (key !== "Escape" && key !== "Insert") e.preventDefault();
    dotnet.invokeMethodAsync("Key", key, ctrl, e.shiftKey, e.altKey, false).catch(() => {});
  };
  document.addEventListener("keydown", listener);
  // The desktop app's F11 is the page's while it is open (the shell asks window.sabFullScreen first); the browser's
  // own Escape out of full screen asks with false.
  const full = (on) => dotnet.invokeMethodAsync("FullScreen", on === false ? false : null).catch(() => {});
  window.sabFullScreen = full;
  return {
    stop: () => {
      document.removeEventListener("keydown", listener);
      if (window.sabFullScreen === full) delete window.sabFullScreen;
    },
  };
}

/** Ctrl+wheel over the viewport zooms (told to C# as a factor). */
export function wheel(element, dotnet) {
  const listener = (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    dotnet.invokeMethodAsync("Wheel", e.deltaY < 0 ? 1.1 : 1 / 1.1).catch(() => {});
  };
  element.addEventListener("wheel", listener, { passive: false });
  return { stop: () => element.removeEventListener("wheel", listener) };
}

/** A window opened now, on the click (about:blank until its address is known), and later pointed or closed. */
export function openWindow(name, features) {
  const opened = window.open("about:blank", name, features);
  return opened
    ? { go: (url) => { opened.location.href = url; }, close: () => opened.close(), open: () => true }
    : null;
}

/** A page of the app in a window of its own (the Widgets window, the analyzer). */
export function openPage(url, name, features) {
  return window.open(url, name, features) !== null;
}

/** A gallery card's preview asked for once the card is in view (told to C# once: Seen). */
export function seen(element, dotnet) {
  // A card already gone (the pane closed as it drew: full screen at once): nothing to watch.
  if (!(element instanceof Element)) return { stop: () => {} };
  if (typeof IntersectionObserver === "undefined") {
    dotnet.invokeMethodAsync("Seen").catch(() => {});
    return { stop: () => {} };
  }
  const watch = new IntersectionObserver((entries) => {
    if (!entries.some((e) => e.isIntersecting)) return;
    watch.disconnect();
    dotnet.invokeMethodAsync("Seen").catch(() => {});
  });
  watch.observe(element);
  return { stop: () => watch.disconnect() };
}

/** The Widgets window's keys (the classic widgetPage.ts): Ctrl+B the list, Ctrl+Alt+B Properties, F5 Preview,
 *  Escape back to the code; told to C# by name. */
export function widgetKeys(dotnet) {
  const listener = (e) => {
    const ctrl = e.ctrlKey || e.metaKey;
    if (ctrl && e.key.toLowerCase() === "b") {
      e.preventDefault();
      dotnet.invokeMethodAsync("Key", "b", e.altKey).catch(() => {});
    } else if (e.key === "F5") {
      e.preventDefault();
      // In the editor, Monaco's own F5 runs it (its action): told once.
      if (!e.target?.closest?.(".monaco-editor")) dotnet.invokeMethodAsync("Key", "F5", false).catch(() => {});
    } else if (e.key === "Escape") {
      dotnet.invokeMethodAsync("Key", "Escape", false).catch(() => {});
    }
  };
  document.addEventListener("keydown", listener);
  // The desktop app's F11 is the page's while it is open (the shell asks window.sabFullScreen first); the browser's
  // own Escape out of full screen asks with false.
  const full = (on) => dotnet.invokeMethodAsync("FullScreen", on === false ? false : null).catch(() => {});
  window.sabFullScreen = full;
  return {
    stop: () => {
      document.removeEventListener("keydown", listener);
      if (window.sabFullScreen === full) delete window.sabFullScreen;
    },
  };
}
