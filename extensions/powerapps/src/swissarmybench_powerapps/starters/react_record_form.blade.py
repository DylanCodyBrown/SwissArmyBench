# /// swissarmybench-blade
# format = 1
# name = "React record form"
# kind = "snippet"
# description = "A React form that adds a record through a generated service, then says it was saved"
# tags = ["react", "tsx", "form", "dataverse", "code app"]
# family = "React"
# language = "tsx"
# ///
snippet = r"""
import { useState } from "react";
import { <<service name: AccountsService>> } from "./generated/services/<<service name: AccountsService>>";

// One field, one button: the record is created through the app's generated service (its own sign-in).
export function <<component name: NewRecordForm>>() {
  const [value, setValue] = useState("");
  const [said, setSaid] = useState("");
  const save = async () => {
    const result = await <<service name: AccountsService>>.create({ <<field name: name>>: value });
    setSaid(result.success ? "<<saved text: Saved.>>" : result.error?.message ?? "It was not saved.");
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); void save(); }}>
      <label>
        {"<<field label: Name>>"}
        <input value={value} onChange={(e) => setValue(e.target.value)} />
      </label>
      <button type="submit">{"<<button text: Add>>"}</button>
      {said && <p role="status">{said}</p>}
    </form>
  );
}
"""
