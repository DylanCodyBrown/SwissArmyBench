namespace SwissArmyBench.Web.Api.Git;

/// <summary>One repository the user can pick: its name, branch and whether it is private.</summary>
public sealed record ScmRepositoryChoice
{
    public string Repository { get; init; } = string.Empty;

    public string Branch { get; init; } = string.Empty;

    public bool Private { get; init; }
}
