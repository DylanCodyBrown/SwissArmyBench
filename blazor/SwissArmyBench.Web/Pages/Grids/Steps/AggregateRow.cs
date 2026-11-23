namespace SwissArmyBench.Web.Pages.Grids.Steps;

/// <summary>One aggregate of a Group by being edited: its function, its column and the name it gets.</summary>
public sealed class AggregateRow
{
    public string Fn { get; set; } = "count_rows";

    public string Column { get; set; } = string.Empty;

    public string As { get; set; } = string.Empty;
}
