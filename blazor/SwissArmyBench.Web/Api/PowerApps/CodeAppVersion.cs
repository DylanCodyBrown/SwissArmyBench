namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>One of the environment's code apps.</summary>
public sealed record CodeAppVersion
{
    public string Id { get; init; } = string.Empty;

    public string Name { get; init; } = string.Empty;

    public bool This { get; init; }
}
