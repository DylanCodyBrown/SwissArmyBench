namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A file in the Files pane: its name, its whole path, its module, what it is made from and whether the app
/// makes it (read-only) or a hand edited it, whether it is the library's, and its outline (classes and functions).</summary>
public sealed record TreeFile(
    string Path,
    string Name,
    string? Full,
    string? Module,
    string? MadeFrom,
    bool ReadOnly,
    bool Edited = false,
    bool Library = false,
    IReadOnlyList<TreeSymbol>? Outline = null);
