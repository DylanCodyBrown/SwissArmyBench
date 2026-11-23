// appKeys.js: the desktop app's own keys (the classic desktopApp.ts and gridCommands.ts mountAppKeys). The shell's
// script puts window.sabApp on every page it shows; there the browser's keys are the app's: Ctrl+W closes a tab
// (the window when none is left), Ctrl+T and Ctrl+N make a new one, Ctrl+Tab and Ctrl+Shift+Tab go round them,
// Ctrl+Shift+T reopens the last closed table. In a browser those keys stay the browser's: nothing is installed.

const shell = () => (window.sabApp && window.sabApp.app === true ? window.sabApp : null);

/** A key event as the app's keys name it: "Ctrl+W", "Ctrl+Shift+Tab". */
function appKey(e) {
  const key = e.key.length === 1 ? e.key.toUpperCase() : e.key;
  return [e.ctrlKey || e.metaKey ? "Ctrl" : "", e.altKey ? "Alt" : "", e.shiftKey ? "Shift" : "", key].filter(Boolean).join("+");
}

const KEYS = new Set(["Ctrl+W", "Ctrl+T", "Ctrl+N", "Ctrl+Tab", "Ctrl+Shift+Tab", "Ctrl+Shift+T"]);

export function install(listener) {
  if (!shell()) return null;
  const heard = (event) => {
    if (event.defaultPrevented) return;
    const key = appKey(event);
    if (!KEYS.has(key)) return;
    event.preventDefault();
    listener.invokeMethodAsync("Key", key);
  };
  document.addEventListener("keydown", heard);
  return { stop: () => document.removeEventListener("keydown", heard) };
}

/** The window this page is in, closed as its close button would (the page is asked first). */
export function closeWindow() {
  shell()?.close();
}
