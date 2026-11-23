namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A table a move could not take, and why.</summary>
public sealed record MoveFailure(string Table, string Error);
