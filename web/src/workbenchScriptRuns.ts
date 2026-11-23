/**
 * workbenchScriptRuns.ts: a script arranged and run: the server asked for the script as it should be
 * (POST /workbench/tables/arrange: the Tables group, the cells' numbers, the outline), a table's cell run,
 * a cell gone to by its number, Run file, the statement at the cursor (or the selection), the top to here
 * and here to the end. A part of workbenchScript.ts's scriptView (workbenchScriptState.ts says how the
 * parts fit). [VIEW]
 *
 * ROUTING: POST /workbench/tables/arrange, POST /workbench/statement
 */
import { api } from "./api";
import { errorHere } from "./errorNote";
import type { ScriptOutline } from "./lazy/codeEditor";
import { dedent, nextCodeLine, safeBlock, sharedIndent } from "./scriptCells";
import { htmlNames } from "./workbenchHtml";
import { htmlAt, runHtmlCell, syncHtml } from "./workbenchScriptHtml";
import { draw, type Script, tableStarts, textOf, variableOf } from "./workbenchScriptState";
import type { TableLine } from "./workbenchTables";

/** A statement's lines as the server reads them (null: a blank line or a comment). */
interface Statement {
  start: number | null;
  end: number | null;
  next: number | null;
}

export const relevant = (sc: Script): boolean => sc.tableInfos.length > 0 || /^# ?(%%|region Tables)/m.test(textOf(sc));

/** Ask the server for the script as it should be, and where its cells are. `move` false while the
 *  user types: nothing is added or moved; only the tables' cells and the uses lines follow. */
export async function arrange(sc: Script, move: boolean): Promise<void> {
  if (!sc.editor) return;
  if (!relevant(sc)) {
    if (sc.outline.cells.length || sc.outline.region) {
      sc.outline = { region: null, cells: [] };
      sc.tableLines = [];
      sc.editor.setOutline(null);
      draw(sc);
    }
    sc.outlineVersion = sc.version;
    syncHtml(sc);
    return;
  }
  const mine = ++sc.asked;
  const at = sc.version;
  try {
    const done = await api<{ text: string; tables: TableLine[]; outline: ScriptOutline }>("/workbench/tables/arrange", "POST", { kind: "script", text: sc.editor.value(), tables: sc.tableInfos.map((t) => t.name), move });
    if (mine !== sc.asked) return; // a newer question is on its way
    if (at !== sc.version) return void (move ? arrange(sc, true) : typedSoon(sc)); // typed meanwhile: ask again
    sc.applying = true;
    sc.quietly = sc.quietly && sc.tableInfos.length === 0;
    try {
      sc.editor.replaceText(done.text);
    } finally {
      sc.applying = false;
      sc.quietly = false;
    }
    sc.outline = done.outline;
    sc.outlineVersion = sc.version; // the text just written is the one the outline describes
    sc.tableLines = done.tables;
    sc.editor.setOutline(sc.outline);
    draw(sc);
    syncHtml(sc);
    if (sc.foldOnce && sc.outline.region) {
      sc.foldOnce = false;
      // Once Monaco has the folds: each table, then the group (a file's group starts folded).
      setTimeout(() => {
        sc.editor?.fold([...tableStarts(sc).values()]);
        if (sc.outline.region) sc.editor?.fold([sc.outline.region[0]]);
      }, 600);
    }
  } catch {
    /* the server is away: the text stays as it is */
  }
}

export function typedSoon(sc: Script): void {
  if (sc.quiet !== null) window.clearTimeout(sc.quiet);
  sc.quiet = window.setTimeout(() => {
    sc.quiet = null;
    void arrange(sc, false);
  }, 600);
}

/** The table whose read-only cell this line is in (its marker or its code). */
export const tableAt = (sc: Script, line: number): string | null => sc.outline.cells.find((c) => c.role === "transformations" && line >= c.line && line <= c.end)?.table ?? null;

/** Lines of the script as they run: a table's cell inside them goes through the kernel's safe run
 *  (client/table_cells.py), on the same lines, so it never transforms a transformed table. */
export function safeLines(sc: Script, start: number, end: number): string {
  if (!sc.editor) return "";
  return safeBlock(sc.editor.lines(start, end), start, end, sc.outline.cells, (table) => variableOf(sc, table));
}

export async function runTable(sc: Script, name: string): Promise<boolean> {
  const line = sc.tableLines.find((l) => l.name === name);
  if (!line) throw new Error(`This script has no table named ${name}.`);
  const ok = await sc.console.run({ code: line.code, kind: "table", table: variableOf(sc, name) }, `# ${name}: its transformations`);
  if (ok) sc.records.set(name, { code: line.code, at: new Date(), opened: false });
  draw(sc);
  return ok;
}

