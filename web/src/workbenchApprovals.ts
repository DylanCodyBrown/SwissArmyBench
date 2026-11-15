/**
 * workbenchApprovals.ts: approved outputs, the notebook as the test surface (docs/ideas.md, lineage
 * with values and approved outputs, 2026-11-15). [FUNCTION]
 *
 *   [APPROVE]  a cell's output marked approved (the cell's menu, the palette, the agent): the server
 *              takes a snapshot of its output records (domain/approvals.py), kept in the cell's
 *              metadata when the notebook is saved
 *   [CHANGED]  after a run, the output is compared with its approval: when it differs, the cell says
 *              "Changed since approved" in amber, and how (a text diff; a table's shape and changed
 *              cells). Nothing shows while it is the same (no confirmation labels)
 *
 * ROUTING: POST /workbench/approvals {outputs, approved?}
 */
import { api } from "./api";
import { button, clear, h } from "./dom";
import type { Output } from "./workbenchOutputs";

export interface Approval {
  snapshot: Record<string, unknown>;
  at: string | null;
}

interface Answer {
  approval?: Approval;
  changed: boolean;
  summary?: string[];
}

const SHOWN_LINES = 12;

/** The outputs as an approval keeps them (the server's snapshot), stamped with the time now. */
export async function approve(outputs: Output[]): Promise<Approval> {
  const made = await api<Answer>("/workbench/approvals", "POST", { outputs, at: new Date().toISOString().slice(0, 19) });
  if (!made.approval) throw new Error("The output could not be approved.");
  return made.approval;
}

/** How the outputs differ from their approval, as plain lines (null: the same). */
export async function compare(outputs: Output[], approved: Approval): Promise<string[] | null> {
  const found = await api<Answer>("/workbench/approvals", "POST", { outputs, approved });
  return found.changed ? (found.summary ?? []) : null;
}

export interface ApprovalNote {
  element: HTMLElement;
  /** Show the difference (null: hide it). */
  show: (lines: string[] | null) => void;
  shown: () => string[] | null;
}

/** A cell's amber note: "Changed since approved", the difference, and Approve this output. */
export function approvalNote(reapprove: () => void): ApprovalNote {
  const element = h("div", { class: "wb-approval", role: "status", hidden: true });
  let lines: string[] | null = null;
  const show = (next: string[] | null): void => {
    lines = next;
    element.hidden = next === null;
    if (next === null) return clear(element);
    const more = next.length - SHOWN_LINES;
    const list = h("ul", { class: "wb-approval-diff mono" }, ...next.slice(0, SHOWN_LINES).map((line) => h("li", { class: line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "" }, line)));
    if (more > 0) list.append(h("li", { class: "hint" }, `and ${more} more`));
    clear(
      element,
      h("div", { class: "wb-approval-head" }, h("span", { class: "wb-approval-word" }, "⚠ Changed since approved"), h("span", { class: "spacer" }), button("Approve this output", reapprove, { icon: "check", class: "ghost" })),
      list,
    );
  };
  return { element, show, shown: () => lines };
}
