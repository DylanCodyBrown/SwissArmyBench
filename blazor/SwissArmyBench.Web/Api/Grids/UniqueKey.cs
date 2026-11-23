namespace SwissArmyBench.Web.Api.Grids;

/// <summary>The Key Finder's most distinct column combination (KeyFinderResult's unique_key): one step per column
/// added, the last the answer, other combinations as small that are also unique, the rows checked, and whether it
/// stopped at the time limit.</summary>
public sealed record UniqueKey
{
    public long RowsChecked { get; init; }

    public bool Limited { get; init; }

    public bool Stopped { get; init; }

    public IReadOnlyList<KeyCombo> Steps { get; init; } = [];

    public IReadOnlyList<KeyCombo> Alternatives { get; init; } = [];
}
