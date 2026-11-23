namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>The app's name, environment, its id once pushed, its local address.</summary>
public sealed record CodeAppInfo
{
    public string Name { get; init; } = string.Empty;

    public string EnvironmentId { get; init; } = string.Empty;

    public string? AppId { get; init; }

    public string LocalUrl { get; init; } = string.Empty;
}
