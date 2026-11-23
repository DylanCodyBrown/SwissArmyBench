namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>A push done: the app's link.</summary>
public sealed record CodeAppPushed
{
    public string? Link { get; init; }
}
