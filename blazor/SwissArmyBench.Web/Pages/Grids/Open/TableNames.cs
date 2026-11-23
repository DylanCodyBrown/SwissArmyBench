using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Grids.Open;

/// <summary>A file's name as a table's (the classic openFile.ts tableName): orders 2026.csv is orders_2026, a sheet
/// adds its name; letters, digits, _ and - only, at most 64; nothing left is "table".</summary>
public static partial class TableNames
{
    private const int Longest = 64;

    /// <summary>The kinds a table opens from (adapters/datasets.py SUFFIXES).</summary>
    public static readonly IReadOnlyList<string> Suffixes = [".csv", ".tsv", ".txt", ".parquet", ".json", ".jsonl", ".ndjson", ".arrow", ".feather", ".xlsx"];

    public static string FromFile(string file, string? sheet = null)
    {
        var leaf = file.Split('/', '\\').Last();
        var dot = leaf.LastIndexOf('.');
        var stem = dot > 0 ? leaf[..dot] : leaf;
        var joined = string.Join("_", new[] { stem, sheet }.Where(p => !string.IsNullOrEmpty(p)));
        var name = Unsafe().Replace(joined, "_").Trim('_');
        name = name[..Math.Min(name.Length, Longest)];
        return name.Length > 0 ? name : "table";
    }

    public static bool IsWorkbook(string file) => file.EndsWith(".xlsx", StringComparison.OrdinalIgnoreCase);

    [GeneratedRegex("[^A-Za-z0-9_-]+")]
    private static partial Regex Unsafe();
}
