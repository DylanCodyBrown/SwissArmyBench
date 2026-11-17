/**
 * connectionSql.ts: a connection's tables named in DuckDB SQL (`SELECT * FROM [Finance Captive].Sales`):
 * which connections a query names (a SQL cell's head shows them), and completion for them: the
 * connections first, then a connection's datasets or schemas and its tables (each as SQL names it).
 *
 * ROUTING: GET /connections/{name}/tree?load=0 (kept in the page by connection: the catalog is never
 *          loaded just to complete; the Connections page's tree loads it)
 */
import { api } from "./api";
import type { Suggestion } from "./lazy/codeEditor";
import type { Tree } from "./connectionTree";

const escape = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The connections a query names as tables' first part: `[Name].`, `"Name".`, or `Name.` (a plain name). */
export function namedConnections(source: string, names: string[]): string[] {
  return names.filter((n) => {
    const plain = /^[A-Za-z_]\w*$/.test(n) ? `|(?<![\\w."\\]])${escape(n)}` : "";
    return new RegExp(`(?:\\[${escape(n)}\\]|"${escape(n)}"${plain})\\s*\\.`, "i").test(source);
  });
}

const trees = new Map<string, Promise<Tree | null>>();

function treeOf(name: string): Promise<Tree | null> {
  const key = name.toLowerCase();
  let found = trees.get(key);
  if (!found) {
    found = api<Tree>(`/connections/${encodeURIComponent(name)}/tree?load=0`).catch(() => null);
    trees.set(key, found);
    // A catalog still loading: asked again next time.
    void found.then((t) => {
      if (!t || !t.groups.length) trees.delete(key);
    });
  }
  return found;
}

/** What to offer at the cursor of a DuckDB query: after `[` the connections, after `[Name].` its
 *  datasets or schemas and tables (as SQL names them). Nothing elsewhere. */
export async function connectionSuggestions(text: string, offset: number, names: string[]): Promise<Suggestion[]> {
  const before = text.slice(0, offset);
  const opened = /\[([^\]\n[]*)$/.exec(before);
  if (opened) {
    const typed = opened[1]!.toLowerCase();
    const start = offset - opened[0].length;
    // The editor closed the bracket as it was typed: the insert takes it too.
    const end = text[offset] === "]" ? offset + 1 : offset;
    return names
      .filter((n) => n.toLowerCase().startsWith(typed) || n.toLowerCase().includes(typed))
      .map((n) => ({ label: `[${n}]`, insert: `[${n}].`, kind: "module", detail: "connection", start, end, filter: `[${n}]` }));
  }
  const dotted = /(\[([^\]\n]+)\]|"([^"\n]+)")\s*\.\s*([^\s,()]*)$/.exec(before);
  if (!dotted) return [];
  const name = names.find((n) => n.toLowerCase() === (dotted[2] ?? dotted[3] ?? "").toLowerCase());
  if (!name) return [];
  const tree = await treeOf(name);
  if (!tree) return [];
  const typed = dotted[4]!;
  const start = offset - typed.length;
  const head = `[${tree.connection}].`;
  const out: Suggestion[] = [];
  const seen = new Set<string>();
  for (const g of tree.groups) {
    const group = g.schema ? (/^[A-Za-z_]\w*$/.test(g.schema) ? g.schema : `"${g.schema}"`) : "";
    if (group && tree.groups.length > 1 && !seen.has(group)) {
      seen.add(group);
      out.push({ label: group, insert: `${group}.`, kind: "module", detail: tree.group, start, end: offset, filter: group });
    }
    for (const t of g.tables) {
      const rest = t.sql.startsWith(head) ? t.sql.slice(head.length) : t.table;
      if (seen.has(rest)) continue;
      seen.add(rest);
      out.push({ label: rest, insert: rest, kind: "struct", detail: g.schema || "table", start, end: offset, filter: rest });
    }
  }
  return out.filter((s) => (s.filter ?? s.label).toLowerCase().includes(typed.replace(/"/g, "").toLowerCase()));
}
