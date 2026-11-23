namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>A Dataverse source opened as a grid: opened, its dataset, or why not.</summary>
public sealed record CodeAppGrid
{
    public bool Opened { get; init; }

    public string? Dataset { get; init; }

    public string? Message { get; init; }
}
