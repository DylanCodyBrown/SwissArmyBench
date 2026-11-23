/**
 * workbenchKeys.ts: the keys the Workbench's window takes wherever the focus is. Moved out of
 * workbenchPage.ts along its own heading (the craft review of 2026-11-22), unchanged. [WIRE]
 *
 *   [WINDOW]  F5, F1, F6, Ctrl+S, Ctrl+O, Ctrl+1 to 3, Ctrl+\ ...: each a command by its name
 *             (workbenchCommands.ts runCommand), before an editor or the browser sees the key
 *   [APP]     in the desktop app the browser's keys are the window's too (Ctrl+W, Ctrl+T, Ctrl+Tab)
 *   [DEBUG]   while the script in front is being debugged: VS Code's F5, F10, F11, Shift+F11, Shift+F5, F9
 *   [UNDO]    Ctrl+Z outside an editor: a notebook's cell delete or move comes back
 */
import { inApp } from "./desktopApp";
import { errorHere } from "./errorNote";
import { runCommand } from "./workbenchCommands";
import type { Doc } from "./workbenchPage";
import type { CodePage } from "./workbenchPages";

/** The window's keys, for this page (Scripts has its search) and the document in front. */
export function windowKeys(page: CodePage, current: () => Doc | null): void {
  /** The keys the window takes wherever the focus is (before an editor or the browser sees them). */
  const WINDOW_KEYS: Record<string, string> = {
    F5: "run.primary",
    F1: "help.atCursor",
    F6: "view.nextPane",
    "Shift+F6": "view.previousPane",
    "Ctrl+Shift+P": "palette",
    "Ctrl+S": "file.save",
    "Ctrl+Shift+S": "file.saveAs",
    "Ctrl+O": "file.open",
    "Ctrl+Shift+E": "view.explorer",
    F11: "view.fullScreen",
    "Ctrl+B": "view.files",
    ...(page === "scripts" ? { "Ctrl+Shift+F": "search.scripts" } : {}),
    "Ctrl+1": "view.source",
    "Ctrl+2": "console.focus",
    "Ctrl+3": "view.variables",
    "Ctrl+Shift+1": "view.focus",
    "Ctrl+\\": "group.splitRight",
    "Ctrl+Alt+PageDown": "doc.next",
    "Ctrl+Alt+PageUp": "doc.previous",
  };
  /** In the desktop app the browser's keys are the window's too (desktopApp.ts); in a browser, the browser's. */
  const APP_KEYS: Record<string, string> = inApp()
    ? { "Ctrl+W": "file.closeTab", "Ctrl+T": "file.newNotebook", "Ctrl+N": "file.newNotebook", "Ctrl+Tab": "doc.next", "Ctrl+Shift+Tab": "doc.previous", "Ctrl+Shift+T": "tabs.reopen" }
    : {};

  function keyName(e: KeyboardEvent): string {
    const key = /^Digit\d$/.test(e.code) ? e.code.slice(5) : e.key.length === 1 ? e.key.toUpperCase() : e.key;
    return [e.ctrlKey || e.metaKey ? "Ctrl" : "", e.altKey ? "Alt" : "", e.shiftKey ? "Shift" : "", key].filter(Boolean).join("+");
  }

  document.addEventListener(
    "keydown",
    (e) => {
      // The debugger's keys (VS Code's) while the script in front is paused; F9 a breakpoint at the cursor.
      const debugging = current()?.debug;
      const debugKeys: Record<string, () => void> = debugging?.paused()
        ? { F5: () => void debugging.step("continue"), F10: () => void debugging.step("over"), F11: () => void debugging.step("into"), "Shift+F11": () => void debugging.step("out"), "Shift+F5": () => void debugging.stop() }
        : debugging?.active()
          ? { "Shift+F5": () => void debugging.stop() }
          : {};
      if (debugging) {
        debugKeys.F9 = () => debugging.toggleAtCursor();
        if (!debugging.active()) debugKeys["Ctrl+Shift+D"] = () => void debugging.start().catch((err: Error) => errorHere(err));
      }
      const debugKey = debugKeys[keyName(e)];
      if (debugKey) {
        e.preventDefault();
        e.stopPropagation();
        debugKey();
        return;
      }
      const id = WINDOW_KEYS[keyName(e)] ?? APP_KEYS[keyName(e)];
      if (!id) return;
      // A blade's tab is an IDE of its own (codeIde.ts): its Save and Run take Ctrl+S and F5 there.
      if ((id === "file.save" || id === "run.primary") && (e.target as Element | null)?.closest?.(".code-ide")) return;
      // F5 would reload the window (stopping every kernel), F1 open the browser's help: the window's own.
      e.preventDefault();
      e.stopPropagation();
      if (document.querySelector(".wb-palette-shade") && id !== "palette") return;
      void runCommand(id).catch((error: Error) => errorHere(error));
    },
    true,
  );
  document.addEventListener("keydown", (e) => {
    // Ctrl+Z outside an editor: a notebook's cell delete or move comes back (inside, the editor's own undo).
    const inEditor = (e.target as HTMLElement | null)?.closest?.(".monaco-editor, input, textarea, select");
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z" && !inEditor) {
      // Never the browser's own undo: with the keyboard on a button it took back the last text typed
      // into some editor, whole and unseen (an HTML cell's edit, in the instant after Edit HTML).
      e.preventDefault();
      current()?.notebook?.undo();
    }
  });
}
