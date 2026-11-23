namespace SwissArmyBench.Web.Api.Git;

/// <summary>A file's two sides for the diff editor: their text, binary, added or deleted.</summary>
public sealed record ScmDiff
{
    public string Path { get; init; } = string.Empty;

    public string Original { get; init; } = string.Empty;

    public string Modified { get; init; } = string.Empty;

    public string? OriginalLabel { get; init; }

    public string? ModifiedLabel { get; init; }

    public bool Binary { get; init; }

    public bool Added { get; init; }

    public bool Deleted { get; init; }
}
