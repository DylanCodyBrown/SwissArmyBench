using System.Text.Json;

namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>A connection's relationships imported into the model (POST /connections/{name}/relationships).</summary>
public sealed record ImportedRelationships(IReadOnlyList<JsonElement> Imported);
