namespace SwissArmyBench.Web.Api.Git;

/// <summary>A folder GitHub sync can link (the team library, the shared projects): its link and its words.</summary>
public sealed record ScmFolder
{
    public string Which { get; init; } = string.Empty;

    public string? Folder { get; init; }

    public bool Set { get; init; }

    public bool Connected { get; init; }

    public string? Repository { get; init; }

    public string? Branch { get; init; }

    public string Words { get; init; } = string.Empty;

    public string State { get; init; } = string.Empty;
}
