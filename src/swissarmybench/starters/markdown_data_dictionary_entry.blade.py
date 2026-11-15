# /// swissarmybench-blade
# format = 1
# name = "Markdown data dictionary entry"
# kind = "snippet"
# description = "One column described: what it means, its type and where it comes from (reads no names)"
# tags = ["markdown", "documentation"]
# family = "Markdown"
# language = "markdown"
# ///
snippet = r"""
#### `<<column: amount>>`

- **Meaning:** <<meaning: the order's value, before tax.>>
- **Type:** <<type: number with two decimals>>
- **Source:** <<source: orders.csv, made up for testing>>
"""
