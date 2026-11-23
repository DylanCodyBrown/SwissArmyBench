namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>A custom connector's dry run: its two files, operations, title, host and sign-in.</summary>
public sealed record CustomConnectorPlan
{
    public IReadOnlyDictionary<string, string> Files { get; init; } = new Dictionary<string, string>();

    public int Operations { get; init; }

    public string Title { get; init; } = string.Empty;

    public string Host { get; init; } = string.Empty;

    public string SignIn { get; init; } = string.Empty;
}
