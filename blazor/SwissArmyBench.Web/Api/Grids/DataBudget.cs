namespace SwissArmyBench.Web.Api.Grids;

/// <summary>The data budget: memory used of the total, tables of the most, tabs of the most, and whether it is past
/// the warning line (the status bar's meter shows then).</summary>
public sealed record DataBudget
{
    public long UsedBytes { get; init; }

    public long TotalBytes { get; init; }

    public string Used { get; init; } = string.Empty;

    public string Total { get; init; } = string.Empty;

    public int Datasets { get; init; }

    public int MaxDatasets { get; init; }

    public int Grids { get; init; }

    public int MaxGrids { get; init; }

    public bool Warn { get; init; }
}
