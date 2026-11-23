using System.Text.Json;

namespace SwissArmyBench.Web.Api.Projects;

/// <summary>POST /project/import: what was copied in, what the project already had (skipped), and the connections
/// that need a password on this computer.</summary>
public sealed record Imported(
    IReadOnlyList<ImportedDocument> Documents,
    IReadOnlyList<string> Connections,
    IReadOnlyList<string> Blades,
    IReadOnlyList<string> Skipped,
    IReadOnlyDictionary<string, JsonElement> NeedsPassword);
