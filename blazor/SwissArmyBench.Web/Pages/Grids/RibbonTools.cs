using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>The ribbon's Table and Column tools (the classic ribbon.ts render): their ids, words, icons, tooltips and
/// the reason each does not apply now. The ribbon draws them; the command palette lists the same.</summary>
public static class RibbonTools
{
    /// <summary>What is on, in a few words ("case, trim"), or "ignore case" when nothing is.</summary>
    private static string MatchingWords(GridInfo info)
    {
        var s = info.Settings;
        (bool On, string Word)[] switches = s is null
            ? []
            : [(s.CaseSensitive, "case"), (s.Wildcards, "wildcards"), (s.TrimSpaces, "trim"), (s.EmptyIsBlank, "empty = blank")];
        var on = switches
            .Where(x => x.On)
            .Select(x => x.Word)
            .ToList();
        return on.Count > 0 ? string.Join(", ", on) : "ignore case";
    }

    public static IEnumerable<RibbonTool> Table(GridInfo info, string connectionLabel)
    {
        yield return new("matching", $"Matching: {MatchingWords(info)}", "case", "How text compares");
        yield return new("filter", "Filter", "filter");
        yield return new("sort", "Sort", "sortup");
        yield return new("columns", "Choose columns", "columns");
        yield return new("rename", "Rename", "rename");
        yield return new("group_by", "Group by", "group");
        yield return new("distinct", "Distinct rows", "keep");
        yield return new("limit", "Keep first rows", "rows");
        yield return new("transform", "Clean text", "clean");
        yield return new("autowidth", "Auto width", "columns", "Auto width: each column as wide as its values");
        yield return new("profile", "Profile", "profile", "Profile: every column's counts, blanks and values");
        yield return new("keyfinder", "Key Finder", "zoom", "Key Finder: the likely join keys");
        yield return new("relationships", "Relationships", "crown", "Relationships: keys and joins, found from the data");
        yield return new("export", "Export", "export", "Export: CSV, Excel or Parquet");
        yield return new("code", "Copy as code", "code", "Copy as code: the steps as one DuckDB query, verified");
        if (!info.Dataset.StartsWith("sandbox_", StringComparison.Ordinal))
        {
            yield return new("variant", "Make a sandbox variant", "branch", "Make a sandbox variant: a copy of this view in the project's sandbox, with its own name");
        }
        yield return new("connection", connectionLabel, "plug", $"{connectionLabel}: read this table from another connection");
    }

    public static IEnumerable<RibbonTool> Column(GridInfo info, IReadOnlyList<string> target)
    {
        string? noColumn = target.Count > 0 ? null : "Select a column first.";
        string? needOne = target.Count == 1 ? null : target.Count > 0 ? "Select one column." : "Select a column first.";
        var one = target.Count == 1 ? target[0] : string.Empty;
        var type = info.Columns.FirstOrDefault(c => c.Name == one)?.Type ?? string.Empty;
        var anyText = target.Any(name => ColumnTypes.IsText(info.Columns.FirstOrDefault(c => c.Name == name)?.Type ?? string.Empty));
        var bucketable = ColumnTypes.IsNumber(type) || ColumnTypes.IsDate(type) ? null : "Number or date columns only.";
        yield return new("col-sort-asc", "Sort A→Z", "sortup", Disabled: noColumn);
        yield return new("col-sort-desc", "Sort Z→A", "sortdown", Disabled: noColumn);
        yield return new("col-filter", "Filter…", "filter", Disabled: needOne);
        yield return new("col-rename", "Rename…", "rename", Disabled: noColumn);
        yield return new("col-autowidth", "Auto width", "columns", Disabled: noColumn);
        yield return new("col-remove", "Remove", "trash", "Remove selected columns", noColumn);
        yield return new("col-keep", "Keep only", "columns", Disabled: noColumn);
        yield return new("col-clean", "Clean text…", "clean", Disabled: noColumn ?? (anyText ? null : "Select a text column."));
        yield return new("col-bucket", "Bucket…", "bucket", Disabled: needOne ?? bucketable);
        yield return new("col-categorize", "Categorize…", "tag", Disabled: needOne);
        yield return new("col-group", "Group by…", "group", Disabled: noColumn);
        yield return new("col-profile", "Profile", "profile", Disabled: needOne);
    }
}
