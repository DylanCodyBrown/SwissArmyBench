/**
 * extensionPanel.ts: an extension's own panel, drawn from the data its backend answers. [SHARED]
 *
 * An extension that is on may name a panel route (GET /extensions lists it as `panel`). Its answer is data:
 *   lines     [{text, tone}]: what it says (tone ok, warn, error or none)
 *   switches  [{id, label, on, disabled}]: each a switch; a change posts {switch, on}
 *   actions   [{id, label, primary, disabled}]: each a button; a click posts {action}
 *   code      {label, text, link, link_label, then, waiting}: a code to copy and a page to open (https only):
 *             the page opens on the user's click, then {action: then} is posted
 *   busy      words while it works (a progress bar; asked again every two seconds)
 *   choices   [{id, label, value, options: [{value, label}]}]: each a picker; a change posts {choice, value}
 *   rows      [{id, text, tone, action: {id, label}}]: a list to work through, each with its one fix
 *   actions may carry a `note`: one sentence under the button
 * The Extensions page's card and Settings draw the same panel. Nothing here names an extension.
 *
 * ROUTING: the panel's route (GET, POST)  ·  notice extension_panel_changed
 */
import { api, onNotice } from "./api";
import { button, h, icon, toast } from "./dom";
import { errorHere } from "./errorNote";

export interface PanelData {
  title?: string;
  lines: { text: string; tone?: string }[];
  switches: { id: string; label: string; on: boolean; disabled?: boolean }[];
  actions: { id: string; label: string; primary?: boolean; disabled?: boolean; note?: string }[];
  choices?: { id: string; label: string; value: string; options: { value: string; label: string }[] }[];
  rows?: { id: string; text: string; tone?: string; action?: { id: string; label: string } }[];
  heading?: string;
  code?: { label: string; text: string; link: string; link_label: string; then: string; waiting?: boolean } | null;
  busy?: string | null;
}

const mounted = new Set<{ host: HTMLElement; redraw: () => void }>();

onNotice((n) => {
  if (n.type !== "extension_panel_changed") return;
  for (const panel of [...mounted]) {
    if (!panel.host.isConnected) mounted.delete(panel);
    else panel.redraw();
  }
});

/** The panel at `route`, drawn into a new element (and kept current while it is on the page). */
export function extensionPanel(route: string): HTMLElement {
  const host = h("div", { class: "extension-panel", "data-panel": route });
  let poll: number | null = null;
  const draw = (data: PanelData): void => {
    const lines = data.lines.map((l) => h("p", { class: `extension-panel-line${l.tone ? ` tone-${l.tone}` : ""}`, role: l.tone === "error" ? "alert" : undefined }, l.text));
    const switches = data.switches.map((s) => {
      const input = h("input", { type: "checkbox", role: "switch", class: "switch-input", "aria-label": s.label, dataset: { switch: s.id } });
      input.checked = s.on;
      input.disabled = Boolean(s.disabled);
      input.addEventListener("change", () => void post({ switch: s.id, on: input.checked }));
      return h("label", { class: "autosave-switch" }, input, h("span", {}, s.label));
    });
    const actions = data.actions.map((a) => {
      const go = button(a.label, () => void post({ action: a.id }), { class: a.primary ? "primary" : "" });
      go.dataset.action = a.id;
      go.disabled = Boolean(a.disabled);
      return a.note ? h("div", { class: "extension-panel-action" }, go, h("p", { class: "extension-panel-note" }, a.note)) : go;
    });
    const choices = (data.choices ?? []).map((c) => {
      const select = h("select", { "aria-label": c.label, dataset: { choice: c.id } }, ...c.options.map((o) => h("option", { value: o.value }, o.label)));
      select.value = c.value;
      select.addEventListener("change", () => void post({ choice: c.id, value: select.value }));
      return h("label", { class: "extension-panel-choice" }, h("span", {}, c.label), select);
    });
    const rows = (data.rows ?? []).map((r) => {
      const fix = r.action ? button(r.action.label, () => void post({ action: r.action!.id }), {}) : null;
      if (fix) fix.dataset.action = r.action!.id;
      return h("li", { class: `extension-panel-row${r.tone ? ` tone-${r.tone}` : ""}`, "data-row": r.id }, h("span", {}, r.text), fix ?? "");
    });
    let code: HTMLElement | null = null;
    if (data.code) {
      const said = data.code;
      const copy = button("Copy", () => void navigator.clipboard.writeText(said.text).then(() => toast("Copied."), () => errorHere("The browser blocked the clipboard.")), { icon: "copy", class: "ghost" });
      const open = button(said.link_label, () => {
        if (said.link.startsWith("https://")) window.open(said.link, "_blank", "noopener");
        void post({ action: said.then });
      }, { class: "primary", icon: "popout" });
      open.dataset.action = said.then;
      code = h("div", { class: "extension-panel-code" }, h("span", { class: "muted" }, said.label), h("strong", { class: "mono extension-panel-usercode" }, said.text), copy, said.waiting ? null : open);
    }
    const busy = data.busy ? h("div", { class: "extension-panel-busy", role: "status" }, h("progress", { "aria-label": data.busy }), h("span", {}, data.busy)) : null;
    host.replaceChildren(
      ...choices,
      data.heading && rows.length ? h("h2", { class: "extension-panel-heading" }, data.heading) : "",
      rows.length ? h("ul", { class: "extension-panel-rows" }, ...rows) : "",
      ...lines,
      code ?? "",
      busy ?? "",
      switches.length || actions.length ? h("div", { class: "extension-panel-controls" }, ...switches, ...actions) : "",
    );
    if (poll !== null) window.clearTimeout(poll);
    poll = data.busy && host.isConnected ? window.setTimeout(() => void load(), 2000) : null;
  };
  const fail = (e: Error): void => {
    host.append(h("p", { class: "extension-panel-line tone-error", role: "alert" }, e.message));
  };
  const load = async (): Promise<void> => {
    try {
      draw(await api<PanelData>(route));
    } catch (e) {
      fail(e as Error);
    }
  };
  const post = async (body: Record<string, unknown>): Promise<void> => {
    for (const control of host.querySelectorAll<HTMLButtonElement | HTMLInputElement>("button, input")) control.disabled = true;
    try {
      draw(await api<PanelData>(route, "POST", body));
    } catch (e) {
      await load();
      fail(e as Error);
    }
  };
  mounted.add({ host, redraw: () => void load() });
  void load();
  return host;
}

/** Settings' sections: each extension that is on and has a panel, drawn from what it answers. */
export function extensionSettings(): HTMLElement {
  const host = h("div", { class: "extension-settings" });
  void api<{ extensions: { id: string; name: string; status: string; panel?: string }[] }>("/extensions").then(
    (got) =>
      host.replaceChildren(
        ...got.extensions
          .filter((e) => e.panel && e.status === "installed")
          .map((e) => h("fieldset", { class: "fieldset extension-settings-fieldset", "data-extension": e.id }, h("legend", {}, icon("extensions"), e.name), extensionPanel(e.panel!))),
      ),
    () => undefined,
  );
  return host;
}
