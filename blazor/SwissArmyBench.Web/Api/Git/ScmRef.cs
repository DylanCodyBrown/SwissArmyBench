namespace SwissArmyBench.Web.Api.Git;

/// <summary>A branch's ref: local or remote, and its commit.</summary>
public sealed record ScmRef
{
    public string Id { get; init; } = string.Empty;

    public string Name { get; init; } = string.Empty;

    public string Commit { get; init; } = string.Empty;

    public string Kind { get; init; } = string.Empty;
}
