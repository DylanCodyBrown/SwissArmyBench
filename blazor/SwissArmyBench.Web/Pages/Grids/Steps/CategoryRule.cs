namespace SwissArmyBench.Web.Pages.Grids.Steps;

/// <summary>One rule of a Categorize being edited: how it matches, its value (a list for "is one of"), the upper
/// end of a number range, and the label its rows get.</summary>
public sealed class CategoryRule
{
    public string Type { get; set; } = "wildcard";

    public string Value { get; set; } = string.Empty;

    public string High { get; set; } = string.Empty;

    public string Label { get; set; } = string.Empty;
}
