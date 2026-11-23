namespace SwissArmyBench.Web.Api.Git;

/// <summary>A commit's changed files (a graph row opened).</summary>
public sealed record ScmCommitFiles
{
    public IReadOnlyList<ScmResource> Files { get; init; } = [];
}
