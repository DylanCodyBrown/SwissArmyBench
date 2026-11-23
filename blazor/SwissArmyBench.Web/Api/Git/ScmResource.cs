namespace SwissArmyBench.Web.Api.Git;

/// <summary>One changed file: its path, status, VS Code's letter, tooltip and git decoration colour.</summary>
public sealed record ScmResource
{
    public string Path { get; init; } = string.Empty;

    public string Status { get; init; } = string.Empty;

    public string Letter { get; init; } = string.Empty;

    public string Tooltip { get; init; } = string.Empty;

    public string Colour { get; init; } = string.Empty;

    public string? Previous { get; init; }
}
