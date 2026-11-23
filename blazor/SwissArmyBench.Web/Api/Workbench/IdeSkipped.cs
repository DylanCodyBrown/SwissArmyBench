namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A file a rename or replace leaves alone (a made file), and why.</summary>
public sealed record IdeSkipped(string Path, string Why);
