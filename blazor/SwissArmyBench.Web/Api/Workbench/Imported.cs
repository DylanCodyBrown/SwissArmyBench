namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /project/import: what came in (each document's copy), and what was skipped (a name the project has).</summary>
public sealed record Imported(
    IReadOnlyList<ImportedDocument> Documents,
    IReadOnlyList<string> Connections,
    IReadOnlyList<string> Blades,
    IReadOnlyList<string> Skipped,
    IReadOnlyDictionary<string, System.Text.Json.JsonElement>? NeedsPassword);
