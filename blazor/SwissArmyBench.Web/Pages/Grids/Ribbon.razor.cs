using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids;

public partial class Ribbon
{
    // The caption names the first two columns, then how many more.
    private const int NamedInCaption = 2;

    [Parameter, EditorRequired]
    public GridInfo Info { get; set; } = default!;

    [Parameter, EditorRequired]
    public GridSelection Selection { get; set; } = GridSelection.None;

    /// <summary>"Connection: Finance", or "Connection…" while it is read.</summary>
    [Parameter]
    public string ConnectionLabel { get; set; } = "Connection…";

    /// <summary>The steps strip, drawn as the Transformations row.</summary>
    [Parameter]
    public RenderFragment? Steps { get; set; }

    /// <summary>A tool was pressed: its id (the page runs it on the selected columns).</summary>
    [Parameter]
    public EventCallback<string> OnTool { get; set; }

    private IReadOnlyList<string> Target => Selection.Target;

    private string ColumnCaption => Target.Count switch
    {
        0 => string.Empty,
        <= NamedInCaption => string.Join(", ", Target),
        _ => $"{string.Join(", ", Target.Take(NamedInCaption))} +{Target.Count - NamedInCaption}",
    };

    /// <summary>What is on, in a few words ("case, trim"), or "ignore case" when nothing is.</summary>
    private string MatchingWords
    {
        get
        {
            var s = Info.Settings;
            (bool On, string Word)[] switches = s is null
                ? []
                : [(s.CaseSensitive, "case"), (s.Wildcards, "wildcards"), (s.TrimSpaces, "trim"), (s.EmptyIsBlank, "empty = blank")];
            var on = switches
                .Where(x => x.On)
                .Select(x => x.Word)
                .ToList();
            return on.Count > 0 ? string.Join(", ", on) : "ignore case";
        }
    }

    private IEnumerable<RibbonTool> TableTools
    {
        get
        {
            yield return new("matching", $"Matching: {MatchingWords}", "case", "How text compares");
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
            if (!Info.Dataset.StartsWith("sandbox_", StringComparison.Ordinal))
            {
                yield return new("variant", "Make a sandbox variant", "branch", "Make a sandbox variant: a copy of this view in the project's sandbox, with its own name");
            }
            yield return new("connection", ConnectionLabel, "plug", $"{ConnectionLabel}: read this table from another connection");
        }
    }

    private IEnumerable<RibbonTool> ColumnTools
    {
        get
        {
            string? noColumn = Target.Count > 0 ? null : "Select a column first.";
            string? needOne = Target.Count == 1 ? null : Target.Count > 0 ? "Select one column." : "Select a column first.";
            var one = Target.Count == 1 ? Target[0] : string.Empty;
            var type = Info.Columns.FirstOrDefault(c => c.Name == one)?.Type ?? string.Empty;
            var anyText = Target.Any(name => ColumnTypes.IsText(Info.Columns.FirstOrDefault(c => c.Name == name)?.Type ?? string.Empty));
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
}
