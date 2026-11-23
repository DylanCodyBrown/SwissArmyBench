using System.Text.Json;

namespace SwissArmyBench.Web.Api.Grids;

/// <summary>POST /tables/{name}/connection: read the table from another connection. Swapped when it was found
/// there; Pick when several tables could be it; Review when its query must be looked over first; Failed's words
/// otherwise.</summary>
public sealed record ConnectionSwap(JsonElement? Swapped, JsonElement? Pick, JsonElement? Review, string? Failed);
