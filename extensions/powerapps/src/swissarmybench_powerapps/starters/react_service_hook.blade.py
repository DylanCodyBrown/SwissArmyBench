# /// swissarmybench-blade
# format = 1
# name = "Hook over a generated service"
# kind = "snippet"
# description = "A page's hook: a generated service's rows with loading, error and refresh"
# tags = ["react", "hook", "typescript", "code app"]
# family = "React"
# language = "typescript"
# ///
snippet = r"""

import { useCallback, useEffect, useState } from "react";
import { <<service: AccountsService>> } from "../../../generated/services/<<service: AccountsService>>";

type Row = NonNullable<Awaited<ReturnType<typeof <<service: AccountsService>>.getAll>>["data"]>[number];

// The page's rows through the generated service: loading while it reads, the error's words when it fails.
export function <<hook name: useAccounts>>() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [asked, setAsked] = useState(0);
  useEffect(() => {
    let current = true;
    <<service: AccountsService>>.getAll()
      .then((result) => current && setRows(result.data ?? []))
      .catch((e: unknown) => current && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, [asked]);
  const refresh = useCallback(() => {
    setLoading(true);
    setAsked((n) => n + 1);
  }, []);
  return { rows, loading, error, refresh };
}
"""
