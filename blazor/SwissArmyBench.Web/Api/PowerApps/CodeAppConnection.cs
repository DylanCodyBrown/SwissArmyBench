namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>One connection: its id, name and status.</summary>
public sealed record CodeAppConnection
{
    public string Id { get; init; } = string.Empty;

    public string DisplayName { get; init; } = string.Empty;

    public string Status { get; init; } = string.Empty;
}
