# /// swissarmybench-blade
# format = 1
# name = "TypeScript Dataverse rows"
# kind = "snippet"
# description = "Read a Dataverse table's rows through its generated service: chosen columns, a filter, an order"
# tags = ["typescript", "dataverse", "code app"]
# family = "TypeScript"
# language = "typescript"
# ///
snippet = r"""
import { <<service name: AccountsService>> } from "./generated/services/<<service name: AccountsService>>";

// The rows the app shows: the columns it needs, filtered and ordered on the server (Dataverse's own query).
export async function load<<rows name: Accounts>>() {
  const result = await <<service name: AccountsService>>.getAll({
    select: ["<<first column: name>>", "<<second column: createdon>>"],
    filter: "<<filter: statecode eq 0>>",
    orderBy: ["<<first column: name>> asc"],
    top: <<top number: 50>>,
  });
  if (!result.success) throw new Error(result.error?.message ?? "The rows could not be read.");
  return result.data ?? [];
}
"""
