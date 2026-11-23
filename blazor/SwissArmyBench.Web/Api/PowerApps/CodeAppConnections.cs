namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>A connector's connections in the environment.</summary>
public sealed record CodeAppConnections
{
    public IReadOnlyList<CodeAppConnection> Connections { get; init; } = [];
}
