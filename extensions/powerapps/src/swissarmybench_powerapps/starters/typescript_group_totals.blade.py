# /// swissarmybench-blade
# format = 1
# name = "TypeScript group totals"
# kind = "snippet"
# description = "Rows grouped by one field, a total of another for each group, largest first"
# tags = ["typescript", "transform", "code app"]
# family = "TypeScript"
# language = "typescript"
# ///
snippet = r"""
// Totals by group, largest first: what a chart or a summary row in the app shows.
export function <<function name: totalsBy>>(rows: Record<string, unknown>[]) {
  const totals = new Map<string, number>();
  for (const row of rows) {
    const key = String(row["<<group field: region>>"] ?? "");
    totals.set(key, (totals.get(key) ?? 0) + Number(row["<<amount field: amount>>"] ?? 0));
  }
  return [...totals.entries()]
    .map(([group, total]) => ({ group, total }))
    .sort((a, b) => b.total - a.total);
}
"""
