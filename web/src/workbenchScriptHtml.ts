/**
 * workbenchScriptHtml.ts: a script's HTML cells (`# %% [7] [html] height=320`: the HTML as one string that
 * does nothing): each one's design under its marker while the cursor is elsewhere, its lines put away, its
 * state, its run (its `{{ name }}` filled from the kernel), the pane's height written on its marker. A part
 * of workbenchScript.ts's scriptView (workbenchScriptState.ts says how the parts fit). [VIEW]
 */
import { withHeight } from "./scriptCells";
import { changedNames, designPane, fillHtml, htmlNames, runHtml } from "./workbenchHtml";
import type { HtmlReport } from "./workbenchNotebookState";
import { draw, type HtmlCell, htmlStateOf, isActive, type Script } from "./workbenchScriptState";

export function drawHtmlState(sc: Script, held: HtmlCell): void {
  held.pane.setState(htmlStateOf(held), held.cell.problem ? [held.cell.problem] : held.notes);
  draw(sc);
}

/** Draw a cell's design from its HTML as it is now, its names filled with what its last run gave. */
export async function drawDesign(sc: Script, held: HtmlCell): Promise<void> {
  const html = held.cell.html;
  if (html === null || html === undefined) return drawHtmlState(sc, held);
  const mine = ++held.drawn;
  let filled: { html: string; missing: string[]; notes: string[] };
  try {
    filled = await fillHtml(html, held.run?.values ?? {});
  } catch {
    filled = { html, missing: [], notes: ["The server is away: the design shows as written."] };
  }
  if (mine !== held.drawn) return;
  held.notes = [...filled.missing.map((n) => `{{ ${n} }} was not found in the kernel.`), ...filled.notes];
  held.drawnFrom = html;
  held.pane.show(filled.html);
  drawHtmlState(sc, held);
}

/** The marker of an HTML cell with its pane's height on it (`height=320`), or without one. */
export function writeHeight(sc: Script, held: { cell: HtmlCell["cell"] }, height: number | null): void {
  if (!sc.editor) return;
  const next = withHeight(sc.editor.value(), held.cell.number, held.cell.line, height);
  if (next !== null) sc.editor.replaceText(next);
}

/** Which lines are put away and which designs show, from the outline (only a fresh one: lines are
 *  never hidden by an outline of an older text). */
export function layoutHtml(sc: Script): void {
  if (!sc.editor || sc.outlineVersion !== sc.version) return;
  const zones: { id: string; afterLine: number; height: number; element: HTMLElement }[] = [];
  const hidden: [number, number][] = [];
  for (const held of sc.htmlCells.values()) {
    const cell = held.cell;
    const active = isActive(sc, held);
    const drawn = cell.html !== null && cell.html !== undefined && cell.html.trim() !== "";
    held.pane.element.hidden = active || (!drawn && !cell.problem);
    if (active || (!drawn && !cell.problem)) continue;
    zones.push({ id: held.key, afterLine: cell.line, height: held.room, element: held.pane.element });
    // A cell that is not one string yet keeps its lines in view, to be mended.
    if (drawn && (cell.html_end ?? 0) > cell.line) hidden.push([cell.line + 1, cell.html_end!]);
  }
  const now = JSON.stringify([zones.map((z) => [z.id, z.afterLine, z.height]), hidden]);
  if (now === sc.laidOut) return;
  sc.laidOut = now;
  sc.editor.setHidden(hidden);
  sc.editor.setZones(zones);
  draw(sc);
}

