using System.Globalization;
using System.Text.Json;

using SwissArmyBench.Web.Api.Accounting;

namespace SwissArmyBench.Web.Pages.Accounting;

/// <summary>The Excel canvas's rules that need no page (the classic excelCanvas.ts and excelPreview.ts): column
/// letters, a cell's row and column, a block's words, its column specs, the kinds' words and icons.</summary>
public static class WorkbookRules
{
    public static readonly IReadOnlyList<string> Kinds = ["title", "text", "table", "pivot", "chart"];

    public static readonly IReadOnlyList<string> Formats = ["", "general", "integer", "number", "currency", "accounting", "percent", "date", "month", "text"];

    public static readonly IReadOnlyList<string> Totals = ["", "sum", "count", "average", "min", "max"];

    public static readonly IReadOnlyList<string> Summaries = ["sum", "count", "average", "min", "max"];

    public static readonly IReadOnlyList<string> Comparisons = [">", ">=", "<", "<=", "=", "!="];

    public static readonly IReadOnlyList<string> Charts = ["column", "bar", "line", "pie", "combo"];

    private static readonly Dictionary<string, string> _words = new()
    {
        ["title"] = "Title",
        ["text"] = "Text",
        ["table"] = "Table",
        ["pivot"] = "Pivot",
        ["chart"] = "Chart",
    };

    private static readonly Dictionary<string, string> _icons = new()
    {
        ["title"] = "rename",
        ["text"] = "note",
        ["table"] = "table",
        ["pivot"] = "group",
        ["chart"] = "chart",
    };

    public static string Word(string kind) => _words.GetValueOrDefault(kind, kind);

    public static string IconOf(string kind) => _icons.GetValueOrDefault(kind, "page");

    /// <summary>1 is A, 27 is AA.</summary>
    public static string Letters(int n)
    {
        var word = string.Empty;
        while (n > 0)
        {
            var r = (n - 1) % 26;
            word = (char)('A' + r) + word;
            n = (n - 1) / 26;
        }
        return word;
    }

    public static int ColumnOf(string text) => text.ToUpperInvariant().Aggregate(0, (n, ch) => (n * 26) + ch - 64);

    /// <summary>"B3" is row 3, column 2; anything else A1.</summary>
    public static (int Row, int Column) CellAt(string cell)
    {
        var m = System.Text.RegularExpressions.Regex.Match(cell.Trim(), @"^\$?([A-Za-z]{1,3})\$?(\d+)$");
        return m.Success ? (int.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture), ColumnOf(m.Groups[1].Value)) : (1, 1);
    }

    public static string Address(int row, int column) => $"{Letters(column)}{row}";

    /// <summary>A table block's columns as specs (a name alone is a spec with only its name).</summary>
    public static IReadOnlyList<ColumnSpec> Specs(WorkbookBlock block) =>
        (block.Columns ?? [])
            .Select(c => c.ValueKind == JsonValueKind.String
                ? new ColumnSpec { Name = c.GetString() ?? string.Empty }
                : c.Deserialize<ColumnSpec>(Api.ApiClient.Json) ?? new ColumnSpec())
            .ToList();

    /// <summary>A pivot's columns: the names.</summary>
    public static IReadOnlyList<string> Names(WorkbookBlock block) =>
        (block.Columns ?? []).Select(c => c.ValueKind == JsonValueKind.String ? c.GetString() ?? string.Empty : c.TryGetProperty("name", out var n) ? n.GetString() ?? string.Empty : string.Empty).ToList();

    /// <summary>"a, b ,, c" as [a, b, c].</summary>
    public static IReadOnlyList<string> Split(string text) =>
        text.Split(',').Select(x => x.Trim()).Where(x => x.Length > 0).ToList();

    /// <summary>What a block says on the canvas: its text, its table, its pivot's shape, its chart.</summary>
    public static string Words(WorkbookBlock b, IReadOnlyList<WorkbookBlock> every)
    {
        if (b.Kind is "title" or "text")
        {
            return string.IsNullOrEmpty(b.Text) ? "(empty)" : b.Text;
        }
        if (b.Kind == "chart")
        {
            var from = every.FirstOrDefault(x => x.Id == b.From);
            var of = from is null ? string.Empty : $" of {from.Source?.Table ?? "a query"}";
            var titled = string.IsNullOrEmpty(b.Title) ? string.Empty : $": {b.Title}";
            return $"{b.Chart ?? "column"} chart{of}{titled}";
        }
        var source = b.Source?.Table ?? (b.Source?.Query is { Length: > 0 } ? "query" : "?");
        if (b.Kind == "pivot")
        {
            var rows = b.Rows is { Count: > 0 } r ? string.Join(", ", r) : "—";
            var columns = Names(b) is { Count: > 0 } c ? string.Join(", ", c) : "—";
            var values = string.Join(", ", (b.Values ?? []).Select(v => $"{v.Agg} {v.Column ?? string.Empty}".Trim()));
            return $"{source}: {rows} by {columns}, {values}";
        }
        var names = Specs(b).Select(c => string.IsNullOrEmpty(c.Label) ? c.Name : c.Label).ToList();
        return $"{source}{(names.Count > 0 ? ": " + string.Join(", ", names) : string.Empty)}{(b.TotalRow == true ? " · total row" : string.Empty)}";
    }

    /// <summary>A number as a value of a colour rule (text that reads as a number is the number).</summary>
    public static object RuleValue(string text) =>
        text.Trim().Length > 0 && double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var n) ? n : text;

    public static string Text(JsonElement? value) => value switch
    {
        null => string.Empty,
        { ValueKind: JsonValueKind.String } v => v.GetString() ?? string.Empty,
        { ValueKind: JsonValueKind.Null or JsonValueKind.Undefined } => string.Empty,
        { } v => v.GetRawText(),
    };
}
