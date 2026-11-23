using System.Text.Json;

namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>An operation's body: required, its schema and example.</summary>
public sealed record CodeAppBody
{
    public bool Required { get; init; }

    public JsonElement Schema { get; init; }

    public JsonElement Example { get; init; }
}