/** The HTML cells as the outline has them: each keeps its pane and its last run by its number. */
export function syncHtml(sc: Script): void {
  const seen = new Set<string>();
  let unnumbered = 0;
  for (const cell of sc.outline.cells) {
    if (cell.kind !== "html") continue;
    const key = cell.number !== null ? `n${cell.number}` : `u${unnumbered++}`;
    seen.add(key);
    let held = sc.htmlCells.get(key);
    if (!held) {
      const made: HtmlCell = {
        key,
        cell,
        run: undefined,
        notes: [],
        drawnFrom: null,
        drawn: 0,
        room: 200,
        pane: designPane({ dark: sc.dark, height: cell.height ?? null, resized: (height) => writeHeight(sc, made, height), run: () => void runHtmlCell(sc, made) }),
      };
      made.pane.element.classList.add("in-script");
      new ResizeObserver(() => {
        const room = Math.ceil(made.pane.element.getBoundingClientRect().height);
        if (room && room !== made.room) {
          made.room = room;
          layoutHtml(sc);
        }
      }).observe(made.pane.element);
      sc.htmlCells.set(key, (held = made));
    }
    held.cell = cell;
    if ((cell.height ?? null) !== held.pane.height() && !held.pane.element.classList.contains("dragging")) held.pane.setHeight(cell.height ?? null);
    if (cell.html !== held.drawnFrom && cell.html !== null && cell.html !== undefined) void drawDesign(sc, held);
    else drawHtmlState(sc, held);
  }
  for (const [key, held] of sc.htmlCells) {
    if (seen.has(key)) continue;
    held.pane.dispose();
    sc.htmlCells.delete(key);
  }
  layoutHtml(sc);
}

/** Run an HTML cell: plain HTML only draws; with names, each is read from the kernel's variables. */
export async function runHtmlCell(sc: Script, held: HtmlCell): Promise<boolean> {
  const html = held.cell.html;
  if (html === null || html === undefined) {
    sc.console.note(held.cell.problem ?? "This HTML cell holds no HTML yet.");
    return false;
  }
  if (!htmlNames(html).length) {
    await drawDesign(sc, held);
    return true;
  }
  let said = "";
  try {
    const done = await runHtml(sc.kernel, html, (item) => {
      if (item.output_type === "error") said = `${String(item.ename ?? "Error")}: ${String(item.evalue ?? "")}`;
    });
    if (done.run) held.run = done.run;
    else sc.console.note(`The HTML cell did not run${said ? `: ${said}` : "."}`);
    held.drawnFrom = null;
    await drawDesign(sc, held);
    return done.ok;
  } catch (e) {
    sc.console.note((e as Error).message);
    return false;
  }
}

export async function checkMarks(sc: Script): Promise<void> {
  const ran = [...sc.htmlCells.values()].filter((held) => held.run && held.run.code !== null);
  if (!ran.length) return;
  const changed = await changedNames(sc.kernel, ran.map((held) => held.run!));
  if (!changed) return;
  for (const held of ran) {
    const now = held.run ? changed.get(held.run) : undefined;
    if (!held.run || !now || now.join("\n") === held.run.changed.join("\n")) continue;
    held.run.changed = now;
    drawHtmlState(sc, held);
  }
}

export function htmlReport(held: HtmlCell): HtmlReport {
  const now = htmlStateOf(held);
  const html = held.cell.html ?? "";
  return { number: held.cell.number, index: held.cell.line, html, names: htmlNames(html), state: now.kind, label: now.label, height: held.cell.height ?? null, notes: held.cell.problem ? [held.cell.problem] : held.notes };
}
export function htmlByNumber(sc: Script, number: number): HtmlCell {
  const held = [...sc.htmlCells.values()].find((e) => e.cell.number === number);
  if (!held) throw new Error(`This script has no HTML cell ${number}.`);
  return held;
}
/** The HTML cell whose lines hold this line. */
export const htmlAt = (sc: Script, line: number): HtmlCell | undefined => [...sc.htmlCells.values()].find((e) => line >= e.cell.line && line <= Math.max(e.cell.html_end ?? e.cell.end, e.cell.line));

/** A kernel that starts (again) or stops: an HTML cell's names were that kernel's variables, so it has not
 *  run in the new one. */
export function forgetHtmlRuns(sc: Script): void {
  for (const held of sc.htmlCells.values()) {
    if (!held.run || held.run.code === null) continue;
    held.run = { ...held.run, code: null, at: null, changed: [] };
    drawHtmlState(sc, held);
  }
}
