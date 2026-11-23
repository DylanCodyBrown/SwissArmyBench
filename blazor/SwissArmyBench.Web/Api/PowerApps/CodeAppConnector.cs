namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>A connector: its names, description, whether it has tables, whether the app has it.</summary>
public sealed record CodeAppConnector
{
    public string Name { get; init; } = string.Empty;

    public string DisplayName { get; init; } = string.Empty;

    public string Description { get; init; } = string.Empty;

    public bool Tabular { get; init; }

    public bool InApp { get; init; }
}
