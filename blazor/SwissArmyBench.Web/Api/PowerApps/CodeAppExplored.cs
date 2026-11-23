namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>One connector read as the APIs explorer draws an API.</summary>
public sealed record CodeAppExplored
{
    public string Name { get; init; } = string.Empty;

    public string DisplayName { get; init; } = string.Empty;

    public string Title { get; init; } = string.Empty;

    public string From { get; init; } = string.Empty;

    public IReadOnlyList<CodeAppOperation> Operations { get; init; } = [];
}
