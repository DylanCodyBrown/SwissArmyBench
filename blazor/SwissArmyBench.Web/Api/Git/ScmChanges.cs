namespace SwissArmyBench.Web.Api.Git;

/// <summary>The Source Control page's repositories (GET /git/changes): signed in, the account, each connected folder's changes.</summary>
public sealed record ScmChanges
{
    public bool SignedIn { get; init; }

    public string? Account { get; init; }

    public IReadOnlyList<ScmRepository> Repositories { get; init; } = [];
}
