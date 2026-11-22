/**
 * keyVaults.ts: the key vaults on the Environment's Settings and secrets tab (the owner, 2026-11-17: a thing
 * with no tables is not a connection, so a vault is listed with the settings it gives; 2026-11-22: the
 * Variables page folded into the Environment, and these pieces moved here from it, unchanged). [SHARED]
 *
 *   [CARDS]  a card per key vault: its name, its kind, how many variables it gives; a click opens its detail
 *            (the Connections page's, where it is edited). A vault that loads every secret whose last read
 *            failed says when its names are from, with Read again.
 *   [ADD]    Add key vault: the vault kinds as buttons; one opens its form (the Connections page's).
 *
 * ROUTING: GET /connections (the vaults), GET /connections/types (Add key vault)
 *          POST /connections/vaults/secrets {name} (Read again)
 */
import { api } from "./api";
import { connectionIcon } from "./connectionsWindow";
import { button, h, icon } from "./dom";
import { errorHere } from "./errorNote";
import { busyClick } from "./loading";
import { visit, withParams } from "./nav";

/** A vault card's line (GET /connections names): its variables, when its names were read, a failed read. */
type Names = { count: number; read_at?: string | null; error?: string; reading?: boolean };
type Vault = { name: string; connection: string; template?: string | null; type?: string | null; every?: boolean; names?: Names | null };

export interface KeyVaults {
  /** The cards (empty while there is no vault), and above them the kinds to add while Add key vault is open. */
  element: HTMLElement;
  /** Read the vaults again (a `blades_changed` or `variables_changed` notice, the tab shown). */
  refresh: () => Promise<void>;
  /** Add key vault: the vault kinds, each opening its form on the Connections page. */
  add: () => Promise<void>;
}

export function mountKeyVaults(): KeyVaults {
  const types = h("div", { class: "variables-form-slot" });
  const cards = h("section", { class: "variables-vaults", "aria-label": "Key vaults" });
  const element = h("div", { class: "env-vaults" }, types, cards);
  const openVault = (name: string): void => visit(withParams({ open: "connections", at: "detail", type: null, name }));

  const refresh = async (): Promise<void> => {
    let found: Vault[];
    try {
      found = (await api<{ connections: Vault[] }>("/connections")).connections.filter((c) => c.connection === "vault");
    } catch {
      return;
    }
    const every = found.filter((v) => v.every).map((v) => v.name);
    cards.replaceChildren(
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
                    v.names ? h("span", { class: "muted variables-vault-count" }, v.names.count === 1 ? "1 variable" : `${v.names.count} variables`) : null,
                  ),
                  v.names?.error ? staleNames(v.name, v.names) : null,
                ),
              ),
            ),
            ...(every.length ? [h("p", { class: "hint variables-every" }, `${every.join(", ")}: every secret, named when it runs.`)] : []),
          ]
        : []),
    );
  };

  // A vault that loads every secret whose last read failed: its names are the ones read before.
  const staleNames = (name: string, names: Names): HTMLElement => {
    const at = names.read_at ? new Date(names.read_at).toLocaleString() : "";
    return h(
      "p",
      { class: "variables-vault-stale", title: names.error ?? "" },
      icon("warning"),
      h("span", {}, at ? `Names from ${at}` : "Not read"),
      button("Read again", busyClick("Reading…", async () => {
        try {
          await api("/connections/vaults/secrets", "POST", { name });
        } catch (e) {
          errorHere(e);
        }
        await refresh();
      }), { class: "link" }),
    );
  };

  const add = async (): Promise<void> => {
    try {
      const kinds = (await api<{ types: { id: string; label: string; connection: string }[] }>("/connections/types")).types.filter((t) => t.connection === "vault");
      types.replaceChildren(
        h(
          "div",
          { class: "variables-form variables-vault-types", role: "group", "aria-label": "Add key vault" },
          ...kinds.map((t) => button(t.label, () => visit(withParams({ open: "connections", at: "form", type: t.id, name: null })), { icon: connectionIcon(t.id, "vault"), class: "connection-type fam-vault" })),
          button("Cancel", () => types.replaceChildren(), { class: "ghost" }),
        ),
      );
    } catch (e) {
      errorHere(e);
    }
  };

  return { element, refresh, add };
}
