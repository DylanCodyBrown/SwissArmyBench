namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>What Push runs, the app and the environment.</summary>
public sealed record CodeAppPushPlan
{
    public IReadOnlyList<string> Commands { get; init; } = [];

    public string App { get; init; } = string.Empty;

    public string Environment { get; init; } = string.Empty;
}
