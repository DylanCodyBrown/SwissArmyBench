using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Grids.Cards;

/// <summary>
/// What the grid page sends to the Analyze board by hand, as cards that read as a report (the classic
/// analysisCards.ts and keyFinder.ts keyFinderCards): a value, a row, a column's profile, the whole table's, the
/// Key Finder's pairs. An analysis's own cards are made on the server.
/// </summary>
public static partial class GridCards
{
    private const int LongValue = 120;
    private const int FirstPairs = 15;

    private static readonly HashSet<string> _labelWords = ["year", "yr", "fy", "id", "key", "code", "zip", "postcode", "sku"];

    /// <summary>One value, titled with where it came from; a long or structured value in a code block.</summary>
    public static IReadOnlyList<BoardCard> Value(JsonElement value, string title, string dataset)
    {
        var text = value.ValueKind == JsonValueKind.String ? value.GetString() ?? string.Empty : value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined ? string.Empty : Pretty(value);
        var isLong = text.Length > LongValue || text.IndexOfAny(['\n', '{', '[']) >= 0;
        var shown = value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined ? "(blank)" : text.Length == 0 ? "(empty text)" : text;
        var markdown = string.Join("\n", $"# {title}", $"*A value from `{dataset}`.*", string.Empty, isLong ? $"```\n{text}\n```" : $"**{shown}**");
        return [new BoardCard("note", title, markdown, isLong ? new CardSize(6, 8) : new CardSize(4, 4))];
    }

    /// <summary>One row: each column and its value, as a two-column table.</summary>
    public static IReadOnlyList<BoardCard> Row(IReadOnlyList<(string Column, JsonElement Value)> values, long row, string dataset)
    {
        var title = $"Row {Format(row + 1)} of {dataset}";
        var rows = values.Select(v => (IReadOnlyList<string>)[v.Column, v.Value switch
        {
            { ValueKind: JsonValueKind.Null or JsonValueKind.Undefined } => "(blank)",
            { ValueKind: JsonValueKind.Object or JsonValueKind.Array } nested => nested.GetRawText(),
            { ValueKind: JsonValueKind.Number } number when IsLabelColumn(v.Column) => Plain(number.GetDouble()),
            var other => Cell(other),
        }]).ToList();
        var markdown = string.Join("\n", $"# {title}", string.Empty, Table(["Column", "Value"], rows));
        var high = Math.Max(5, Math.Min(18, (int)Math.Ceiling(values.Count * 0.6) + 3));
        return [new BoardCard("note", title, markdown, new CardSize(5, high))];
    }

    /// <summary>A Markdown table; `right` marks the columns aligned right (numbers).</summary>
    public static string Table(IReadOnlyList<string> head, IEnumerable<IReadOnlyList<string>> rows, IReadOnlyList<bool>? right = null)
    {
        var rule = head.Select((_, i) => right is not null && i < right.Count && right[i] ? "---:" : "---");
        var lines = rows.Select(r => $"| {string.Join(" | ", r.Select(Escape))} |");
        return string.Join("\n", new[] { $"| {string.Join(" | ", head)} |", $"| {string.Join(" | ", rule)} |" }.Concat(lines));
    }

    /// <summary>The Key Finder's pairs as a report.</summary>
    public static IReadOnlyList<BoardCard> KeyFinder(Api.Grids.KeyFinderResult result, IReadOnlyList<string> targets)
    {
        static string Share(double v) => $"{Math.Round(100 * v).ToString(CultureInfo.InvariantCulture)}%";
        var with = targets.Count > 0 ? string.Join(", ", targets.Select(t => $"`{t}`")) : "no other table";
        var markdown = string.Join("\n",
            $"# Likely join columns for {result.Source}",
            $"**{Format(result.PairCount)} column pair{(result.PairCount == 1 ? string.Empty : "s")} share values** with {with}.",
            string.Empty,
            Table([$"{result.Source} column", "Table", "Column", "Relationship", $"Found from {result.Source}", "Found from the other", "Shared values"],
                result.Pairs.Take(FirstPairs).Select(p => (IReadOnlyList<string>)[p.SourceColumn, p.TargetDataset, p.TargetColumn, p.Relationship, Share(p.SourceFound), Share(p.TargetFound), Format(p.Shared)]),
                [false, false, false, false, true, true, true]));
        var high = Math.Min(16, 5 + Math.Min(FirstPairs, result.Pairs.Count));
        return [new BoardCard("note", $"Join columns for {result.Source}", markdown, new CardSize(12, high))];
    }

    /// <summary>A column whose numbers are labels (a year, an id, a code): shown as their digits.</summary>
    public static bool IsLabelColumn(string column, double? low = null, double? high = null)
    {
        var words = SplitWords().Split(CamelGap().Replace(column, "$1 $2").ToLowerInvariant()).Where(w => w.Length > 0);
        if (words.Any(w => _labelWords.Contains(w) || w.EndsWith("year", StringComparison.Ordinal)))
        {
            return true;
        }
        static bool Yearish(double? v) => v is { } n && n == Math.Floor(n) && n >= 1800 && n <= 2200;
        return Yearish(low) && Yearish(high);
    }

    public static string Format(double value) =>
        value == Math.Floor(value) ? value.ToString("#,0", CultureInfo.InvariantCulture) : value.ToString("#,0.##", CultureInfo.InvariantCulture);

    public static string Plain(double value) =>
        value == Math.Floor(value) ? value.ToString("0", CultureInfo.InvariantCulture) : Math.Round(value, 2).ToString(CultureInfo.InvariantCulture);

    /// <summary>A value as a table shows it: numbers grouped, text as it is.</summary>
    public static string Cell(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.Number => Format(value.GetDouble()),
        JsonValueKind.String => value.GetString() ?? string.Empty,
        JsonValueKind.Null or JsonValueKind.Undefined => string.Empty,
        JsonValueKind.True => "true",
        JsonValueKind.False => "false",
        _ => value.GetRawText(),
    };

    private static string Pretty(JsonElement value) => JsonSerializer.Serialize(value, new JsonSerializerOptions { WriteIndented = true });

    /// <summary>A cell's text: a bar inside a value would end the cell early.</summary>
    private static string Escape(string text) => text.Replace("|", "\\|", StringComparison.Ordinal).Replace("\n", " ", StringComparison.Ordinal);

    [GeneratedRegex("([a-z0-9])([A-Z])")]
    private static partial Regex CamelGap();

    [GeneratedRegex("[^a-z0-9]+")]
    private static partial Regex SplitWords();
}
