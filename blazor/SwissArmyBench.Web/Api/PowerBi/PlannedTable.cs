namespace SwissArmyBench.Web.Api.PowerBi;

/// <summary>One table in the plan: whether it goes, where Power Query reads it, why not and the fix, its rows, notes and what works only here.</summary>
public sealed record PlannedTable
{
    public string Name { get; init; } = string.Empty;

    public bool Goes { get; init; }

    public string Source { get; init; } = string.Empty;

    public string? Why { get; init; }

    public string? Fix { get; init; }

    public bool NeedsRows { get; init; }

    public bool Rows { get; init; }

    public IReadOnlyList<string> Notes { get; init; } = [];

    public IReadOnlyList<string> Local { get; init; } = [];

    public int Columns { get; init; }

    public long? RowCount { get; init; }
}
