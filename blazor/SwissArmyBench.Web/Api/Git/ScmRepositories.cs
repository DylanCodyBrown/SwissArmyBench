namespace SwissArmyBench.Web.Api.Git;

/// <summary>The signed-in user's repositories (Clone and Connect's quick pick).</summary>
public sealed record ScmRepositories
{
    public IReadOnlyList<ScmRepositoryChoice> Repositories { get; init; } = [];
}
