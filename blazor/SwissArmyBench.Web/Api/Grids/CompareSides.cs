namespace SwissArmyBench.Web.Api.Grids;

/// <summary>The columns each side of a diff shows, under that side's own names.</summary>
public sealed record CompareSides
{
    public IReadOnlyList<string> Left { get; init; } = [];

    public IReadOnlyList<string> Right { get; init; } = [];
}
