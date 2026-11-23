namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>The environment's connectors, searched.</summary>
public sealed record CodeAppConnectors
{
    public IReadOnlyList<CodeAppConnector> Connectors { get; init; } = [];

    public int Total { get; init; }
}
