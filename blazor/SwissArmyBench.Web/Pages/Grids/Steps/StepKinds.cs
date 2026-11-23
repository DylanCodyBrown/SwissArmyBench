namespace SwissArmyBench.Web.Pages.Grids.Steps;

/// <summary>Each step kind's name in words (the classic stepForms.ts KIND_LABELS).</summary>
public static class StepKinds
{
    public static string Label(string kind) => kind switch
    {
        "filter" => "Filter",
        "sort" => "Sort",
        "columns" => "Choose columns",
        "rename" => "Rename",
        "group_by" => "Group by",
        "distinct" => "Distinct rows",
        "limit" => "Keep first rows",
        "transform" => "Clean text",
        "bucket" => "Bucket",
        "categorize" => "Categorize",
        "sql" => "SQL transformation",
        _ => kind,
    };

    /// <summary>The kinds this page has a form for .</summary>
    public static bool HasForm(string kind) => kind is "filter" or "sort" or "columns" or "rename" or "group_by" or "limit" or "transform" or "bucket" or "categorize" or "sql";
}
