namespace SwissArmyBench.Web.Api.Grids;

/// <summary>How diff mode compares two cells: a tolerance for numbers (an amount, or a percent of the left value),
/// trimming and letter case for text, the columns left out, the one column looked at, and whether only the
/// columns that differ are shown.</summary>
public sealed record CompareDiffOptions
{
    public double Tolerance { get; init; }

    public bool Percent { get; init; }

    public bool Trim { get; init; } = true;

    public bool IgnoreCase { get; init; }

    public IReadOnlyList<string> Skip { get; init; } = [];

    public string? Column { get; init; }

    public bool OnlyDiffering { get; init; } = true;
}
