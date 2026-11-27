# /// swissarmybench-blade
# format = 1
# name = "React rows table"
# kind = "snippet"
# description = "A React component that shows rows as a table, its columns named, a message while empty"
# tags = ["react", "tsx", "table", "code app"]
# family = "React"
# language = "tsx"
# ///
snippet = r"""
type Row = Record<string, string | number | boolean | null>;

// A plain table of rows: the columns given, in their order; a line of text while there are none.
export function <<component name: RowsTable>>({ rows, columns }: { rows: Row[]; columns: string[] }) {
  if (!rows.length) return <p>{"<<empty text: Nothing to show yet.>>"}</p>;
  return (
    <table>
      <thead>
        <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i}>{columns.map((c) => <td key={c}>{String(row[c] ?? "")}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}
"""
