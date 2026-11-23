namespace SwissArmyBench.Web.Api.Grids;

/// <summary>POST /connections/{name}/move: every table of a connection moved to another; those moved, those whose
/// query needs a look, those that need a pick, and those that failed.</summary>
public sealed record MoveAnswer(
    IReadOnlyList<Swapped> Moved,
    IReadOnlyList<MovedTable> Review,
    IReadOnlyList<SwapPick> Pick,
    IReadOnlyList<MoveFailure> Failed);
