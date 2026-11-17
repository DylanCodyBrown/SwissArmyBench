/**
 * workbenchIntel.ts: the editors' intelligence for every Python editor in the Workbench (a notebook's
 * cells, a script, the console) and SQL cells, asked of the server (services/intellisense.py). [WIRE]
 *
 *   MEMBER LIST   as you type and on Ctrl+Space: Jedi's names (the kernel's live ones once it has run),
 *                 each with its kind, its signature on the right and the documentation panel beside the
 *                 list; the app's names inside strings; a project module's name with its import added;
 *                 a function's required arguments as tab stops. Ranked by the server; what was chosen
 *                 lately comes first
 *   PARAMETER     on `(` and `,`: each signature (overloads with up and down), the current parameter bold
 *   INFO          with its own words from the docstring, the return type
 *   QUICK INFO    on hover: the signature or the variable's type, and the docstring
 *   LINT          400 ms after typing stops: squiggles (errors red, warnings yellow, unused faded), Ctrl+.
 *                 fixes; the status bar's count, and the list it opens; the agent reads the same
 *                 (workbench_problems)
 *
 * Each editor's requests carry its own id and a sequence number: the server skips one a newer request
 * from the same editor has overtaken, and the page drops an answer that comes back after a newer one.
 *
 * ROUTING: POST /workbench/intel/{complete,signature,hover,lint}; PUT /workbench/intel/problems
 */
import { api } from "./api";
import type { IntelProblem, Signatures, Suggestion } from "./lazy/codeEditor";
import type { Missing } from "./missingPackages";
import type { Kernel } from "./workbenchKernel";

/** What a request is asked with, beyond the text: the cells before and after (a notebook), the kernel,
 *  the document, its language and connection (a SQL cell). */
export interface IntelContext {
  notebook: boolean;
  before?: () => string[];
  after?: () => string[];
  language?: () => "python" | "sql" | "other";
  connection?: () => string | null;
  /** The problems list's place: the document and, in a notebook, the cell. */
  document: () => string;
  place?: () => string;
}

interface Item {
  label: string;
  module?: string;
  kind?: string;
  detail?: string;
  documentation?: string;
  snippet?: string;
  imports?: { line: number; col: number; end_line: number; end_col: number; text: string }[];
  sort?: string;
}

let editors = 0;

/** A long parameter list cut to fit the row (the documentation panel has it whole). */
const short = (text: string): string => (text.length > 48 ? `${text.slice(0, 47)}…)` : text);
const RECENT = "sab-intel-recent";

function recent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT) ?? "[]") as string[];
  } catch {
    return [];
  }
}

/** A completion was chosen: it comes first next time (in its group). */
export function chosen(label: string): void {
  try {
    const list = [label, ...recent().filter((l) => l !== label)].slice(0, 50);
    localStorage.setItem(RECENT, JSON.stringify(list));
  } catch {
    /* no storage: nothing remembered */
  }
}

const KIND: Record<string, string> = { instance: "variable", statement: "variable", param: "variable", struct: "table" };

