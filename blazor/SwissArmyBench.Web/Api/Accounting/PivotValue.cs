namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>A pivot block's value: its summary of a column, its format and label.</summary>
public sealed record PivotValue
{
    public string? Column { get; init; }

    public string Agg { get; init; } = "count";

    public string? Format { get; init; }

    public string? Label { get; init; }
}
