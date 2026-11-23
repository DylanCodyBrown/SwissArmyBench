namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>One session state key made an In or an Out.</summary>
public sealed record UpgradeChange
{
    public string Key { get; init; } = string.Empty;

    public string Port { get; init; } = string.Empty;

    public string Direction { get; init; } = string.Empty;

    public string Type { get; init; } = string.Empty;
}
