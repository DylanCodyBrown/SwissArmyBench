namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>POST /local-api/scaffold: the endpoints added to API.py, the line the first starts on, the file, a note.</summary>
public sealed record Scaffolded(
    IReadOnlyList<string> Added,
    int Line,
    string File,
    string? Note = null);
