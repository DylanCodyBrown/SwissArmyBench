namespace SwissArmyBench.Web.Api.Git;

/// <summary>The repository's branches on GitHub and the current one.</summary>
public sealed record ScmBranches
{
    public string Current { get; init; } = string.Empty;

    public IReadOnlyList<ScmBranch> Branches { get; init; } = [];
}
