namespace SwissArmyBench.Web.Api.Grids;

/// <summary>Diff mode's summary: the matched rows that differ, each column's changes (most first), the columns
/// compared, what each side shows (its keys, then its columns that differ) and the first column that differs.</summary>
public sealed record CompareDiffer
{
    public CompareSides Shown { get; init; } = new();

    public CompareFirst? First { get; init; }

    public long Matched { get; init; }

    public long Differ { get; init; }

    public long LeftOnly { get; init; }

    public long RightOnly { get; init; }

    /// <summary>Each column that differs and in how many rows, most first (the server's order).</summary>
    public IReadOnlyDictionary<string, long> Columns { get; init; } = new Dictionary<string, long>();

    public IReadOnlyList<string> Compared { get; init; } = [];
}
