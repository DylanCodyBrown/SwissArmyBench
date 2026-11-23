/**
 * workbenchScriptErrors.ts: a script's errors (workbenchErrors.ts's panel in the console): a frame of a run
 * as this script's line (the file's own, or the lines that ran with the indent the dedent took off), the
 * failing expression marked, the fixes, a frame's go-to (another file opens). A part of workbenchScript.ts's
 * scriptView (workbenchScriptState.ts says how the parts fit). [VIEW]
 */
import { sameFile } from "./scriptCells";
import type { RunOrigin } from "./workbenchConsole";
import { type ErrorDetail, type Frame, problemsFor, yourFrame } from "./workbenchErrors";
import type { ErrorHooks } from "./workbenchOutputs";
import type { Script } from "./workbenchScriptState";

/** A frame of this run, as this script's line and the columns the dedent took off (null: elsewhere). */
export const placeIn = (sc: Script, origin: RunOrigin | undefined, detail: ErrorDetail) => (frame: Pick<Frame, "where" | "cell" | "file" | "line">): { line: number; colShift: number } | null => {
  if (!origin) return null;
  if (origin.kind === "file") {
    const path = origin.path ?? sc.file.path();
    const mine = frame.where === "file" && (sameFile(frame.file, path) || (!origin.path && /[\\/]untitled\.py$/.test(frame.file ?? "")));
    return mine ? { line: frame.line, colShift: 0 } : null;
  }
  const numbers = detail.chain.flatMap((e) => e.frames.map((f) => f.cell ?? 0).concat(e.syntax?.cell ?? 0));
  return frame.where === "cell" && frame.cell === Math.max(...numbers) ? { line: origin.start + frame.line - 1, colShift: origin.indent } : null;
};

export function errorHooks(sc: Script, origin?: RunOrigin): ErrorHooks {
  let shown: ErrorDetail | null = null;
  const yours = (): { line: number; colShift: number } | null => {
    const entry = shown?.chain[shown.chain.length - 1];
    const frame = yourFrame(entry) ?? (entry?.syntax ? ({ where: entry.syntax.where, cell: entry.syntax.cell, file: entry.syntax.file, line: entry.syntax.line } as Frame) : null);
    return frame && shown ? placeIn(sc, origin, shown)(frame) : null;
  };
  return {
    shown: (detail) => {
      shown = detail;
      sc.editor?.setProblems(problemsFor(detail, placeIn(sc, origin, detail)));
    },
    fix: (fix) => {
      if (fix.kind === "replace" || fix.kind === "import") {
        if (!sc.editor?.applyFix(fix, fix.kind === "import" ? 1 : (yours()?.line ?? sc.editor.cursorLine()))) sc.console.note(`${fix.target ?? "That"} is no longer in the script.`);
        else sc.editor.focus(); // back in the code, ready to run it again
        return;
      }
      if (fix.kind === "cell" && fix.text) {
        // A line to put in the script (reading a Dataverse table instead of SQL): copied.
        const text = fix.text;
        void navigator.clipboard.writeText(text).then(() => sc.console.note(`Copied: ${text}`), () => sc.console.note(text));
        return;
      }
      if (!sc.hooks.fix?.(fix)) sc.console.note(fix.kind === "define" ? `Nothing defines ${fix.name}` : "Fix not available here");
    },
    goTo: (frame) => {
      const at = shown ? placeIn(sc, origin, shown)(frame) : null;
      if (at && sc.editor) {
        sc.editor.reveal(at.line, (frame.col ?? 1) + at.colShift);
        return true;
      }
      if (frame.where === "file" && frame.file && sc.hooks.openFile) {
        sc.hooks.openFile(frame.file, frame.line);
        return true;
      }
      return false;
    },
    openGrid: sc.hooks.openGrid,
    openResult: sc.hooks.openResult,
  };
}
