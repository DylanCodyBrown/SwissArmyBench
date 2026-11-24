using System.Globalization;
using System.Text.Json;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>A table result of another kernel (a mode's TypeScript or SQL cell; the classic workbenchOutputs.ts
/// TABLE_MIME bundle): its id, columns, DuckDB's types, its first rows and its total, drawn as data (never markup).
/// Open as table writes it whole by its id.</summary>
public sealed record ResultTable(
    string Id,
    IReadOnlyList<string> Columns,
    IReadOnlyList<string> Types,
    IReadOnlyList<JsonElement> Rows,
    long Total)
{
    public const string Mime = "application/vnd.swissarmybench.table+json";

    /// <summary>"1,200 rows, 3 columns: the first 200 shown".</summary>
    public string Said
    {
        get
        {
            var total = Total > 0 ? Total : Rows.Count;
            var rows = total == 1 ? "row" : "rows";
            var columns = Columns.Count == 1 ? "column" : "columns";
            var cut = total > Rows.Count ? $": the first {Rows.Count.ToString("N0", CultureInfo.CurrentCulture)} shown" : string.Empty;
            return $"{total.ToString("N0", CultureInfo.CurrentCulture)} {rows}, {Columns.Count} {columns}{cut}";
        }
    }

    /// <summary>The bundle an output carries, or null.</summary>
    public static ResultTable? Of(JsonElement output)
    {
        if (!output.TryGetProperty("data", out var data) || data.ValueKind != JsonValueKind.Object
            || !data.TryGetProperty(Mime, out var bundle) || bundle.ValueKind != JsonValueKind.Object)
        {
            return null;
        }
        return new ResultTable(
            Text(bundle, "id"),
            Strings(bundle, "columns"),
            Strings(bundle, "types"),
            bundle.TryGetProperty("rows", out var rows) && rows.ValueKind == JsonValueKind.Array ? [.. rows.EnumerateArray()] : [],
            bundle.TryGetProperty("total", out var total) && total.TryGetInt64(out var n) ? n : 0);
    }

    /// <summary>A cell's value as text: empty for none, an object or list as JSON.</summary>
    public static string Cell(JsonElement row, string column) =>
        row.ValueKind != JsonValueKind.Object || !row.TryGetProperty(column, out var value) ? string.Empty : value.ValueKind switch
        {
            JsonValueKind.Null or JsonValueKind.Undefined => string.Empty,
            JsonValueKind.String => value.GetString() ?? string.Empty,
            _ => value.GetRawText(),
        };

    private static string Text(JsonElement bundle, string name) =>
        bundle.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? string.Empty : string.Empty;

    private static List<string> Strings(JsonElement bundle, string name) =>
        bundle.TryGetProperty(name, out var list) && list.ValueKind == JsonValueKind.Array
            ? [.. list.EnumerateArray().Select(v => v.ValueKind == JsonValueKind.String ? v.GetString() ?? string.Empty : v.GetRawText())]
            : [];
}
