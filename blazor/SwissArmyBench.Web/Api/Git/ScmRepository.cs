namespace SwissArmyBench.Web.Api.Git;

/// <summary>One connected folder as a repository: its GitHub repository, branch, last synced commit, its groups of changes, how many, how far behind.</summary>
public sealed record ScmRepository
{
    public string Which { get; init; } = string.Empty;

    public string Name { get; init; } = string.Empty;

    public string Repository { get; init; } = string.Empty;

    public string Folder { get; init; } = string.Empty;

    public string? Scope { get; init; }

    public string Branch { get; init; } = string.Empty;

    public string? Commit { get; init; }

    public ScmGroups Groups { get; init; } = new();

    public int Count { get; init; }

    public int Behind { get; init; }

    public bool Pulled { get; init; }
}
