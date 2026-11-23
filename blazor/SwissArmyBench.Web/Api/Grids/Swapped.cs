namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A table now read from another connection: from which, to which, and the steps that no longer fit.</summary>
public sealed record Swapped(string Table, string? From, string To, IReadOnlyList<string> StepsProblems);
