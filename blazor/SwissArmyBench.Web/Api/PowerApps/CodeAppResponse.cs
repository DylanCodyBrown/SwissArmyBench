using System.Text.Json;

namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>One answer of an operation: its status, description, schema and example.</summary>
public sealed record CodeAppResponse
{
    public string Status { get; init; } = string.Empty;

    public string Description { get; init; } = string.Empty;

    public JsonElement Schema { get; init; }

    public JsonElement Example { get; init; }
}
