/**
 * structurePaths.ts: a structure's paths as words and as code, its search, and which files are a structure's
 * tab. Pure functions, no page: tested as the page runs them (tests/test_structure_paths.py, with the server's
 * own cases in tests/golden/structure_code.json). [SHARED]
 *
 *   [PATH]    $.orders[3].lines (domain/structures.py format_path)
 *   [CODE]    the Python that reaches a node from the file's value: data["orders"][3]["lines"] (code_of)
 *   [FIND]    where words stand in keys and values, in the document's order (search)
 *   [FILES]   a .json, .yaml, .yml, .xml or .toml file opens as a structure's tab beside the code; an app's
 *             canvas, a workbook design, an old app canvas and the app's .sab/ state never (workbench_pages.py)
 */

export type Value = null | boolean | number | string | Value[] | { [key: string]: Value };
export type Part = string | number;

const NAME = /^[A-Za-z_][A-Za-z0-9_-]*$/;

export function pathText(parts: Part[]): string {
  let out = "$";
  for (const p of parts) out += typeof p === "number" ? `[${p}]` : NAME.test(p) ? `.${p}` : `[${JSON.stringify(p)}]`;
  return out;
}

/** The Python that reaches the node at `parts` from the file's value (`variable`, by default data). */
export function accessCode(parts: Part[], variable = "data"): string {
  let out = variable;
  for (const p of parts) out += typeof p === "number" ? `[${p}]` : `[${JSON.stringify(p)}]`;
  return out;
}

const wordsOf = (node: Value): string => (typeof node === "string" ? node : JSON.stringify(node));

/** Every node whose key or value holds `words` (in any case), in the document's order (at most `limit`). */
export function matchPaths(value: Value, words: string, limit = 1000): Part[][] {
  const said = words.trim().toLowerCase();
  const found: Part[][] = [];
  if (!said) return found;
  const walk = (node: Value, parts: Part[], key: string | null): void => {
    if (found.length >= limit) return;
    const hit = (key !== null && key.toLowerCase().includes(said)) || (node === null || typeof node !== "object" ? wordsOf(node).toLowerCase().includes(said) : false);
    if (hit) found.push(parts);
    if (Array.isArray(node)) node.forEach((v, i) => walk(v, [...parts, i], null));
    else if (node !== null && typeof node === "object") for (const [k, v] of Object.entries(node)) walk(v, [...parts, k], k);
  };
  walk(value, [], null);
  return found;
}

/** Whether a file opens as a structure's tab beside the code, and the endings a structure's file may have:
 *  the server's rule, applied (pageRules.ts; this file keeps no list). */
export { isStructurePath, structureSuffixes } from "./pageRules";

/** A structure's format from its file's suffix (yml is YAML). */
export function formatOfPath(path: string): "json" | "yaml" | "xml" | "toml" | null {
  const name = path.toLowerCase();
  if (name.endsWith(".json")) return "json";
  if (name.endsWith(".yaml") || name.endsWith(".yml")) return "yaml";
  if (name.endsWith(".xml")) return "xml";
  if (name.endsWith(".toml")) return "toml";
  return null;
}

/** "line 3, column 5" in a parse error's words: where it is (column 1 when it names none). */
export function errorPlace(message: string): { line: number; column: number } | null {
  const found = /line (\d+)(?:, column (\d+))?/.exec(message);
  return found ? { line: Number(found[1]), column: found[2] ? Number(found[2]) : 1 } : null;
}
