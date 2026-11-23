namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>A Power Platform environment.</summary>
public sealed record CodeAppEnvironment
{
    public string Name { get; init; } = string.Empty;

    public string Id { get; init; } = string.Empty;

    public string Url { get; init; } = string.Empty;

    public bool Active { get; init; }

    public bool Project { get; init; }
}
