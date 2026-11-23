namespace SwissArmyBench.Web.Api.Grids;

/// <summary>The first column that differs, by each side's own name for it.</summary>
public sealed record CompareFirst(string Left, string Right);
