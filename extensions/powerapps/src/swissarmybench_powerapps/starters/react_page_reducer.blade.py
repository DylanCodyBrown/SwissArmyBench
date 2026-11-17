# /// swissarmybench-blade
# format = 1
# name = "Page reducer"
# kind = "snippet"
# description = "A page's own state and its actions, typed: kept at the page's root, never app-wide"
# tags = ["react", "state", "typescript", "code app"]
# family = "TypeScript"
# language = "typescript"
# ///
snippet = r"""

export interface <<state name: OrdersState>> {
  selectedId: string | null;
  filter: string;
}

export type <<action name: OrdersAction>> =
  | { type: "select"; id: string | null }
  | { type: "filter"; text: string }
  | { type: "reset" };

export const <<initial name: initialOrdersState>>: <<state name: OrdersState>> = { selectedId: null, filter: "" };

// The page's state: useReducer(<<reducer name: ordersReducer>>, <<initial name: initialOrdersState>>) at its root.
export function <<reducer name: ordersReducer>>(state: <<state name: OrdersState>>, action: <<action name: OrdersAction>>): <<state name: OrdersState>> {
  switch (action.type) {
    case "select":
      return { ...state, selectedId: action.id };
    case "filter":
      return { ...state, filter: action.text };
    case "reset":
      return <<initial name: initialOrdersState>>;
  }
}
"""
