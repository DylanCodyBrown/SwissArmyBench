using System.Globalization;
using System.Text.Json;

using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids.Cards;

/// <summary>A column's profile and the whole view's, as Analyze board cards (the classic analysisCards.ts
/// profileCards and tableProfileCards): the numbers in a table, the most common values, and a Plotly chart beside
/// them (a histogram for numbers, rows by month for dates, the top values for anything else).</summary>
public static class ProfileCards
{
    private const int TopShown = 10;
    private const int TopCharted = 15;
    private const int NoteWide = 5;
    private const int ChartWide = 7;

    public static IReadOnlyList<BoardCard> Column(ColumnProfile p, string dataset)
    {
        var label = GridCards.IsLabelColumn(p.Column, Number(p.Min), Number(p.Max));
        string Amount(JsonElement? v) => v is { ValueKind: JsonValueKind.Number } n && label ? GridCards.Plain(n.GetDouble()) : v is { } some ? GridCards.Cell(some) : string.Empty;
        (string Name, string? Value)[] measures =
        [
            ("Lowest", p.Min is { } min ? Amount(min) : null), ("1st quartile", Num(p.Q1, label)), ("Median", Num(p.Median, label)), ("Mean", Num(p.Mean, false)),
            ("3rd quartile", Num(p.Q3, label)), ("Highest", p.Max is { } max ? Amount(max) : null), ("Standard deviation", Num(p.Stddev, false)), ("Sum", Num(p.Sum, false)),
            ("Zeros", Count(p.Zeros)), ("Negatives", Count(p.Negatives)), ("Shortest text", Count(p.Shortest)), ("Longest text", Count(p.Longest)),
            ("Empty text", Count(p.EmptyStrings)), ("Padded with spaces", Count(p.Padded)), ("Earliest", Text(p.Earliest)), ("Latest", Text(p.Latest)),
        ];
        var stats = measures.Where(m => m.Value is not null).Select(m => (IReadOnlyList<string>)[m.Name, m.Value!]).ToList();
        var lines = new List<string>
        {
            $"# Profile of {p.Column}",
            $"**{GridCards.Format(p.Rows)} rows, {GridCards.Format(p.Distinct)} different values{(p.AllUnique ? " (every row different)" : string.Empty)}, {GridCards.Format(p.Blanks)} blank ({p.BlankPercent.ToString(CultureInfo.InvariantCulture)}%).** A {p.Type.ToLowerInvariant()} column of `{dataset}`.",
        };
        if (stats.Count > 0)
        {
            lines.AddRange([string.Empty, GridCards.Table(["Measure", "Value"], stats, [false, true])]);
        }
        if (p.TopValues.Count > 0)
        {
            var top = p.TopValues.Take(TopShown).Select(t => (IReadOnlyList<string>)[Shown(t.Value, label), GridCards.Format(t.Count), Percent(t.Count / (double)Math.Max(1, p.Rows))]);
            lines.AddRange([string.Empty, "#### Most common values", GridCards.Table(["Value", "Rows", "Share"], top, [false, true, true])]);
        }
        return Pair($"Profile of {p.Column}", string.Join("\n", lines), Figure(p, label));
    }

    public static IReadOnlyList<BoardCard> Table(TableProfile r, string dataset)
    {
        var rows = r.Columns.Select(c =>
        {
            var label = GridCards.IsLabelColumn(c.Column, Number(c.Min), Number(c.Max));
            string Edge(JsonElement? v) => v is { ValueKind: JsonValueKind.Number } n && label ? GridCards.Plain(n.GetDouble()) : v is { } some ? GridCards.Cell(some) : string.Empty;
            return (IReadOnlyList<string>)[c.Column, c.Type.ToLowerInvariant(), GridCards.Format(c.Blanks), $"{c.BlankPercent.ToString(CultureInfo.InvariantCulture)}%", GridCards.Format(c.Distinct), Edge(c.Min), Edge(c.Max)];
        });
        var markdown = string.Join("\n",
            $"# Profile of {dataset}",
            $"**{GridCards.Format(r.Rows)} rows, {GridCards.Format(r.Columns.Count)} columns, {GridCards.Format(r.DuplicateRows)} duplicate rows.**",
            string.Empty,
            GridCards.Table(["Column", "Type", "Blank", "Blank %", "Different values", "Lowest", "Highest"], rows, [false, false, true, true, true, false, false]));
        return Pair($"Profile of {dataset}", markdown, null).Select(c => c with { Size = c.Size with { W = 12 } }).ToList();
    }

