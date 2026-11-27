# /// swissarmybench-blade
# format = 1
# name = "React page"
# kind = "snippet"
# description = "A page's root: its rows from its hook, its state in a reducer, a list and a detail handed it by props"
# tags = ["react", "tsx", "page", "code app"]
# family = "React"
# language = "tsx"
# ///
snippet = r"""

import { useReducer } from "react";

type Row = Record<string, unknown>;
type State = { selected: Row | null };
type Action = { type: "select"; row: Row | null };

function reducer(state: State, action: Action): State {
  return action.type === "select" ? { ...state, selected: action.row } : state;
}

// A page's root: it keeps the page's state and hands it down; nothing here is shared with another page.
export function <<page name: OrdersPage>>({ rows }: { rows: Row[] }) {
  const [state, dispatch] = useReducer(reducer, { selected: null });
  return (
    <div>
      <h1>{"<<title: Orders>>"}</h1>
      <ul>
        {rows.map((row, i) => (
          <li key={i} onClick={() => dispatch({ type: "select", row })}>{JSON.stringify(row)}</li>
        ))}
      </ul>
      {state.selected && <pre>{JSON.stringify(state.selected, null, 2)}</pre>}
    </div>
  );
}
"""
