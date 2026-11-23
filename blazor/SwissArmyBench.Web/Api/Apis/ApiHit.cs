using System.Text.Json;

namespace SwissArmyBench.Web.Api.Apis;

/// <summary>One result of Search every API: the API, the operation, its method and path, its name, what matched.</summary>
public sealed record ApiHit(
    string Api,
    string Operation,
    string Method,
    string Path,
    string Name,
    IReadOnlyDictionary<string, JsonElement>? Matched = null);
