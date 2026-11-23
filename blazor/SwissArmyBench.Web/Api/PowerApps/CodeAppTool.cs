namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>One tool: found with its version, ok, its phase, and this system's install command.</summary>
public sealed record CodeAppTool
{
    public string Id { get; init; } = string.Empty;

    public string Name { get; init; } = string.Empty;

    public string Purpose { get; init; } = string.Empty;

    public bool Found { get; init; }

    public string? Version { get; init; }

    public bool Ok { get; init; }

    public int Phase { get; init; }

    public string Install { get; init; } = string.Empty;

    public string? Problem { get; init; }
}
