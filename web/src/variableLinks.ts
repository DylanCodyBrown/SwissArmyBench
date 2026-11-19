/**
 * variableLinks.ts: "Set it" and "New variable…" (design principle 12.7): the Variables page's Add variable
 * form, with the name filled in, over whatever is open, so a half-filled connection form stays as it was.
 * The same three fields as the page's form (a name, a value, where it is kept); the same PUT /variables.
 * [SHARED]
 *
 *   addVariable(name, done)   the form; `done` once it is saved (the box that asked reads it again).
 */
import { api } from "./api";
import { button, h, openDialog, toast } from "./dom";
import { showError } from "./errorNote";

const SECRET_NAME = /(PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|PRIVATE)/i;

export function addVariable(name: string, done?: () => void): void {
  const { dialog, body, foot, close } = openDialog("Add variable");
  dialog.classList.add("variable-add-dialog");
  const named = h("input", { type: "text", class: "mono", "aria-label": "Name", placeholder: "SALES_REGION", spellcheck: false, value: name }) as HTMLInputElement;
  const kept = h(
    "select",
    { "aria-label": "Kept" },
    h("option", { value: "value" }, "Plain value"),
    h("option", { value: "local" }, "This computer only"),
    h("option", { value: "keyring" }, "Keyring (secret)"),
  ) as HTMLSelectElement;
  const value = h("input", { type: "text", "aria-label": "Value", spellcheck: false, autocomplete: "off" }) as HTMLInputElement;
  let picked = false;
  const suit = (): void => {
    if (!picked) kept.value = SECRET_NAME.test(named.value) ? "keyring" : "value";
    value.type = kept.value === "keyring" ? "password" : "text";
  };
  named.addEventListener("input", () => {
    named.value = named.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_");
    suit();
  });
  kept.addEventListener("change", () => {
    picked = true;
    suit();
  });
  suit();
  const problem = h("div", { class: "variable-add-problem", role: "alert" });
  const save = async (): Promise<void> => {
    const from = kept.value === "keyring" ? "keyring" : "value";
    try {
      await api("/variables", "PUT", { name: named.value.trim(), value: value.value, from, ...(from === "value" ? { local: kept.value === "local" } : {}) });
      close();
      toast(`Added ${named.value.trim()}`);
      done?.();
    } catch (e) {
      showError(problem, e);
    }
  };
  const form = h(
    "form",
    { class: "variables-form", "aria-label": "Add variable", onsubmit: (e: Event) => (e.preventDefault(), void save()) },
    h("label", { class: "field" }, h("span", {}, "Name"), named),
    h("label", { class: "field variables-form-value" }, h("span", {}, "Value"), value),
    h("label", { class: "field" }, h("span", {}, "Kept"), kept),
  );
  body.append(form, problem);
  foot.append(button("Cancel", close), h("button", { type: "button", class: "btn primary", onclick: () => void save() }, "Add"));
  (name ? value : named).focus();
}
