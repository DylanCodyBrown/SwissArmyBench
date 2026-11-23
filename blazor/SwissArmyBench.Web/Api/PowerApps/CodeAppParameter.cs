using System.Text.Json;

namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>One input of an operation.</summary>
public sealed record CodeAppParameter
{
    public string Name { get; init; } = string.Empty;

    public string In { get; init; } = string.Empty;

    public string Type { get; init; } = string.Empty;

    public bool Required { get; init; }

    public JsonElement Default { get; init; }

    public string Description { get; init; } = string.Empty;
}
