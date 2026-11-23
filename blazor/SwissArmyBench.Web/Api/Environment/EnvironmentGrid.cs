namespace SwissArmyBench.Web.Api.Environment;

/// <summary>A grid that shows a table (a view of it, never a copy).</summary>
public sealed record EnvironmentGrid(string Id, string Name, int Steps = 0);
