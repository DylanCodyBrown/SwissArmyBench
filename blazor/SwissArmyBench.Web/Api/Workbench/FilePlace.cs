namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A file the Files pane made or moved (a copy, a package's __init__.py, the trash it went to).</summary>
public sealed record FilePlace(string? Path = null, string? To = null);
