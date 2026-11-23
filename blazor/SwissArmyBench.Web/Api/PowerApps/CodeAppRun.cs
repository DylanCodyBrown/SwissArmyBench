namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>One pa, pac or npm run of this session: its command, who, its code, ok, done, output and time.</summary>
public sealed record CodeAppRun
{
    public string Id { get; init; } = string.Empty;

    public string Command { get; init; } = string.Empty;

    public string Who { get; init; } = string.Empty;

    public int? Code { get; init; }

    public bool Ok { get; init; }

    public bool Done { get; init; }

    public string Output { get; init; } = string.Empty;

    public double Seconds { get; init; }
}
