namespace SwissArmyBench.Web.Api.Git;

/// <summary>GitHub sync's state (GET /git): signed in, the device flow offered, the token's steps, each folder's link.</summary>
public sealed record ScmStatus
{
    public bool SignedIn { get; init; }

    public string? Account { get; init; }

    public bool Device { get; init; }

    public IReadOnlyList<string> TokenSteps { get; init; } = [];

    public IReadOnlyList<ScmFolder> Folders { get; init; } = [];
}