    /// <summary>A note and its chart, sized to sit side by side.</summary>
    private static IReadOnlyList<BoardCard> Pair(string title, string markdown, object? figure)
    {
        var lines = markdown.Split('\n').Length;
        var high = Math.Max(7, Math.Min(18, (int)Math.Ceiling((lines * 23 + 60) / 52.0)));
        var note = new BoardCard("note", title, markdown, new CardSize(figure is null ? 12 : NoteWide, high));
        return figure is null ? [note] : [note, new BoardCard("plotly", $"{title} (chart)", JsonSerializer.Serialize(figure), new CardSize(ChartWide, high))];
    }

    private static object? Figure(ColumnProfile p, bool label)
    {
        var layout = new Dictionary<string, object> { ["font"] = new { size = 12 }, ["hovermode"] = "closest" };
        if (p.Histogram is { Count: > 0 } bins)
        {
            var trace = new { type = "bar", x = bins.Select(b => (b.Low + b.High) / 2), y = bins.Select(b => b.Count), width = bins.Select(b => (b.High - b.Low) * 0.95), marker = new { color = "theme:accent" }, hovertemplate = "%{x}: %{y} rows<extra></extra>" };
            return new { data = new[] { trace }, layout = Merge(layout, new() { ["xaxis"] = Axis(p.Column), ["yaxis"] = Axis("Rows"), ["bargap"] = 0 }) };
        }
        if (p.ByMonth is { Count: > 0 } months)
        {
            var trace = new { type = "scatter", mode = "lines+markers", x = months.Select(m => m.Month), y = months.Select(m => m.Count), line = new { color = "theme:accent", width = 2 }, hovertemplate = "%{x}: %{y} rows<extra></extra>" };
            return new { data = new[] { trace }, layout = Merge(layout, new() { ["xaxis"] = Axis($"{p.Column} (by month)"), ["yaxis"] = Axis("Rows") }) };
        }
        if (p.TopValues.Count > 1)
        {
            var top = p.TopValues.Take(TopCharted).Reverse().ToList();
            var trace = new { type = "bar", orientation = "h", x = top.Select(t => t.Count), y = top.Select(t => Shown(t.Value, label)), marker = new { color = "theme:accent" }, hovertemplate = "%{y}: %{x} rows<extra></extra>" };
            return new { data = new[] { trace }, layout = Merge(layout, new() { ["xaxis"] = Axis("Rows"), ["yaxis"] = new { automargin = true, type = "category" } }) };
        }
        return null;
    }

    private static object Axis(string title) => new { title = new { text = title } };

    private static Dictionary<string, object> Merge(Dictionary<string, object> a, Dictionary<string, object> b) => a.Concat(b).ToDictionary(x => x.Key, x => x.Value);

    private static string Shown(JsonElement v, bool label) => v.ValueKind switch
    {
        JsonValueKind.Null or JsonValueKind.Undefined => "(blank)",
        JsonValueKind.Number when label => GridCards.Plain(v.GetDouble()),
        _ => GridCards.Cell(v),
    };

    private static string? Num(double? v, bool label) => v is { } n ? label ? GridCards.Plain(n) : GridCards.Format(n) : null;

    private static string? Count(long? v) => v is { } n ? GridCards.Format(n) : null;

    private static string? Text(JsonElement? v) => v is { ValueKind: not JsonValueKind.Null } some ? GridCards.Cell(some) : null;

    private static double? Number(JsonElement? v) => v is { ValueKind: JsonValueKind.Number } n ? n.GetDouble() : null;

    private static string Percent(double share) => $"{(100 * share).ToString(share < 0.1 ? "0.0" : "0", CultureInfo.InvariantCulture)}%";
}
