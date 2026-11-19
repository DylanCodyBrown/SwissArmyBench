/**
 * variablesPage.ts: the Variables page, on the rail after Connections (the owner, 2026-11-16:
 * "a workspace Variable page for the rail to help manage project variables"; "add new local env variables
 * from the page easily and browse what is there and for variables that are not from the key vault you can
 * see their current values"). This computer's variables, whether or not a project is open (2026-11-17:
 * the library of connections is the computer's). [SHARED]
 *
 *   [LIST]    every variable this computer gives or something reads, grouped by where its value comes
 *             from (a key vault, a plain value, the keyring, this computer's environment, not set); each
 *             row its name, its value (a plain one in plain sight; a keyring's dots and Show; a vault's the
 *             vault and the secret's name, never a value) and what uses it (a connection opens its card, a
 *             notebook's or a script's cell opens there).
 *   [SEARCH]  a name, a vault, a connection or a document; the source chips keep one group.
 *   [ADD]     Add variable (the heading row, prominent): a name, a value, and where it is kept: a plain
 *             value (shareable), This computer only (a plain value never shared), or the keyring (a
 *             secret). Edit, Rename (connections and Run settings follow; the cells still reading the
 *             old name listed) and Remove (what uses it shown first) on this computer's own.
 *   [SHOW]    a keyring secret's value on the user's click only (the server refuses the agent).
 *   [VAULTS]  the key vaults (the owner, 2026-11-17: a thing with no tables is not a connection): a card
 *             each (its detail and form are the Connections page's), Add key vault (a vault type's form).
 *   [PAGE]    a page of the rail's over any page (areaPage.ts), in the address as open=variables.
 *
 * ROUTING: GET/PUT /variables  ·  POST /variables/rename, /variables/reveal  ·  DELETE /variables/{name}
 *          GET /connections (the vaults), /connections/types (Add key vault)
 *          notice variables_changed
 */
import { api, onNotice } from "./api";
import { openAreaPage, type PageElement } from "./areaPage";
import { connectionIcon, openReference } from "./connectionsWindow";
import { append, button, h, icon, toast } from "./dom";
import { loadingBlock } from "./loading";
import { dismissDialog, layerOpened, registerLayer, setOverTitle, visit, watchLayerDialog, withParams } from "./nav";
import { errorHere, errorNote } from "./errorNote";

type Source = "vault" | "value" | "keyring" | "env" | "missing";

interface Use {
  kind: "connection" | "notebook" | "script" | "run_settings";
  name: string;
  how: string;
  path?: string;
  cell?: number;
  line?: number;
}

interface Variable {
  name: string;
  from: Source;
  words: string;
  set: boolean;
  secret: boolean;
  editable: boolean;
  renamable: boolean;
  uses: Use[];
  vault?: string;
  vault_secret?: string;
  owner?: string;
  kept?: "value" | "keyring";
  local?: boolean;
  value?: string;
  default?: string;
  hidden: boolean;
  replaces_env?: boolean;
}

interface Listing {
  variables: Variable[];
  every_vault: string[];
  kernels: number;
}

const GROUPS: { source: Source; name: string; icon: string }[] = [
  { source: "vault", name: "Key vault", icon: "key" },
  { source: "value", name: "Plain value", icon: "tag" },
  { source: "keyring", name: "Keyring", icon: "key" },
  { source: "env", name: "Environment", icon: "desktop" },
  { source: "missing", name: "Not set", icon: "help" },
];
const USE_ICONS: Record<Use["kind"], string> = { connection: "plug", notebook: "notebook", script: "code", run_settings: "clock" };
const DOTS = "••••••••";

let shownPage: PageElement | null = null;
let reload: (() => void) | null = null;

registerLayer("variables", {
  isOpen: () => Boolean(shownPage?.open),
  open: () => drawVariables(),
  show: () => undefined,
  dismiss: () => {
    if (shownPage) dismissDialog(shownPage);
  },
});

onNotice((n) => {
  if (n.type === "variables_changed" || n.type === "blades_changed") reload?.();
});

/** The Variables page, opened by the user (the rail's icon). */
export function openVariables(): void {
  if (shownPage?.open) return;
  layerOpened("variables");
  drawVariables();
}

/** A running kernel keeps the environment it started with: said after a change, once. */
function afterChange(kernels: number): void {
  if (kernels > 0) toast(kernels === 1 ? "A running kernel reads it after a restart." : `${kernels} running kernels read it after a restart.`);
}

