namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A grid the Key Finder compared with: its id, its tab's words, its table.</summary>
public sealed record KeyTarget(string Grid, string Label, string Dataset);