export function goTo(sc: Script, number: number, line?: number | null): boolean {
  const cell = sc.outline.cells.find((c) => c.number === number);
  if (!cell || !sc.editor) {
    errorHere(`There is no cell ${number} in this script.`);
    return false;
  }
  if (cell.grouped && sc.outline.region) sc.editor.unfold([sc.outline.region[0], cell.line]);
  sc.editor.reveal(cell.line + (line ?? 0));
  if (line) sc.editor.moveTo(cell.line + line);
  return true;
}

export async function statementAt(sc: Script, line: number): Promise<Statement> {
  try {
    return await api<Statement>("/workbench/statement", "POST", { code: textOf(sc), line });
  } catch {
    return { start: line, end: line, next: line + 1 };
  }
}

export async function runFile(sc: Script): Promise<void> {
  const code = textOf(sc);
  if (!code.trim()) return sc.console.note("Empty script");
  if (!(await sc.file.saveFirst())) return;
  const path = sc.file.path();
  const name = path ? (path.split(/[\\/]/).pop() ?? path) : null;
  const lines = code.split("\n").length;
  const ran = sc.tableLines.map((l) => ({ name: l.name, code: l.code }));
  // Script mode: the run settings' arguments (sys.argv).
  const args = sc.hooks.arguments?.() ?? "";
  const ok = await sc.console.run({ code, kind: "file", path, ...(args ? { args } : {}) }, name ? `%run ${name}${args ? ` ${args}` : ""}` : `# the script (${lines} line${lines === 1 ? "" : "s"}, not saved)`, { kind: "file", path });
  // The file ran to its end: so did its tables' cells (each the safe way, in the kernel).
  if (ok) for (const table of ran) sc.records.set(table.name, { code: table.code, at: new Date(), opened: false });
  // And its HTML cells' names are read from what the run left.
  if (ok) for (const held of [...sc.htmlCells.values()]) if (htmlNames(held.cell.html ?? "").length) await runHtmlCell(sc, held);
  draw(sc);
  if (ok) void arrange(sc, true);
}

/** The whole statement at the cursor, then the cursor on to the next (the selection's lines when
 *  there is one). The cursor moves at once: pressing again queues the next statement. */
export async function runSelection(sc: Script): Promise<void> {
  if (!sc.editor) return;
  const chosen = sc.editor.selected();
  if (chosen) {
    const part = chosen.startLine === chosen.endLine && chosen.text.trim() !== chosen.wholeLines.trim();
    const code = part ? chosen.text.trim() : dedent(safeLines(sc, chosen.startLine, chosen.endLine));
    const indent = part ? Math.max(0, chosen.wholeLines.indexOf(code)) : sharedIndent(chosen.wholeLines);
    await sc.console.run({ code }, code.trimEnd(), { kind: "lines", start: chosen.startLine, indent });
    return;
  }
  const line = sc.editor.cursorLine();
  // In a table's read-only cell: its Run.
  const table = tableAt(sc, line);
  if (table) return void (await runTable(sc, table));
  // In an HTML cell: its Run (its names filled, its design drawn).
  const held = sc.outlineVersion === sc.version ? htmlAt(sc, line) : undefined;
  if (held) return void (await runHtmlCell(sc, held));
  const found = await statementAt(sc, line);
  if (found.start === null || found.end === null) {
    // A blank line or a comment: on to the next line with code.
    sc.editor.moveTo(nextCodeLine(sc.editor.value(), line));
    return;
  }
  const block = sc.editor.lines(found.start, found.end);
  const code = dedent(block);
  sc.editor.moveTo(found.next ?? Math.min(found.end + 1, sc.editor.lineCount()));
  await sc.console.run({ code }, code.trimEnd(), { kind: "lines", start: found.start, indent: sharedIndent(block) });
}

/** The script's top to the end of the cursor's statement, or from its start to the end. */
export async function runPart(sc: Script, to: boolean): Promise<void> {
  if (!sc.editor) return;
  const line = sc.editor.cursorLine();
  const found = await statementAt(sc, line);
  const last = sc.editor.lineCount();
  const code = to ? safeLines(sc, 1, found.end ?? line) : safeLines(sc, found.start ?? line, last);
  if (!code.trim()) return sc.console.note("Nothing to run");
  await sc.console.run({ code }, to ? `# lines 1 to ${found.end ?? line}` : `# lines ${found.start ?? line} to ${last}`, { kind: "lines", start: to ? 1 : (found.start ?? line), indent: 0 });
}
