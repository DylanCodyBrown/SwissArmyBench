namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A compare's rows: matched on the keys, and on one side only.</summary>
public sealed record CompareCounts
{
    public long Matched { get; init; }

    public long LeftOnly { get; init; }

    public long RightOnly { get; init; }
}
