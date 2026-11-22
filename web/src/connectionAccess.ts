// A connection's Access section on the Connections page's card detail (GET /connections/{name}/access): what
// the app registrations that sign it in can reach, when that was last checked and on which computer, each item
// marked (✓, ✗ with its reason and fix, or not checked with why), and Check again (POST
// /app-registrations/{registration}/check: read-only calls, never on a timer). A connection no registration
// signs in has no section.

import { api } from "./api";
import { button, dateTime, h, icon } from "./dom";
import { errorNote } from "./errorNote";
import { busyClick } from "./loading";

interface AccessItem {
  area: string;
  target: string;
  ok: boolean | null;
  mark: string;
  reason?: string;
  fix?: string;
}

interface AccessBy {
  registration: string;
  checked: string;
  computer: string;
  line: string;
  items: AccessItem[];
}

/** "2026-11-19T10:04:00Z" in the reader's own time, to the minute. */

function item(i: AccessItem): HTMLElement {
  const state = i.ok === true ? "ok" : i.ok === false ? "refused" : "unchecked";
  return h(
    "li",
    { class: `connection-access-item access-${state}` },
    h("span", { class: "connection-access-mark", "aria-label": i.ok === true ? "Reaches" : i.ok === false ? "Refused" : "Not checked" }, i.ok === null ? "–" : i.mark),
    h(
      "span",
      { class: "connection-access-what" },
      h("span", {}, i.target),
      i.reason ? h("span", { class: "connection-access-why" }, i.reason) : null,
      i.fix ? h("span", { class: "connection-access-fix" }, i.fix) : null,
    ),
  );
}

/** The section, filled once its answer comes; it stays hidden when no registration signs the connection in. */
export function accessSection(name: string): HTMLElement {
  const section = h("section", { class: "connection-section connection-access", "aria-label": "Access", hidden: "" });
  const draw = async (): Promise<void> => {
    let found: AccessBy[];
    try {
      found = (await api<{ access: AccessBy[] }>(`/connections/${encodeURIComponent(name)}/access`)).access;
    } catch {
      return; // no registrations here (an older server): no section
    }
    if (!found.length) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    section.replaceChildren(
      h("h2", {}, icon("key"), "Access"),
      ...found.map((by) => {
        const said = h("div", { class: "connection-access-said", role: "status" });
        return h(
          "div",
          { class: "connection-access-by" },
          h("p", { class: "connection-access-line" }, h("strong", {}, by.registration), " ", by.line),
          h("p", { class: "connection-access-when" }, `Last checked ${dateTime(by.checked)}`, by.computer ? ` on ${by.computer}` : ""),
          h("ul", { class: "connection-access-items" }, ...by.items.map(item)),
          button(
            "Check again",
            busyClick("Checking…", async () => {
              said.replaceChildren();
              try {
                await api(`/app-registrations/${encodeURIComponent(by.registration)}/check`, "POST");
                await draw();
              } catch (e) {
                said.replaceChildren(errorNote(e));
              }
            }),
            { icon: "play" },
          ),
          said,
        );
      }),
    );
  };
  void draw();
  return section;
}
