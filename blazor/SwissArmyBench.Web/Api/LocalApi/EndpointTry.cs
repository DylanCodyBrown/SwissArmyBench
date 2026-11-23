using System.Text.Json;

namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>A made-up request from an endpoint's definition and its learned shape (no kept value).</summary>
public sealed record EndpointTry(
    IReadOnlyDictionary<string, JsonElement>? Path = null,
    IReadOnlyDictionary<string, JsonElement>? Query = null,
    JsonElement? Body = null);