/** One editor's intelligence: a completer, parameter info, the hover and the lint. */
export function pythonIntel(kernel: Kernel, context: IntelContext) {
  const editor = `e${++editors}`;
  let seq = 0;
  const latest: Record<string, number> = {};
  const body = (text: string, offset?: number): Record<string, unknown> => {
    const k = kernel.intel();
    return {
      text,
      offset,
      notebook: context.notebook,
      before: context.before?.() ?? [],
      after: context.after?.() ?? [],
      kernel: k.kernel,
      path: k.path,
      python: k.python,
      seq: ++seq,
      document: `${context.document()}${context.place ? `#${context.place()}` : ""}`,
      // The server keeps answers by the text itself (and the place): the same text asks Jedi once.
      version: 0,
    };
  };
  const ask = async <T>(kind: string, payload: Record<string, unknown>): Promise<T | null> => {
    const mine = payload.seq as number;
    latest[kind] = mine;
    try {
      // Superseded by kind: a completion asked after a lint does not overtake it.
      const send = (): Promise<T> => api<T>(`/workbench/intel/${kind}`, "POST", { ...payload, editor: `${editor}:${kind}` });
      let found = await send();
      // Late (Jedi's first look at a library, a cold start): it goes on in the server; asked once more,
      // the answer is quick.
      if ((found as { late?: boolean }).late && latest[kind] === mine) found = await send();
      return latest[kind] === mine ? found : null; // a newer one is on its way
    } catch {
      return null;
    }
  };
  return {
    /** The member list (null: the server could not say; the caller's own completer answers). */
    complete: async (text: string, offset: number): Promise<Suggestion[] | null> => {
      const found = await ask<{ items: Item[]; start: number; end: number; late?: boolean }>("complete", { ...body(text, offset), recent: recent() });
      if (!found || found.late) return null;
      return found.items.map((i) => ({
        label: i.label,
        // A function's parameters after its name; its return type, a variable's type or a module at the right.
        labelDetail: i.detail?.startsWith(`${i.label}(`) ? short(i.detail.slice(i.label.length).replace(/\s*->.*$/, "")) : undefined,
        description: i.detail?.startsWith(`${i.label}(`) ? (/->\s*(.+)$/.exec(i.detail)?.[1] ?? i.module ?? "") : i.detail && i.detail.length <= 40 ? i.detail : (i.module ?? ""),
        kind: KIND[i.kind ?? ""] ?? i.kind,
        detail: i.detail ?? "",
        documentation: i.documentation,
        snippet: i.snippet,
        edits: i.imports,
        sort: i.sort,
        start: found.start,
        end: found.end,
      }));
    },
    signature: async (text: string, offset: number): Promise<Signatures | null> => {
      const found = await ask<Signatures>("signature", body(text, offset));
      return found && found.signatures.length ? found : null;
    },
    hover: async (text: string, offset: number): Promise<string> => (await ask<{ hover: string }>("hover", body(text, offset)))?.hover ?? "",
    lint: async (text: string): Promise<IntelProblem[] | null> => {
      const language = context.language?.() ?? "python";
      if (language === "other") return [];
      const found = await ask<{ problems: IntelProblem[]; ruff?: { used: boolean; missing?: Missing } }>("lint", { ...body(text), language, connection: context.connection?.() ?? null });
      if (found?.ruff) ruffOffers.set(context.document(), found.ruff.used ? null : (found.ruff.missing ?? null));
      return found ? found.problems : null;
    },
  };
}

// ===== the problems every editor shows: the status bar's count, its list, and the agent's copy =====

export interface Shown {
  document: string;
  place: string;
  problems: IntelProblem[];
  reveal: (line: number, column: number) => void;
}

const shown = new Map<string, Shown>();
// Each document's Ruff: not in its Python (offered from the Problems list, never pressed on the user).
const ruffOffers = new Map<string, Missing | null>();

/** Ruff to offer for a document's Python (null: it is there, or nothing was checked yet). */
export function ruffOffer(document: string): Missing | null {
  return ruffOffers.get(document) ?? null;
}
const listeners: (() => void)[] = [];
const reporting = new Map<string, number>();

/** An editor's problems now (an empty list clears them). */
export function showProblems(key: string, entry: Shown | null): void {
  if (entry && entry.problems.length) shown.set(key, entry);
  else shown.delete(key);
  for (const l of listeners) l();
  const document = entry?.document ?? key.split("\u0000")[0]!;
  // The server keeps each document's problems for the agent (a moment after they settle).
  window.clearTimeout(reporting.get(document));
  reporting.set(
    document,
    window.setTimeout(() => {
      const problems = [...shown.values()].filter((s) => s.document === document).flatMap((s) => s.problems.map((p) => ({ ...p, place: s.place, fixes: undefined })));
      void api("/workbench/intel/problems", "PUT", { document, title: document.split(/[\\/]/).pop(), problems }).catch(() => undefined);
    }, 600),
  );
}

export function onProblems(listener: () => void): void {
  listeners.push(listener);
}

/** Every editor's problems, for one document (or all). */
export function problemsOf(document?: string): Shown[] {
  return [...shown.values()].filter((s) => document === undefined || s.document === document);
}
