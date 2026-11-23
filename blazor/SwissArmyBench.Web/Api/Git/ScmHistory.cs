namespace SwissArmyBench.Web.Api.Git;

/// <summary>A repository's history from GitHub: its rows, the refs, whether there is more.</summary>
public sealed record ScmHistory
{
    public string Which { get; init; } = string.Empty;

    public string Branch { get; init; } = string.Empty;

    public int Page { get; init; }

    public bool More { get; init; }

    public IReadOnlyList<ScmRow> Rows { get; init; } = [];

    public IReadOnlyList<ScmRef> Refs { get; init; } = [];

    public int Uncommitted { get; init; }
}
