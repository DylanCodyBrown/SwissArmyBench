namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>The environment's code apps and this session's pushes.</summary>
public sealed record CodeAppVersions
{
    public IReadOnlyList<CodeAppVersion> Apps { get; init; } = [];

    public IReadOnlyList<CodeAppPush> Pushes { get; init; } = [];
}
