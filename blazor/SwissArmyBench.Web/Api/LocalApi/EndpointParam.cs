using System.Text.Json;

namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>One input of a local sandbox API's endpoint: its name, where it goes (path, query, body), its type and default.</summary>
public sealed record EndpointParam(
    string Name,
    string Where,
    string Type = "",
    bool Required = false,
    JsonElement? Default = null);