function drawVariables(): void {
  const { element, body, actions } = openAreaPage("variables", "Variables");
  shownPage = element;
  body.classList.add("variables-page");
  setOverTitle("Variables");
  let listing: Listing | null = null;
  let source: Source | null = null;
  let failed: string | null = null;
  const search = h("input", { type: "search", class: "variables-search", placeholder: "Search", "aria-label": "Search variables", spellcheck: false }) as HTMLInputElement;
  const chips = h("div", { class: "segmented variables-sources", role: "group", "aria-label": "Source" });
  const formSlot = h("div", { class: "variables-form-slot" });
  const list = h("div", { class: "variables-list", "aria-live": "polite" });
  const add = button("Add variable", () => showForm(null), { icon: "plus", class: "primary variables-add" });
  const addVault = button("Add key vault", () => void showVaultTypes(), { icon: "key", class: "variables-add-vault" });
  actions.replaceChildren(search, addVault, add);
  const vaults = h("section", { class: "variables-vaults", "aria-label": "Key vaults" });
  body.append(formSlot, vaults, chips, list);

  // ----- the key vaults: each one's detail and form are the Connections page's -----
  const openVault = (name: string): void => visit(withParams({ open: "connections", at: "detail", type: null, name }));
  const loadVaults = async (): Promise<void> => {
    let found: { name: string; connection: string; template?: string | null; type?: string | null }[];
    try {
      found = (await api<{ connections: typeof found }>("/connections")).connections.filter((c) => c.connection === "vault");
    } catch {
      return;
    }
    vaults.replaceChildren(
      ...(found.length
        ? [
            h("h2", {}, icon("key"), "Key vaults", h("span", { class: "count" }, String(found.length))),
            h(
              "ul",
              { class: "variables-vault-cards" },
              ...found.map((v) =>
                h(
                  "li",
                  {},
                  h(
                    "button",
                    { type: "button", class: "variables-vault-card", "data-vault": v.name, onclick: () => openVault(v.name) },
                    icon(connectionIcon(v.template, "vault")),
                    h("strong", {}, v.name),
                    h("span", { class: "muted" }, v.type ?? "Key vault"),
                  ),
                ),
              ),
            ),
          ]
        : []),
    );
  };
  const showVaultTypes = async (): Promise<void> => {
    try {
      const types = (await api<{ types: { id: string; label: string; connection: string }[] }>("/connections/types")).types.filter((t) => t.connection === "vault");
      formSlot.replaceChildren(
        h(
          "div",
          { class: "variables-form variables-vault-types", role: "group", "aria-label": "Add key vault" },
          ...types.map((t) => button(t.label, () => visit(withParams({ open: "connections", at: "form", type: t.id, name: null })), { icon: connectionIcon(t.id, "vault"), class: "connection-type fam-vault" })),
          button("Cancel", closeForm),
        ),
      );
    } catch (e) {
      errorHere(e);
    }
  };

  const load = async (): Promise<void> => {
    try {
      listing = await api<Listing>("/variables");
      failed = null;
    } catch (e) {
      failed = (e as Error).message;
    }
    draw();
  };
  reload = () => {
    void load();
    void loadVaults();
  };

  const draw = (): void => {
    if (!element.open) return;
    if (failed) {
      list.replaceChildren(errorNote(failed));
      return;
    }
    if (!listing) {
      list.replaceChildren(loadingBlock("Loading the variables…"));
      return;
    }
    const words = search.value.trim().toLowerCase();
    const found = listing.variables.filter((v) => !words || [v.name, v.vault ?? "", v.vault_secret ?? "", v.owner ?? "", ...v.uses.map((u) => u.name)].some((s) => s.toLowerCase().includes(words)));
    const counts = new Map<Source, number>(GROUPS.map((g) => [g.source, found.filter((v) => v.from === g.source).length]));
    chips.replaceChildren(
      button(`All ${found.length}`, () => ((source = null), draw()), { pressed: source === null }),
      ...GROUPS.filter((g) => counts.get(g.source)).map((g) => {
        const b = button(`${g.name} ${counts.get(g.source)}`, () => ((source = source === g.source ? null : g.source), draw()), { pressed: source === g.source });
        b.dataset.source = g.source;
        return b;
      }),
    );
    const groups = GROUPS.filter((g) => (source === null || g.source === source) && counts.get(g.source));
    if (!groups.length) {
      list.replaceChildren(h("p", { class: "empty-note" }, listing.variables.length ? "No match." : "No variables yet."));
    } else {
      list.replaceChildren(
        ...groups.map((g) =>
          h(
            "section",
            { class: "variables-group", "data-source": g.source },
            h("h2", {}, icon(g.icon), g.name, h("span", { class: "count" }, String(counts.get(g.source)))),
            h("div", { class: "variables-rows", role: "list" }, ...found.filter((v) => v.from === g.source).map(row)),
          ),
        ),
      );
    }
    if (listing.every_vault.length) list.append(h("p", { class: "hint variables-every" }, `${listing.every_vault.join(", ")}: every secret, named when it runs.`));
  };

  // ----- one row -----

  const valueCell = (v: Variable): HTMLElement => {
    const cell = h("div", { class: "variable-value" });
    if (v.from === "vault") {
      cell.append(h("span", { class: "variable-vault" }, icon("key"), h("span", {}, v.vault ?? ""), h("span", { class: "muted" }, " · "), h("span", { class: "mono" }, v.vault_secret ?? "")));
    } else if (v.hidden) {
      const shown = h("span", { class: "mono variable-dots" }, DOTS);
      const show = button("Show", async () => {
        if (show.dataset.shown === "1") {
          shown.textContent = DOTS;
          show.dataset.shown = "";
          show.querySelector(".btn-label")!.textContent = "Show";
          show.title = "Show";
          show.setAttribute("aria-label", "Show");
          return;
        }
        try {
          const got = await api<{ value: string }>("/variables/reveal", "POST", { name: v.name });
          shown.textContent = got.value;
          show.dataset.shown = "1";
          show.querySelector(".btn-label")!.textContent = "Hide";
          show.title = "Hide";
          show.setAttribute("aria-label", "Hide");
        } catch (e) {
          errorHere(e);
        }
      }, { icon: "eye", class: "small variable-show" });
      cell.append(shown, show);
    } else if (v.value !== undefined) {
      cell.append(v.value === "" ? h("span", { class: "muted" }, "(empty)") : h("span", { class: "mono variable-plain", title: v.value }, v.value));
    } else if (v.from === "missing") {
      append(cell, h("span", { class: "variable-missing" }, "Not set"), v.default ? h("span", { class: "mono muted", title: v.default }, ` ${v.default}`) : null);
    } else {
      cell.append(h("span", { class: "muted" }, DOTS));
    }
    return cell;
  };

  const useChip = (u: Use): HTMLElement => {
    // A connection's use names its field (12.7: Warehouse · Server); its code or a password by the same words.
    const field = u.how.charAt(0).toUpperCase() + u.how.slice(1);
    const where = u.kind === "run_settings" ? `${u.name}: ${u.how}` : u.kind === "connection" ? `${u.name} · ${field}` : `${u.name}${u.cell ? ` · cell ${u.cell}` : ""}`;
    const open = (): void => {
      if (u.kind === "connection") visit(withParams({ open: "connections", at: "detail", type: null, name: u.name }));
      else if (u.path) void openReference({ document: u.path, title: u.name, kind: u.kind === "notebook" ? "notebook" : "script", how: u.how, line: "", cell: u.cell ?? null }).catch((e: Error) => errorHere(e));
    };
    return h("button", { type: "button", class: "variable-use", title: u.kind === "connection" ? `${u.name}: ${u.how}` : u.how, onclick: open }, icon(USE_ICONS[u.kind]), h("span", {}, where));
  };

  const row = (v: Variable): HTMLElement => {
    const tools = h(
      "div",
      { class: "variable-tools" },
      v.editable ? button("Edit", () => showForm(v), { icon: "edit", class: "small" }) : null,
      v.renamable ? button("Rename", () => showRename(v), { class: "small" }) : null,
      v.renamable ? button("Remove", () => showRemove(v), { icon: "trash", iconOnly: true, class: "small" }) : null,
    );
    const where = v.kept === "value" && v.local ? h("span", { class: "variable-badge", title: "Not shared" }, "This computer only") : v.owner && v.from !== "vault" ? h("span", { class: "variable-badge" }, v.owner) : null;
    return h(
      "div",
      { class: "variable-row", role: "listitem", "data-name": v.name, "data-source": v.from },
      h("div", { class: "variable-name" }, h("span", { class: "mono" }, v.name), where),
      valueCell(v),
      h("div", { class: "variable-uses" }, ...v.uses.map(useChip)),
      tools,
    );
  };

  // ----- add, edit, rename, remove: a form above the list -----

  const closeForm = (): void => formSlot.replaceChildren();

  const showForm = (editing: Variable | null): void => {
    const name = h("input", { type: "text", class: "mono", "aria-label": "Name", placeholder: "SALES_REGION", spellcheck: false, value: editing?.name ?? "", readonly: Boolean(editing) }) as HTMLInputElement;
    const keyring = editing?.kept === "keyring";
    const kept = h(
      "select",
      { "aria-label": "Kept" },
      h("option", { value: "value" }, "Plain value"),
      h("option", { value: "local" }, "This computer only"),
      h("option", { value: "keyring" }, "Keyring (secret)"),
    ) as HTMLSelectElement;
    kept.value = keyring ? "keyring" : editing?.local ? "local" : "value";
    const value = h("input", { type: keyring ? "password" : "text", "aria-label": "Value", spellcheck: false, autocomplete: "off", value: editing && !keyring ? (editing.value ?? "") : "", placeholder: keyring ? "Saved" : "" }) as HTMLInputElement;
    // A secret's name: the keyring, until the user picks otherwise.
    const secretName = (s: string): boolean => /(PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|PRIVATE)/i.test(s);
    let picked = Boolean(editing);
    kept.addEventListener("change", () => {
      picked = true;
      value.type = kept.value === "keyring" ? "password" : "text";
    });
    name.addEventListener("input", () => {
      name.value = name.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_");
      if (!picked) {
        kept.value = secretName(name.value) ? "keyring" : "value";
        value.type = kept.value === "keyring" ? "password" : "text";
      }
    });
    const save = async (): Promise<void> => {
      const from = kept.value === "keyring" ? "keyring" : "value";
      try {
        const done = await api<{ kernels: number }>("/variables", "PUT", { name: name.value.trim(), value: value.value, from, ...(from === "value" ? { local: kept.value === "local" } : {}) });
        closeForm();
        toast(editing ? `Changed ${name.value.trim()}` : `Added ${name.value.trim()}`);
        afterChange(done.kernels);
        await load();
      } catch (e) {
        errorHere(e);
      }
    };
    const form = h(
      "form",
      { class: "variables-form", "aria-label": editing ? `Edit ${editing.name}` : "Add variable", onsubmit: (e: Event) => (e.preventDefault(), void save()) },
      h("label", { class: "field" }, h("span", {}, "Name"), name),
      h("label", { class: "field variables-form-value" }, h("span", {}, "Value"), value),
      h("label", { class: "field" }, h("span", {}, "Kept"), kept),
      h("div", { class: "variables-form-buttons" }, h("button", { type: "submit", class: "btn primary" }, editing ? "Save" : "Add"), button("Cancel", closeForm)),
    );
    formSlot.replaceChildren(form);
    (editing ? value : name).focus();
  };

  const showRename = (v: Variable): void => {
    const to = h("input", { type: "text", class: "mono", "aria-label": "New name", value: v.name, spellcheck: false }) as HTMLInputElement;
    const go = async (): Promise<void> => {
      try {
        const done = await api<{ connections: string[]; still_reading: Use[]; kernels: number }>("/variables/rename", "POST", { name: v.name, to: to.value.trim() });
        closeForm();
        await load();
        if (done.still_reading.length) {
          formSlot.replaceChildren(
            h(
              "div",
              { class: "variables-form variables-still", role: "status" },
              h("strong", {}, `Still reading ${v.name}:`),
              h("div", { class: "variable-uses" }, ...done.still_reading.map(useChip)),
              button("Done", closeForm),
            ),
          );
        } else toast(`Renamed to ${to.value.trim()}`);
        afterChange(done.kernels);
      } catch (e) {
        errorHere(e);
      }
    };
    formSlot.replaceChildren(
      h(
        "form",
        { class: "variables-form", "aria-label": `Rename ${v.name}`, onsubmit: (e: Event) => (e.preventDefault(), void go()) },
        h("label", { class: "field" }, h("span", {}, `Rename ${v.name}`), to),
        h("div", { class: "variables-form-buttons" }, h("button", { type: "submit", class: "btn primary" }, "Rename"), button("Cancel", closeForm)),
      ),
    );
    to.select();
  };

  const showRemove = (v: Variable): void => {
    const go = async (): Promise<void> => {
      try {
        await api(`/variables/${encodeURIComponent(v.name)}`, "DELETE");
        closeForm();
        toast(`Removed ${v.name}`);
        await load();
      } catch (e) {
        errorHere(e);
      }
    };
    formSlot.replaceChildren(
      h(
        "div",
        { class: "variables-form variables-remove", role: "group", "aria-label": `Remove ${v.name}` },
        h("strong", {}, v.uses.length ? `Remove ${v.name}? Used by:` : `Remove ${v.name}?`),
        v.uses.length ? h("div", { class: "variable-uses" }, ...v.uses.map(useChip)) : null,
        h("div", { class: "variables-form-buttons" }, button("Remove", () => void go(), { class: "danger" }), button("Cancel", closeForm)),
      ),
    );
  };

  search.addEventListener("input", draw);
  watchLayerDialog(element, "variables", [], () => {
    if (shownPage === element) shownPage = null;
    reload = null;
  });
  draw();
  void load();
  void loadVaults();
}
