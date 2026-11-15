# /// swissarmybench-blade
# format = 1
# name = "HTML bar chart"
# kind = "snippet"
# description = "A bar chart drawn in CSS from a table's rows"
# tags = ["html", "chart"]
# family = "HTML"
# language = "html"
# ///
snippet = r"""
<!-- A bar chart in CSS: one bar for each row of <<table>>, as long as its <<value column>>. The rows come
     from {{ <<table>> }}, filled when the cell runs (inside a script it is a list of rows). -->
<div id="bars" style="max-width:560px;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;font-size:13px"></div>
<script>
  const rows = {{ <<table>> }};
  const label = "<<label column>>", value = "<<value column>>";
  const most = Math.max(...rows.map((r) => Math.abs(Number(r[value]) || 0)), 1);
  const box = document.getElementById("bars");
  for (const row of rows.slice(0, 30)) {
    const amount = Number(row[value]) || 0;
    const line = document.createElement("div");
    line.style.cssText = "display:grid;grid-template-columns:140px 1fr 80px;gap:8px;align-items:center;margin:3px 0";
    const name = document.createElement("span");
    name.textContent = row[label];
    name.style.cssText = "overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
    const track = document.createElement("span");
    track.style.cssText = "height:14px;border-radius:3px;background:color-mix(in srgb, currentColor 5%, transparent)";
    const bar = document.createElement("span");
    bar.style.cssText = `display:block;height:100%;border-radius:3px;background:<<colour: #c8102e>>;width:${(Math.abs(amount) / most) * 100}%`;
    track.append(bar);
    const shown = document.createElement("span");
    shown.textContent = amount.toLocaleString();
    shown.style.cssText = "text-align:right;font-variant-numeric:tabular-nums";
    line.append(name, track, shown);
    box.append(line);
  }
</script>
"""
