namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A place the Scripts IDE found (a definition, a reference, a search match): its file (null: the text
/// sent), line and column, the name, its module, whether it is the project's or built in, and its line's text.</summary>
public sealed record IdePlace(
    string? Path,
    int Line,
    int Column,
    string Name,
    string? Module = null,
    bool InProject = true,
    bool Builtin = false,
    string? Text = null);
