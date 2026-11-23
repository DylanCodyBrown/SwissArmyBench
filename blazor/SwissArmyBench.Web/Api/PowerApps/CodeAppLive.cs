namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>Run live: running, ready, the pane's address, Local Play's.</summary>
public sealed record CodeAppLive
{
    public bool Running { get; init; }

    public bool Ready { get; init; }

    public string? Pane { get; init; }

    public string? PlayUrl { get; init; }

    public string? LocalUrl { get; init; }
}
