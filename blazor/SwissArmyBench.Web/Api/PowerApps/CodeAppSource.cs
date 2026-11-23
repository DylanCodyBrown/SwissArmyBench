namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>A data source of the app: a Dataverse table or a connector.</summary>
public sealed record CodeAppSource
{
    public string Name { get; init; } = string.Empty;

    public string Kind { get; init; } = string.Empty;

    public string Connector { get; init; } = string.Empty;

    public string? Table { get; init; }

    public string? Dataset { get; init; }

    public string? DisplayName { get; init; }
}
