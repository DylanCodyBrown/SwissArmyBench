/**
 * desktopApp.ts: is this page in the desktop app (PySide6, server/desktop_shell.py), and the window it is in.
 * [FUNCTION]
 *
 * The shell's script puts `window.sabApp` on every page it shows. In the app the browser's keys are the app's
 * (the owner, 2026-11-18: "Agreed"): Ctrl+W closes a tab (the window when none is left), Ctrl+T and Ctrl+N
 * make a new one, Ctrl+Tab and Ctrl+Shift+Tab go round them, Ctrl+Shift+T reopens the last closed table. In a
 * browser those keys stay the browser's, so the pages take them only here.
 */

interface SabApp {
  app: true;
  close: () => void;
}

function shell(): SabApp | null {
  const found = (window as unknown as { sabApp?: SabApp }).sabApp;
  return found && found.app === true ? found : null;
}

/** True in the desktop app's windows; false in a browser (and VS Code's). */
export function inApp(): boolean {
  return shell() !== null;
}

/** The window this page is in, closed as its close button would (the page is asked first). */
export function closeWindow(): void {
  shell()?.close();
}

/** A key event as the app's keys name it: "Ctrl+W", "Ctrl+Shift+Tab", "Ctrl+Shift+T". */
export function appKey(e: KeyboardEvent): string {
  const key = e.key.length === 1 ? e.key.toUpperCase() : e.key;
  return [e.ctrlKey || e.metaKey ? "Ctrl" : "", e.altKey ? "Alt" : "", e.shiftKey ? "Shift" : "", key].filter(Boolean).join("+");
}
