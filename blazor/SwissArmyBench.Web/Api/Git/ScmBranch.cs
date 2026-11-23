namespace SwissArmyBench.Web.Api.Git;

/// <summary>One branch: its name and commit.</summary>
public sealed record ScmBranch
{
    public string Name { get; init; } = string.Empty;

    public string Commit { get; init; } = string.Empty;
}
