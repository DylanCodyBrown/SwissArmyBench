namespace SwissArmyBench.Web.Api.Grids;

/// <summary>Values that differ only by letter case ("North", "north"), and their rows.</summary>
public sealed record CaseGroup(IReadOnlyList<string> Variants, long Rows);
