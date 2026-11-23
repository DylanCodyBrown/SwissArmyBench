namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A file in the Files pane: its name, its whole path, and whether the app makes it (read-only).</summary>
public sealed record TreeFile(
    string Path,
    string Name,
    string? Full,
    string? Module,
    string? MadeFrom,
    bool ReadOnly);
