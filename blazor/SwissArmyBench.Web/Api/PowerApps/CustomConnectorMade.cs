namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>A custom connector made: the files written.</summary>
public sealed record CustomConnectorMade
{
    public bool Made { get; init; }

    public IReadOnlyList<string> Files { get; init; } = [];
}
