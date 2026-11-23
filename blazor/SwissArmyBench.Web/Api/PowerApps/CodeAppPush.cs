namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>One push this session.</summary>
public sealed record CodeAppPush
{
    public double At { get; init; }

    public string? Link { get; init; }

    public string Who { get; init; } = string.Empty;
}
