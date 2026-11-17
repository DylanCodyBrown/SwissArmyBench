# /// swissarmybench-blade
# format = 1
# name = "Connector call"
# kind = "snippet"
# description = "Call one operation of a connector added to the app, through its generated service"
# tags = ["typescript", "connector", "code app"]
# family = "Connectors"
# language = "typescript"
# ///
snippet = r"""
import { <<service name: ContosotasksService>> } from "./generated/services/<<service name: ContosotasksService>>";

// One connector operation (its name is the operation's id, as the Connectors page shows it). It runs in the
// Power Apps host: in Local Play or the published app, signed in as the person using it.
export async function <<function name: listTasks>>() {
  const result = await <<service name: ContosotasksService>>.<<operation name: ListTasks>>("<<first input: inbox>>");
  if (!result.success) throw new Error(result.error?.message ?? "The connector did not answer.");
  return result.data;
}
"""
