using System.Text.Json;

namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /connections/{name}/relationships: the relationships brought into the model and what changed.</summary>
public sealed record RelationshipsAnswer(IReadOnlyList<JsonElement> Imported, IReadOnlyList<string>? Changed = null);
