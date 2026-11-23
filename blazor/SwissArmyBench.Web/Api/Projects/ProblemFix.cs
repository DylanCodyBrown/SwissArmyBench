namespace SwissArmyBench.Web.Api.Projects;

/// <summary>A problem's fix: its kind (retry, remove, find_file, add_connection, password, open_notebook), its button's
/// words, and what it is about (the connection, the file and its suffix, the notebook).</summary>
public sealed record ProblemFix(
    string Kind,
    string Label,
    string? Connection = null,
    string? File = null,
    string? Suffix = null,
    string? Notebook = null);
