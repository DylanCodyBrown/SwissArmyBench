namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A new file asked for: its type, its name, the folder (inside the project, "" its top; with no project
/// open the folder's whole path), for a SQL file where it runs (null: DuckDB over the open tables) and, for a type
/// with kinds, the one picked; for a type made from another file (an import), that file's path.</summary>
public sealed record NewFileRequest(
    string Type,
    string Name,
    string Folder,
    string? Connection = null,
    string? Variant = null,
    string? Source = null);
