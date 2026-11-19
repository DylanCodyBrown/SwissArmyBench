/**
 * agentAccess.ts: the agent's requests for a click. [STATE + WIRE]
 *
 * The agent sees what the page shows. An agent export always waits for the user's click: each
 * request opens the approval popup at once, wherever the user is, rather than waiting in a tab
 * they might not be looking at. (Settings' Agent activity list is gone, the owner, 2026-11-16; the audit
 * log stays on disk and GET /audit still reads it.)
 *
 * ROUTING: [APPROVAL POPUP]   Allow / Deny -> resolveApproval(id, approve)
 */
import { api, type Notice } from "./api";
import { button, clear, h, icon, openDialog } from "./dom";
import { errorHere } from "./errorNote";

interface Approval {
  id: string;
  dataset: string;
  action: string;
  detail: string;
}

let pending: Approval[] = [];
let popup: { body: HTMLElement; close: () => void } | null = null;

// ===== approval requests =====

/** Live notices about the agent's requests: open, update or close the approval popup. */
export function handleAgentNotice(notice: Notice): void {
  if (notice.type === "approval_requested" && notice.id && !pending.some((a) => a.id === notice.id)) {
    pending.push({ id: notice.id, dataset: notice.dataset ?? "", action: notice.action ?? "", detail: notice.detail ?? "" });
    showApprovals();
  }
  if (notice.type === "approval_resolved") {
    pending = pending.filter((a) => a.id !== notice.id);
    showApprovals();
  }
}

/** On page load: any request already waiting. */
export async function loadApprovals(): Promise<void> {
  try {
    pending = (await api<{ pending: Approval[] }>("/agent/approvals")).pending;
    showApprovals();
  } catch {
    // none
  }
}

function showApprovals(): void {
  if (!pending.length) {
    popup?.close();
    popup = null;
    return;
  }
  if (!popup || !popup.body.isConnected) {
    // Not closed by the browser's Back (closing declines): it waits for Allow or Deny (nav.ts).
    const { dialog, body, foot, close } = openDialog("The agent is asking", true, { history: false });
    foot.append(h("span", { class: "hint" }, "Closing declines. Expires in 3 minutes."));
    // Escape or the X used to hide a request that was still waiting, with nothing in the page to
    // bring it back: the agent waited out its 3 minutes. Closing now answers No.
    dialog.addEventListener("close", () => {
      for (const approval of [...pending]) void resolveApproval(approval.id, false);
    });
    popup = { body, close };
  }
  clear(
    popup.body,
    ...pending.map((approval) =>
      h(
        "section",
        { class: "approval", role: "alertdialog", "aria-label": "Agent approval request" },
        h("strong", {}, icon("agent"), ` The agent wants to ${approval.action} ${approval.dataset}:`),
        h("pre", { class: "mono" }, approval.detail),
        h(
          "div",
          { class: "row" },
          button("Allow", () => void resolveApproval(approval.id, true), { class: "primary" }),
          button("Deny", () => void resolveApproval(approval.id, false), { class: "danger" }),
        ),
      ),
    ),
  );
}

async function resolveApproval(id: string, approve: boolean): Promise<void> {
  try {
    await api(`/agent/approvals/${id}`, "POST", { approve });
    pending = pending.filter((a) => a.id !== id);
    showApprovals();
  } catch (e) {
    errorHere(e);
  }
}
