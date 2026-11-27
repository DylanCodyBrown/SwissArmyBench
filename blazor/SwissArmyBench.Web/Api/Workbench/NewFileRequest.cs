namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A new file asked for: its type, its name, the folder inside the project ("" its top) and, for a SQL
/// file, where it runs (null: DuckDB over the open tables).</summary>
public sealed record NewFileRequest(string Type, string Name, string Folder, string? Connection = null);
